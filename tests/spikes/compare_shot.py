"""
Shoot the crop handles from a given copy of the addon, with everything that is
not the addon held still.

    blender.exe --factory-startup --python compare_shot.py \
        -- <workspace root containing BL_EasyCrop> <out dir> <name>

The pointer is parked in a fixed spot before the shot. Without that the centre
symbol draws ACCENT_COLOR or HANDLE_COLOR depending on where the mouse happens
to be, which is an 18x18 difference between two otherwise identical runs.
"""

# A spike, not shipped code. The stubs' ContextTempOverride implements neither
# __enter__ nor __exit__, though `with bpy.context.temp_override(...)` is the
# documented usage - a stub gap, suppressed per file rather than globally.
# pyright: reportGeneralTypeIssues=false


import sys
from pathlib import Path

import bpy

_ARGS = sys.argv[sys.argv.index("--") + 1:]
ROOT, OUT, NAME = _ARGS[0], Path(_ARGS[1]), _ARGS[2]
sys.path.insert(0, ROOT)

bpy.context.preferences.view.show_splash = False

import BL_EasyCrop as addon  # noqa: E402

print("[from] " + str(Path(addon.__file__).resolve()))
addon.register()

STATE = {}


def build_scene():
    scene = bpy.context.scene
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    editor = scene.sequence_editor_create()
    strips = editor.strips if hasattr(editor, "strips") else editor.sequences
    try:
        strip = strips.new_effect(name="crop_test", type='COLOR',
                                  channel=1, frame_start=1, frame_end=50)
    except TypeError:
        strip = strips.new_effect(name="crop_test", type='COLOR',
                                  channel=1, frame_start=1, length=50)
    strip.color = (0.15, 0.35, 0.75)
    strip.select = True
    editor.active_strip = strip
    scene.frame_current = 10
    strip.crop.min_x = 120
    strip.crop.max_x = 120
    strip.crop.min_y = 80
    strip.crop.max_y = 80

    workspace = bpy.context.window.workspace
    if hasattr(workspace, "sequencer_scene"):
        workspace.sequencer_scene = scene

    area = max(bpy.context.window.screen.areas, key=lambda a: a.width * a.height)
    area.type = 'SEQUENCE_EDITOR'
    STATE["area"] = area
    return 1.0


def make_preview():
    space = STATE["area"].spaces.active
    space.view_type = 'PREVIEW'
    space.display_mode = 'IMAGE'
    STATE["area"].tag_redraw()
    return 1.0


def activate_tool():
    area = STATE["area"]
    region = next((r for r in area.regions if r.type == 'PREVIEW'), None)
    if region is None:
        region = next(r for r in area.regions if r.type == 'WINDOW')
    STATE["region"] = region
    with bpy.context.temp_override(window=bpy.context.window,
                                   area=area, region=region):
        bpy.ops.wm.tool_set_by_id(name="sequencer.crop_handles_tool")
    area.tag_redraw()
    return 1.0


def park_pointer():
    """Low-left of the preview, clear of every handle by well over 25px."""
    region = STATE["region"]
    bpy.context.window.cursor_warp(region.x + 20, region.y + 20)
    STATE["area"].tag_redraw()
    return 1.5


def shoot():
    OUT.mkdir(parents=True, exist_ok=True)
    path = str(OUT / (NAME + ".png"))
    with bpy.context.temp_override(window=bpy.context.window,
                                   area=STATE["area"], region=STATE["region"]):
        bpy.ops.screen.screenshot_area(filepath=path)
    print("[shot] " + path)

    def quit_now():
        bpy.ops.wm.quit_blender()
        return None

    bpy.app.timers.register(quit_now, first_interval=0.5)
    return None


def chain(*steps):
    queue = list(steps)

    def tick():
        if not queue:
            return None
        gap = queue.pop(0)()
        if gap is None or not queue:
            return None
        return gap

    bpy.app.timers.register(tick, first_interval=1.5, persistent=True)


chain(build_scene, make_preview, activate_tool, park_pointer, shoot)
