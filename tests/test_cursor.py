"""
A drag must not leave the pointer somewhere the handle is not.

Both interfaces accumulate per-event deltas and refuse a move that would take
the crop out of range, so a handle held against a limit stops while the mouse
carries on. The pointer and the handle then disagree by however far the
excursion went, and the pointer is the thing the user is watching.

The gizmo tool has always hidden the pointer, because use_grab_cursor does it,
and warped it back onto the handle in exit(). The modal operator did neither:
DEV.md argued that visible drift was the better half of the trade, since at
least the user can see what happened. Reported from a real session 2026-09-04,
it is not - a pointer that is plainly not on the handle it is still driving
reads as the control having come loose. Both interfaces now hide and warp.

What is pinned here:

- handle_window_position answers in *window* coordinates, and clamps to the
  region. Both are ways to put the pointer somewhere it must never go: region
  coordinates land it low and left of the editor by the region's origin, and an
  unclamped answer follows a handle that has been zoomed off the edge of the
  preview clean out of the editor - possibly off the screen.
- It reads the handle's position fresh from the crop rather than from anything
  the drag carried, which is the whole point: the drag's idea of where the
  cursor is is exactly what is wrong by then.
- The modal operator's hide and restore are balanced, idempotent, and ordered
  so that the warp still knows which handle the drag was on.

Not testable headlessly, and confirmed by hand instead: that the pointer
actually disappears, and that warping inline works for the modal operator where
the gizmo needs a timer. The gizmo defers because use_grab_cursor makes Blender
restore the pointer itself after exit() returns; this operator never grabs, so
nothing overwrites an inline warp.

    "/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b \
        --factory-startup --python tests/test_cursor.py
"""

import inspect
import sys
import traceback
from pathlib import Path
from typing import Any, cast

import bpy

WORKSPACE = str(Path(__file__).resolve().parents[2])
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)

from BL_EasyCrop.gizmos.crop_handles_gizmo import EASYCROP_GT_crop_handle  # noqa: E402
from BL_EasyCrop.operators.crop_core import handle_window_position  # noqa: E402
from BL_EasyCrop.operators.crop_operators import EASYCROP_OT_crop  # noqa: E402

WIDTH, HEIGHT = 1920, 1080
REGION_X, REGION_Y = 100, 50

failures = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}: expected {want}, got {got}")


def unbound(method):
    """Call a real method with a stand-in for self.

    These tests drive the addon's own methods against fakes, which is what lets
    the logic be exercised with no modal session and no gizmo Blender is
    driving. A type checker cannot tell a deliberate stand-in from a mistake,
    so the ones that are deliberate say so here.
    """
    return cast(Any, method)


class FakeView2D:
    """view_to_region as the identity on resolution space.

    res_to_screen subtracts half the render resolution before calling this,
    because the preview's View2D has its origin at the frame center. Adding it
    back means a handle at resolution (x, y) lands at region pixel (x, y), so
    every expected position below can be read straight off the crop.
    """

    def view_to_region(self, x, y, clip=False):
        return (int(round(x + WIDTH / 2)), int(round(y + HEIGHT / 2)))


class FakeRegion:
    """Only what handle_window_position reads off a region."""

    def __init__(self, x=REGION_X, y=REGION_Y, width=WIDTH, height=HEIGHT):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.view2d = FakeView2D()


def make_strip():
    """One croppable COLOR strip filling the frame, with no crop applied."""
    scene = bpy.context.scene
    scene.render.resolution_x = WIDTH
    scene.render.resolution_y = HEIGHT
    scene.frame_current = 1

    if scene.sequence_editor:
        scene.sequence_editor_clear()
    editor = scene.sequence_editor_create()
    strips = editor.strips if hasattr(editor, "strips") else editor.sequences

    try:
        strip = strips.new_effect(name="video", type='COLOR',
                                  channel=1, frame_start=1, frame_end=50)
    except TypeError:
        # new_effect(frame_end=...) became new_effect(length=...) in 5.1.
        strip = strips.new_effect(name="video", type='COLOR',
                                  channel=1, frame_start=1, length=50)

    editor.active_strip = strip
    return strip


def test_position_is_in_window_coordinates():
    """cursor_warp takes window coordinates; a region answer is off by origin.

    The bottom-left corner of an uncropped full-frame strip sits at region
    (0, 0), so the region's own origin is the entire answer here. Anything
    returning region coordinates gives (0, 0) and puts the pointer in the corner
    of the Blender window instead of the corner of the preview.
    """
    strip = make_strip()
    region = FakeRegion()

    got = handle_window_position(strip, bpy.context.scene, region, 0)
    check("bottom-left corner in window coords", got, (REGION_X, REGION_Y))


def test_position_is_clamped_to_the_region():
    """A handle off the edge of the preview must not take the pointer with it.

    Zoom the preview in and the crop rect leaves the view; the top-right corner
    of a full-frame strip is already one pixel outside a region exactly the size
    of the frame. Unclamped this returns the region's far corner plus its
    origin, which is outside the editor and, on a region near the edge of the
    screen, outside the window.
    """
    strip = make_strip()
    region = FakeRegion()

    got = handle_window_position(strip, bpy.context.scene, region, 2)
    check("top-right corner clamped inside the region", got,
          (REGION_X + WIDTH - 1, REGION_Y + HEIGHT - 1))

    # Off the other end too: a small region clamps to its own bottom-left.
    small = FakeRegion(width=200, height=200)
    check("far corner clamped to a small region",
          handle_window_position(strip, bpy.context.scene, small, 2),
          (REGION_X + 199, REGION_Y + 199))


def test_indices_four_to_seven_are_the_edge_midpoints():
    """The flat numbering both interfaces hit-test with: 0-3 corners, 4-7 edges.

    The gizmo stores handle_type and handle_index separately and has to convert.
    Getting that wrong is silent - it warps to a real handle, just not the one
    the drag was on - so the mapping is pinned rather than trusted.
    """
    strip = make_strip()
    region = FakeRegion()
    scene = bpy.context.scene

    # Left edge midpoint of a full-frame strip: x = 0, y = half the height.
    check("index 4 is the left edge midpoint",
          handle_window_position(strip, scene, region, 4),
          (REGION_X, REGION_Y + HEIGHT // 2))

    # Top edge midpoint: x = half the width, y = clamped to the top.
    check("index 5 is the top edge midpoint",
          handle_window_position(strip, scene, region, 5),
          (REGION_X + WIDTH // 2, REGION_Y + HEIGHT - 1))


def test_position_follows_the_crop():
    """The answer is read fresh from the crop, not carried from the drag.

    This is the property the whole fix rests on. The drag's own idea of where
    the pointer is is what has gone wrong by the time the warp runs, so a warp
    computed from anything the drag accumulated would put the pointer back
    exactly where it should not be.
    """
    strip = make_strip()
    region = FakeRegion()
    scene = bpy.context.scene

    before = handle_window_position(strip, scene, region, 0)
    if before is None:
        # Report rather than raise: a None here is a failure of this test's
        # premise, not a crash the runner should have to interpret.
        check("geometry available before the move", before, "an (x, y) tuple")
        return

    strip.crop.min_x = 300
    strip.crop.min_y = 200
    after = handle_window_position(strip, scene, region, 0)

    check("bottom-left corner moved with the crop", after,
          (before[0] + 300, before[1] + 200))


def test_missing_geometry_is_reported_not_guessed():
    """No region, no answer - and the caller must not then hide the pointer.

    Both callers return early on None. Returning a plausible fallback instead
    would hide the pointer and warp it somewhere arbitrary, which is the one
    outcome worse than not warping at all.
    """
    strip = make_strip()
    check("no region", handle_window_position(strip, bpy.context.scene, None, 0), None)
    check("no strip", handle_window_position(None, bpy.context.scene, FakeRegion(), 0), None)


class FakeWindow:
    """Records the cursor calls the operator makes, in order."""

    def __init__(self):
        self.calls = []

    def cursor_modal_set(self, cursor):
        self.calls.append(("set", cursor))

    def cursor_modal_restore(self):
        self.calls.append(("restore",))

    def cursor_warp(self, x, y):
        self.calls.append(("warp", x, y))


class FakeContext:
    """Only what _hide_cursor and _restore_cursor read off a context."""

    def __init__(self, window, region=None, scene=None):
        self.window = window
        self.region = region
        self.scene = scene


class FakeSelf:
    """Stands in for the operator. An Operator cannot be built outside Blender.

    Both methods are ordinary functions on the class and touch one attribute.
    """

    def __init__(self):
        self.cursor_hidden = False


def test_hide_is_idempotent():
    """A second grab without a release must not double the hidden state.

    cursor_modal_restore is not a stack pop, so an unbalanced pair would be
    survivable - but the flag is what every teardown path consults, and one
    that could get out of step with the pointer is not worth having.
    """
    window = FakeWindow()
    operator = FakeSelf()
    context = FakeContext(window)

    unbound(EASYCROP_OT_crop._hide_cursor)(operator, context)
    unbound(EASYCROP_OT_crop._hide_cursor)(operator, context)

    check("hidden once", window.calls, [("set", 'NONE')])
    check("flag set", operator.cursor_hidden, True)


def test_restore_warps_then_shows():
    """The warp has to happen while the pointer is still hidden.

    Restoring first shows the pointer wherever the drag left it and then moves
    it, which is the visible jump this is meant to remove.
    """
    strip = make_strip()
    window = FakeWindow()
    operator = FakeSelf()
    operator.cursor_hidden = True
    context = FakeContext(window, FakeRegion(), bpy.context.scene)

    unbound(EASYCROP_OT_crop._restore_cursor)(operator, context, 0)

    check("warped, then restored", window.calls,
          [("warp", REGION_X, REGION_Y), ("restore",)])
    check("flag cleared", operator.cursor_hidden, False)


def test_restore_without_a_handle_still_shows_the_pointer():
    """finish() restores with -1: a session can end mid-drag, on ESC.

    There is nowhere sensible to warp to then - ESC has already put the crop
    back - but the pointer must reappear regardless.
    """
    window = FakeWindow()
    operator = FakeSelf()
    operator.cursor_hidden = True

    unbound(EASYCROP_OT_crop._restore_cursor)(operator, FakeContext(window), -1)

    check("restored without warping", window.calls, [("restore",)])


def test_restore_does_nothing_when_nothing_was_hidden():
    """finish() runs on every path, including ones where no drag ever started."""
    window = FakeWindow()
    operator = FakeSelf()

    unbound(EASYCROP_OT_crop._restore_cursor)(operator, FakeContext(window), 0)

    check("no cursor calls", window.calls, [])


def test_every_exit_from_a_drag_restores_the_pointer():
    """A missed restore costs the session its pointer, not just the crop.

    Source inspection, because the paths out of a modal cannot be driven from a
    script. The ordering assertion is the one with teeth: active_corner is the
    warp's only record of which handle the drag was on, so clearing it first
    silently downgrades every release to a bare restore.
    """
    modal_src = inspect.getsource(EASYCROP_OT_crop.modal)
    finish_src = inspect.getsource(EASYCROP_OT_crop.finish)

    check("finish() restores", "_restore_cursor" in finish_src, True)
    check("modal() hides on grab", "_hide_cursor" in modal_src, True)

    restore = modal_src.index("_restore_cursor")
    cleared = modal_src.index("self.active_corner = -1", restore - 400)
    check("restore precedes clearing active_corner", restore < cleared, True)


def test_the_gizmo_converts_its_handle_numbering():
    """handle_type/handle_index is the gizmo's own scheme, not the flat one."""
    warp_src = inspect.getsource(EASYCROP_GT_crop_handle._warp_cursor_to_handle)

    check("uses the shared helper", "handle_window_position" in warp_src, True)
    check("offsets edge handles by four", "+ 4" in warp_src, True)


def main():
    tests = [
        test_position_is_in_window_coordinates,
        test_position_is_clamped_to_the_region,
        test_indices_four_to_seven_are_the_edge_midpoints,
        test_position_follows_the_crop,
        test_missing_geometry_is_reported_not_guessed,
        test_hide_is_idempotent,
        test_restore_warps_then_shows,
        test_restore_without_a_handle_still_shows_the_pointer,
        test_restore_does_nothing_when_nothing_was_hidden,
        test_every_exit_from_a_drag_restores_the_pointer,
        test_the_gizmo_converts_its_handle_numbering,
    ]

    for test in tests:
        try:
            test()
        except Exception:
            failures.append(f"{test.__name__} raised:\n{traceback.format_exc()}")

    version = bpy.app.version_string
    if failures:
        print(f"CURSOR {version} FAIL")
        for failure in failures:
            print(f"  {failure}")
        sys.exit(1)

    print(f"CURSOR {version} PASS")


if __name__ == "__main__":
    main()
