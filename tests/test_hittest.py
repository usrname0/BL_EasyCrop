"""
Click-through hit testing must only ever consider croppable strips.

The modal operator lets a click land on a different strip and switches to it.
That test walks every strip visible at the frame, and the geometry it walks them
with is get_strip_geometry_with_flip_support - which reads strip.transform.

A strip with no crop has no transform either, and the only strip type in that
position is SoundStrip. Given one, the geometry used to fall back to offset 0
and scale 1, which is the entire render rectangle, so point_in_polygon matched
a click anywhere in the preview. Sorted highest channel first, an audio strip
above the video strip therefore swallowed every click-through test: the user's
strip was deselected, the sound strip became active, and the crop ended - with
no error and nothing to report.

The other thing pinned here is that the modal operator's two hit tests agree.
It grabs a handle in crop_operators._get_corner_at_mouse and lights one up in
crop_drawing._get_hovered_corner, two hand-rolled tests Blender does not
coordinate - unlike the gizmo tool, where the highlight comes from the same
test_select that decides the grab. They disagreed on the radius (10 vs 15),
which left a ring where a handle was lit and a click missed it. Both now use
crop_core.SELECT_RADIUS and both take the nearest handle, not the first.

Which of these catch the old behaviour, checked by replaying them against it:

- croppable_only_reaches_the_hit_test    old returned both strips     - catches it
- geometry_refuses_a_strip_with_no_crop  old returned a full-frame rect
                                                                      - catches it
- hover_and_grab_agree                   old disagreed 10px-15px out  - catches it
- hover_and_grab_share_the_radius        old grabbed at 10px          - catches it
- nearest_handle_wins                    isolates the rule: with the radius
                                         already at 25 and first-match still in
                                         place, the contested click goes to the
                                         corner (1) instead of the midpoint (4)
- rotation_is_radians_from_transform     old and new agree         - regression guard

The last one does not demonstrate a fix. Keep it anyway: get_strip_rotation used
to try strip.rotation_start first and convert it with math.radians, so the day
any Blender or addon defines that name, every handle position and drag delta
goes out by a factor of 57.3 with nothing raising. The test pins the unit.

    "/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b \
        --factory-startup --python tests/test_hittest.py
"""

import struct
import sys
import tempfile
import traceback
import wave
from pathlib import Path
from typing import Any, cast

import bpy
from mathutils import Matrix, Vector

WORKSPACE = str(Path(__file__).resolve().parents[2])
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)

from BL_EasyCrop.gizmos.crop_handles_gizmo import EASYCROP_GT_crop_handle  # noqa: E402
from BL_EasyCrop.operators.crop_core import (  # noqa: E402
    get_strip_geometry_with_flip_support, get_strip_rotation, SELECT_RADIUS)
from BL_EasyCrop.operators.crop_drawing import _get_hovered_corner  # noqa: E402
from BL_EasyCrop.operators.crop_operators import EASYCROP_OT_crop  # noqa: E402

WIDTH, HEIGHT = 1920, 1080

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


def write_silent_wav():
    """A one-second mono WAV, so a real SoundStrip can be built headlessly."""
    path = Path(tempfile.mkdtemp(prefix="easycrop_")) / "silence.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(struct.pack("<8000h", *([0] * 8000)))
    return path


def make_scene():
    """A croppable COLOR strip on channel 1, a SoundStrip above it on 2.

    That is the ordinary layout for a movie imported with its audio, and it is
    the arrangement in which the defect bites: the sound strip sorts first.
    """
    scene = bpy.context.scene
    scene.render.resolution_x = WIDTH
    scene.render.resolution_y = HEIGHT
    scene.frame_current = 1

    if scene.sequence_editor:
        scene.sequence_editor_clear()
    editor = scene.sequence_editor_create()
    strips = editor.strips if hasattr(editor, "strips") else editor.sequences

    try:
        color = strips.new_effect(name="video", type='COLOR',
                                  channel=1, frame_start=1, frame_end=50)
    except TypeError:
        # new_effect(frame_end=...) became new_effect(length=...) in 5.1.
        color = strips.new_effect(name="video", type='COLOR',
                                  channel=1, frame_start=1, length=50)

    sound = strips.new_sound(name="audio", filepath=str(write_silent_wav()),
                             channel=2, frame_start=1)
    editor.active_strip = color
    return color, sound


def test_croppable_only_reaches_the_hit_test():
    """_get_visible_strips must not hand a sound strip to the hit test."""
    color, sound = make_scene()

    # self is unused, so the method can be driven without an operator instance.
    visible = unbound(EASYCROP_OT_crop._get_visible_strips)(None, bpy.context)
    names = [strip.name for strip in visible]

    check("sound strip excluded", sound.name in names, False)
    check("color strip included", color.name in names, True)


def test_geometry_refuses_a_strip_with_no_crop():
    """The geometry helper must raise, not invent a full-frame rectangle.

    Returning something plausible is what made the defect silent. Raising is
    what makes a future caller that forgets the filter fail loudly instead.
    """
    _, sound = make_scene()

    try:
        get_strip_geometry_with_flip_support(sound, bpy.context.scene)
    except AttributeError:
        return
    failures.append("geometry: a strip with no transform produced an outline "
                    "instead of raising")


def test_rotation_is_radians_from_transform():
    """strip.transform.rotation is radians and must be returned unconverted."""
    color, _ = make_scene()
    color.transform.rotation = 0.5

    check("rotation read back", round(get_strip_rotation(color), 6), 0.5)


class FakeEvent:
    """Only what _get_corner_at_mouse reads off an event."""

    def __init__(self, x, y):
        self.mouse_region_x = x
        self.mouse_region_y = y


class FakeOperator:
    """Stands in for self. _get_corner_at_mouse reads nothing else off it.

    An Operator subclass cannot be instantiated outside Blender's own
    invocation, but the method is an ordinary function on the class, so any
    object with the one attribute it uses will do.
    """

    def __init__(self, handles):
        self._handles = handles

    def _get_crop_corners(self, context):
        return self._handles[:4], self._handles[4:]


def grab_at(handles, x, y):
    """Drive _get_corner_at_mouse against a fixed set of handle positions."""
    return unbound(EASYCROP_OT_crop._get_corner_at_mouse)(
        FakeOperator(handles), None, FakeEvent(x, y))


def hover_at(handles, x, y):
    """Drive _get_hovered_corner against the same set."""
    return _get_hovered_corner(list(handles[:4]), list(handles[4:]), x, y)


def square_handles(left, bottom, right, top):
    """Corners BL, TL, TR, BR then the four edge midpoints, as Vectors."""
    corners = [Vector((left, bottom)), Vector((left, top)),
               Vector((right, top)), Vector((right, bottom))]
    midpoints = [(corners[i] + corners[(i + 1) % 4]) / 2 for i in range(4)]
    return corners + midpoints


def test_hover_and_grab_agree():
    """Whatever lights up is whatever a click grabs, everywhere on the rect.

    The 5px step matters. The two tests used to differ only between 10px and
    15px from a handle, so a coarser sweep steps straight over the ring where
    they disagreed and passes against the defect it exists to catch.
    """
    handles = square_handles(400, 300, 700, 600)

    disagreements = []
    for x in range(360, 741, 5):
        for y in range(260, 641, 5):
            if grab_at(handles, x, y) != hover_at(handles, x, y):
                disagreements.append((x, y))

    check("hover and grab disagree nowhere", disagreements[:3], [])


def test_hover_and_grab_share_the_radius():
    """Both must reach exactly SELECT_RADIUS, and neither further."""
    handles = square_handles(400, 300, 700, 600)
    inside = 400 - int(SELECT_RADIUS) + 1
    outside = 400 - int(SELECT_RADIUS) - 2

    check("grab just inside the radius", grab_at(handles, inside, 300), 0)
    check("hover just inside the radius", hover_at(handles, inside, 300), 0)
    check("grab just outside the radius", grab_at(handles, outside, 300), -1)
    check("hover just outside the radius", hover_at(handles, outside, 300), -1)


def test_nearest_handle_wins():
    """Where two handles contest a click, the closer one takes it.

    A crop rect shorter than four times SELECT_RADIUS puts an edge midpoint
    within reach of the corners either side of it. Corners are tested first, so
    taking the first match inside the radius hands every contested click to a
    corner however much nearer the midpoint is.
    """
    # 60px tall: the left edge midpoint sits at (500, 530), 30px from each of
    # the left-hand corners at (500, 500) and (500, 560).
    handles = square_handles(500, 500, 560, 560)

    # 10px from the midpoint, 20px from the top-left corner. Both are inside a
    # 25px radius, so the two rules give different answers here.
    check("contested click takes the nearer midpoint",
          grab_at(handles, 500, 540), 4)
    check("hover agrees on the contested click",
          hover_at(handles, 500, 540), 4)

    # Sitting exactly on a corner must still take the corner.
    check("on the top-left corner", grab_at(handles, 500, 560), 1)
    check("hover on the top-left corner", hover_at(handles, 500, 560), 1)


class FakeGizmo:
    """Stands in for a handle gizmo. test_select reads only matrix_basis."""

    def __init__(self, x, y):
        self.matrix_basis = Matrix.Translation((x, y, 0))


def test_gizmo_test_select_answers_hit_or_skip():
    """RNA calls the return intersect_id, and -1 is its only special value.

    It indexes a part *within* one gizmo, and these have one part each, so 0 is
    the whole vocabulary for a hit. Until 2026-09-04 each handle returned its
    own 0-8 id, which looked like it told Blender which handle was struck. It
    never did - Blender asks each gizmo separately, and invoke() reads
    handle_type/handle_index. The ids came from a `select_id` attribute that is
    not a Gizmo property at all, so nothing but this return ever read it.

    Pinned because the center handle returned 8, and any future edit that
    reintroduces a per-handle id puts an out-of-range part index back into
    Blender's hands for a gizmo that has one part.
    """
    gizmo = FakeGizmo(500, 500)
    call = unbound(EASYCROP_GT_crop_handle.test_select)

    check("dead centre is a hit", call(gizmo, None, (500, 500)), 0)
    check("just inside the radius is a hit",
          call(gizmo, None, (500 + int(SELECT_RADIUS) - 1, 500)), 0)
    check("well outside is a skip",
          call(gizmo, None, (500 + int(SELECT_RADIUS) * 3, 500)), -1)


def test_gizmo_hit_radius_matches_the_shared_constant():
    """The gizmo grabs at SELECT_RADIUS, the same number the modal pair uses."""
    gizmo = FakeGizmo(0, 0)
    call = unbound(EASYCROP_GT_crop_handle.test_select)

    inside = call(gizmo, None, (int(SELECT_RADIUS) - 1, 0))
    outside = call(gizmo, None, (int(SELECT_RADIUS) + 2, 0))
    check("inside the shared radius", inside, 0)
    check("outside the shared radius", outside, -1)


TESTS = (
    test_croppable_only_reaches_the_hit_test,
    test_gizmo_test_select_answers_hit_or_skip,
    test_gizmo_hit_radius_matches_the_shared_constant,
    test_geometry_refuses_a_strip_with_no_crop,
    test_hover_and_grab_agree,
    test_hover_and_grab_share_the_radius,
    test_nearest_handle_wins,
    test_rotation_is_radians_from_transform,
)


def main():
    version = bpy.app.version_string
    for test in TESTS:
        try:
            test()
        except Exception as exc:
            failures.append(f"{test.__name__} raised {type(exc).__name__}: {exc}")

    if failures:
        print(f"HITTEST {version} FAIL")
        for line in failures:
            print(f"  - {line}")
        return 1

    print(f"HITTEST {version} PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print(f"HITTEST {bpy.app.version_string} ERROR")
        traceback.print_exc()
        sys.exit(1)
