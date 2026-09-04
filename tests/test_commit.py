"""
Auto-key and undo tests for the end of a crop drag.

Two things have to happen when a drag finishes: key the channels it moved if
auto-key is on, and leave an undo step behind. Both are easy to get wrong in
ways that stay silent - see ../BLENDER.md, "Auto-key never fires on a plain RNA
write" and "End-of-drag work belongs in exit(), not modal()".

A gizmo drag cannot be driven from a script (event_simulate is not enough -
draw_prepare/refresh never run, so the handles are never positioned), so the
commit logic is exercised directly and the *wiring* is asserted separately:
_commit must be reachable from exit() and must not be called from modal().

    "/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b \
        --factory-startup --python tests/test_commit.py
"""

import inspect
import sys
import traceback
from pathlib import Path

import bpy

WORKSPACE = str(Path(__file__).resolve().parents[2])
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)

from BL_EasyCrop.gizmos.crop_handles_gizmo import EASYCROP_GT_crop_handle  # noqa: E402
from BL_EasyCrop.operators.crop_core import (  # noqa: E402
    autokey_crop, crop_props_for_handle, map_handle)

WIDTH, HEIGHT = 1920, 1080
CORNER_BL, CORNER_TR, EDGE_LEFT, EDGE_TOP = 0, 2, 4, 5

failures = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}: expected {want}, got {got}")


def make_strip():
    scene = bpy.context.scene
    scene.render.resolution_x = WIDTH
    scene.render.resolution_y = HEIGHT
    if scene.sequence_editor:
        scene.sequence_editor_clear()
    editor = scene.sequence_editor_create()
    strips = editor.strips if hasattr(editor, "strips") else editor.sequences
    try:
        strip = strips.new_effect(name="commit_test", type='COLOR',
                                  channel=1, frame_start=1, frame_end=50)
    except TypeError:
        strip = strips.new_effect(name="commit_test", type='COLOR',
                                  channel=1, frame_start=1, length=50)
    strip.crop.min_x = strip.crop.max_x = 0
    strip.crop.min_y = strip.crop.max_y = 0
    return strip


def keyed_channels():
    """Which crop channels currently have fcurves on the scene's action.

    Action.fcurves stopped existing in 4.4 - curves moved into a per-slot
    channelbag, action.layers[i].strips[j].channelbags[k].fcurves. Every
    Blender this addon supports is past that, but the legacy attribute is
    still worth falling back to for actions loaded out of older files.
    See ../BLENDER.md -> "Slotted actions changed fcurve access in 4.4".
    """
    anim = bpy.context.scene.animation_data
    action = getattr(anim, "action", None) if anim else None
    if action is None:
        return set()

    if hasattr(action, "fcurves"):
        curves = list(action.fcurves)
    else:
        curves = [curve
                  for layer in action.layers
                  for strip in layer.strips
                  for bag in strip.channelbags
                  for curve in bag.fcurves]

    return {curve.data_path.rsplit(".", 1)[-1] for curve in curves
            if ".crop." in curve.data_path}


# --- which channels a handle owns -------------------------------------------

def test_a_corner_owns_two_channels_an_edge_one():
    check("corner BL channels", crop_props_for_handle(CORNER_BL, False, False),
          ("min_x", "min_y"))
    check("corner TR channels", crop_props_for_handle(CORNER_TR, False, False),
          ("max_x", "max_y"))
    check("edge left channels", crop_props_for_handle(EDGE_LEFT, False, False),
          ("min_x",))
    check("edge top channels", crop_props_for_handle(EDGE_TOP, False, False),
          ("max_y",))


def test_flips_move_which_channel_a_handle_owns():
    """The handle drawn on the left of a mirrored strip drives max_x."""
    check("edge left, flip_x", crop_props_for_handle(EDGE_LEFT, True, False),
          ("max_x",))
    check("edge left, flip_y", crop_props_for_handle(EDGE_LEFT, False, True),
          ("min_x",))
    check("corner BL, flip both", crop_props_for_handle(CORNER_BL, True, True),
          ("max_x", "max_y"))
    # map_handle is the single place flips are resolved; identity when unflipped.
    check("map_handle is identity unflipped",
          tuple(map_handle(i, False, False) for i in range(8)),
          tuple(range(8)))


# --- auto-key ---------------------------------------------------------------

def test_autokey_off_inserts_nothing():
    strip = make_strip()
    bpy.context.tool_settings.use_keyframe_insert_auto = False
    strip.crop.min_x = 120
    keyed = autokey_crop(bpy.context, strip, EDGE_LEFT, False, False)
    check("autokey off: nothing reported", keyed, ())
    check("autokey off: no fcurves", keyed_channels(), set())


def test_autokey_keys_only_what_moved():
    """Keying all four channels is the tempting answer and the wrong one."""
    strip = make_strip()
    bpy.context.tool_settings.use_keyframe_insert_auto = True
    strip.crop.min_x = 120
    strip.crop.min_y = 60
    keyed = autokey_crop(bpy.context, strip, CORNER_BL, False, False)
    check("autokey on: reported channels", keyed, ("min_x", "min_y"))
    check("autokey on: only those channels keyed", keyed_channels(),
          {"min_x", "min_y"})
    bpy.context.tool_settings.use_keyframe_insert_auto = False


def test_autokey_reads_the_context_tool_settings():
    """The flag must come from context, not from a scene looked up by hand.

    tool_settings is per-scene and the UI writes the window scene's copy, so a
    second scene's copy can disagree. Reading the wrong one fails silently.
    """
    strip = make_strip()
    other = bpy.data.scenes.new("other_scene")
    other.tool_settings.use_keyframe_insert_auto = True
    bpy.context.tool_settings.use_keyframe_insert_auto = False
    check("the two scenes disagree",
          other.tool_settings.use_keyframe_insert_auto
          != bpy.context.tool_settings.use_keyframe_insert_auto, True)

    strip.crop.min_x = 90
    keyed = autokey_crop(bpy.context, strip, EDGE_LEFT, False, False)
    check("follows context, not the other scene", keyed, ())
    bpy.data.scenes.remove(other)


# --- wiring -----------------------------------------------------------------

def test_commit_is_called_from_exit_and_not_from_modal():
    """Blender does not reliably hand modal() the confirming mouse release."""
    exit_src = inspect.getsource(EASYCROP_GT_crop_handle.exit)
    modal_src = inspect.getsource(EASYCROP_GT_crop_handle.modal)
    commit_src = inspect.getsource(EASYCROP_GT_crop_handle._commit)
    check("exit() calls _commit", "_commit" in exit_src, True)
    check("modal() does not call _commit", "_commit" in modal_src, False)
    check("_commit pushes undo", "undo_push" in commit_src, True)
    check("_commit auto-keys", "autokey_crop" in commit_src, True)


def test_undo_push_actually_restores_a_crop():
    """Undo is driveable in background mode, so this is a real round trip.

    Runs first, and deliberately so: undo restores whole-file state, so a test
    that has already rebuilt the sequence editor a few times leaves the stack
    holding older editors and an undo lands somewhere unrelated. This is a
    property of the fixture, not of the addon.
    """
    strip = make_strip()
    name = strip.name
    bpy.ops.ed.undo_push(message="before crop")

    def min_x():
        editor = bpy.context.scene.sequence_editor
        strips = editor.strips if hasattr(editor, "strips") else editor.sequences
        return strips[name].crop.min_x

    baseline = min_x()
    strip.crop.min_x = 400
    bpy.ops.ed.undo_push(message="Crop")
    check("the edit landed", min_x(), 400)

    bpy.ops.ed.undo()
    check("undo restored the crop", min_x(), baseline)


TESTS = (
    # Undo restores whole-file state, so it has to run before the fixture has
    # rebuilt the sequence editor for other tests. See its docstring.
    test_undo_push_actually_restores_a_crop,
    test_a_corner_owns_two_channels_an_edge_one,
    test_flips_move_which_channel_a_handle_owns,
    test_autokey_off_inserts_nothing,
    test_autokey_keys_only_what_moved,
    test_autokey_reads_the_context_tool_settings,
    test_commit_is_called_from_exit_and_not_from_modal,
)


def main():
    version = bpy.app.version_string
    for test in TESTS:
        try:
            test()
        except Exception as exc:
            failures.append(f"{test.__name__} raised {type(exc).__name__}: {exc}")

    if failures:
        print(f"COMMIT {version} FAIL")
        for line in failures:
            print(f"  - {line}")
        return 1
    print(f"COMMIT {version} PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print(f"COMMIT {bpy.app.version_string} ERROR")
        traceback.print_exc()
        sys.exit(1)
