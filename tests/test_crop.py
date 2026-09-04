"""
Drag-accumulation tests for apply_crop_changes.

The behaviour under test is the one BLENDER.md calls "A constrained drag must
accumulate deltas, not read absolute positions": when a drag runs into a limit,
the crop stops, and the first event heading back off the limit must move it
again. Reading the cursor's absolute position instead strands the user - the
crop sits still while the cursor travels on, and every pixel of that invisible
travel has to be dragged back before anything moves.

Every test here drives a *sequence* of events. That matters: stop-and-resume
does not exist inside a single event, so a one-shot test passes against both the
accumulating and the absolute version and proves nothing.

Deltas are in strip image space, which is what apply_crop_changes takes, so
these run without a region or a view2d.

Which of these actually catch the old behaviour, checked by replaying the same
sequences through the pre-2.0.4 implementation:

- zero_limit_resumes_immediately   old gives 0, new 25   - catches it
- opposite_edge_collision_resumes  old gives 8, new 5    - catches it
- axes_are_accepted_independently  old and new agree     - regression guard
- subpixel_motion_accumulates      old and new agree     - regression guard

The three tests below those cover projecting a blocked move onto the limit
instead of dropping it, which came after. Replayed against the refusing version:
escapes_an_overextended_crop is frozen at min_x=1200 through 580px of dragging,
and pushing_out_of_range_settles_on_the_limit discards a 500px move entirely
(min_x=0 instead of 9).

The last two pass against both versions, so they do not demonstrate the fix.
Keep them anyway: they pin properties the rewrite could plausibly have broken.
The old code tested each axis in its own branch, and it accumulated a total
displacement that grew every event, so per-event rounding never bit it. The new
code has to hold both properties deliberately - axis independence in the accept
loop, and a float crop_base. Turn crop_base back into integers and only
subpixel_motion_accumulates notices.

    "/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b \
        --factory-startup --python tests/test_crop.py
"""

import sys
import traceback
from pathlib import Path

import bpy

WORKSPACE = str(Path(__file__).resolve().parents[2])
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)

from BL_EasyCrop.operators.crop_core import apply_crop_changes  # noqa: E402

WIDTH, HEIGHT = 1920, 1080

# Handle indices, as apply_crop_changes numbers them.
CORNER_BL = 0
EDGE_LEFT = 4

failures = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}: expected {want}, got {got}")


def make_strip():
    """A COLOR strip on a fresh sequence editor, with crop zeroed."""
    scene = bpy.context.scene
    scene.render.resolution_x = WIDTH
    scene.render.resolution_y = HEIGHT

    if scene.sequence_editor:
        scene.sequence_editor_clear()
    editor = scene.sequence_editor_create()
    strips = editor.strips if hasattr(editor, "strips") else editor.sequences

    try:
        strip = strips.new_effect(name="crop_test", type='COLOR',
                                  channel=1, frame_start=1, frame_end=50)
    except TypeError:
        # new_effect(frame_end=...) became new_effect(length=...) in 5.1.
        strip = strips.new_effect(name="crop_test", type='COLOR',
                                  channel=1, frame_start=1, length=50)

    strip.crop.min_x = 0
    strip.crop.max_x = 0
    strip.crop.min_y = 0
    strip.crop.max_y = 0
    return strip


def drag(strip, handle, steps, base=None):
    """Feed a sequence of per-event (dx, dy) deltas through one drag.

    Returns the crop the drag ended on, the way a modal handler would carry it.
    """
    if base is None:
        base = (float(strip.crop.min_x), float(strip.crop.max_x),
                float(strip.crop.min_y), float(strip.crop.max_y))
    for dx, dy in steps:
        base = apply_crop_changes(handle, strip, dx, dy, base,
                                  WIDTH, HEIGHT, False, False)
    return base


def test_unconstrained_drag_tracks_the_cursor():
    """With nothing in the way, accumulating equals total displacement."""
    strip = make_strip()
    drag(strip, EDGE_LEFT, [(10.0, 0.0)] * 5)
    check("unconstrained: min_x after +50 of travel", strip.crop.min_x, 50)


def test_zero_limit_resumes_immediately():
    """Push the left edge past zero, then head back: it must move at once."""
    strip = make_strip()

    # Into the limit and well beyond it.
    drag(strip, EDGE_LEFT, [(-40.0, 0.0)] * 5)
    check("zero limit: min_x pinned at 0", strip.crop.min_x, 0)

    # One event back the other way. Accumulating onto the accepted 0 moves it
    # by the delta. Reading the absolute position would still be 160px inside
    # the disallowed region and would not move at all.
    base = (0.0, 0.0, 0.0, 0.0)
    drag(strip, EDGE_LEFT, [(25.0, 0.0)], base=base)
    check("zero limit: min_x after one event back", strip.crop.min_x, 25)


def test_opposite_edge_collision_resumes_immediately():
    """The two crops on an axis cannot meet; recovery must be immediate."""
    strip = make_strip()
    # Leave the left edge only 10px of room: min_x + max_x must stay < WIDTH.
    strip.crop.max_x = WIDTH - 10

    base = drag(strip, EDGE_LEFT, [(4.0, 0.0)] * 6)
    # 0 -> 4 -> 8 accepted; 12 is past the limit, so the move is projected onto
    # it. The limit is WIDTH - max_x - 1 = 9, and it settles exactly there
    # rather than stopping short at the last value that happened to fit.
    check("collision: min_x settled on the limit", strip.crop.min_x, 9)

    # Straight back off it, one event.
    drag(strip, EDGE_LEFT, [(-4.0, 0.0)], base=base)
    check("collision: min_x after one event back", strip.crop.min_x, 5)


def test_axes_are_accepted_independently():
    """A corner blocked on X must still slide along Y."""
    strip = make_strip()
    # No room left on X at all, Y wide open.
    strip.crop.max_x = WIDTH - 1

    drag(strip, CORNER_BL, [(6.0, 6.0)] * 4)
    check("independent axes: x blocked", strip.crop.min_x, 0)
    check("independent axes: y still moved", strip.crop.min_y, 24)


def test_subpixel_motion_accumulates():
    """A slow drag must not be swallowed by per-event rounding."""
    strip = make_strip()
    # Each event is well under a pixel; rounding per event would lose them all.
    drag(strip, EDGE_LEFT, [(0.4, 0.0)] * 25)
    check("subpixel: min_x after 25 x 0.4px", strip.crop.min_x, 10)


def test_escapes_an_overextended_crop():
    """A crop the sidebar pushed past the limit must be draggable back.

    StripCrop enforces nothing, so min_x + max_x can already exceed the strip
    width before the drag starts. Refusing every move that is still invalid
    freezes the handles completely: each event's delta is small, so no single
    one lands back inside the valid range, and the crop never moves however far
    the cursor travels.
    """
    strip = make_strip()
    # 1200 + 1200 = 2400, well past WIDTH. Only the sidebar can do this.
    strip.crop.min_x = 1200
    strip.crop.max_x = 1200

    # Small inward steps, none of which reach validity on its own.
    base = drag(strip, EDGE_LEFT, [(-20.0, 0.0)] * 4)
    check("overextended: small inward steps move the crop", strip.crop.min_x, 1120)

    # Keep going until it is back inside the valid range. min_x has to get
    # below WIDTH - max_x - 1 = 719 for the pair to be legal again, so this
    # takes a while - the other edge is doing most of the damage.
    drag(strip, EDGE_LEFT, [(-20.0, 0.0)] * 25, base=base)
    check("overextended: escapes to a valid crop", strip.crop.min_x, 620)
    check("overextended: and is valid",
          strip.crop.min_x + strip.crop.max_x < WIDTH, True)


def test_overextended_crop_cannot_be_made_worse():
    """While past the limit, only improving moves are taken."""
    strip = make_strip()
    strip.crop.min_x = 1200
    strip.crop.max_x = 1200

    drag(strip, EDGE_LEFT, [(20.0, 0.0)] * 3)
    check("overextended: outward drag is held", strip.crop.min_x, 1200)


def test_pushing_out_of_range_settles_on_the_limit():
    """From inside the valid range, a blocked move is projected, not dropped."""
    strip = make_strip()
    strip.crop.max_x = WIDTH - 10          # limit for min_x is 9

    # One big event straight past the limit.
    drag(strip, EDGE_LEFT, [(500.0, 0.0)])
    check("projection: lands on the limit", strip.crop.min_x, 9)
    check("projection: stays valid",
          strip.crop.min_x + strip.crop.max_x < WIDTH, True)


TESTS = (
    test_unconstrained_drag_tracks_the_cursor,
    test_zero_limit_resumes_immediately,
    test_opposite_edge_collision_resumes_immediately,
    test_axes_are_accepted_independently,
    test_subpixel_motion_accumulates,
    test_escapes_an_overextended_crop,
    test_overextended_crop_cannot_be_made_worse,
    test_pushing_out_of_range_settles_on_the_limit,
)


def main():
    version = bpy.app.version_string
    for test in TESTS:
        try:
            test()
        except Exception as exc:
            failures.append(f"{test.__name__} raised {type(exc).__name__}: {exc}")

    if failures:
        print(f"CROP {version} FAIL")
        for line in failures:
            print(f"  - {line}")
        return 1

    print(f"CROP {version} PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print(f"CROP {bpy.app.version_string} ERROR")
        traceback.print_exc()
        sys.exit(1)
