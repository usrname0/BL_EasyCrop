"""Settle the two questions error.blend raises, with a hand on the mouse.

    "/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
        --factory-startup <error.blend> --python <this file>

No --background, and no quit timer: the window stays open until you close it.

Q1  Does ONE Ctrl+Z undo a gizmo drag?
    _commit() calls ed.undo_push from exit(). tests/test_commit.py proves the
    push restores a crop when called from a script, and proves by source
    inspection that exit() reaches _commit - but nothing has ever measured a
    real drag followed by a real Ctrl+Z. If the gizmo tweak operator pushes a
    step of its own after ours, the first Ctrl+Z lands on an identical state
    and reads as "undo did nothing".

Q2  At a collapsed crop, which handle does a click actually take?
    On error.blend the nine handles occupy three points 0-2px apart. Each
    stack holds one handle that can widen the crop (max_x) and one that
    cannot (min_x, pinned at 0 with a limit of 0). Scripted cursor_warp
    cannot answer this - an unfocused window produces no pick pass, and the
    highlight then read back is stale.

Every crop change is printed as it happens, tagged with what caused it.
"""
# pyright: reportAttributeAccessIssue=false, reportCallIssue=false

import atexit
import sys
from pathlib import Path

import bpy

WORKSPACE = r"D:\Dev\Blender_Dev"
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)

bpy.context.preferences.view.show_splash = False

import BL_EasyCrop as addon                                        # noqa: E402
from BL_EasyCrop.gizmos.crop_handles_gizmo import (                # noqa: E402
    EASYCROP_GT_crop_handle as GT, EASYCROP_GGT_crop_handles as GGT)

NAMES = {("corner", 0): "corner BL", ("corner", 1): "corner TL",
         ("corner", 2): "corner TR", ("corner", 3): "corner BR",
         ("edge", 0): "edge L", ("edge", 1): "edge T",
         ("edge", 2): "edge R", ("edge", 3): "edge B",
         ("center", 0): "centre"}

COLLAPSED = (0, 511, 115, 0)     # exactly as error.blend has it
CONTROL = (60, 60, 115, 40)      # a normal crop, for the Ctrl+Z control

LOG = {"tag": "startup", "last": None}
STATE = {"strip": None, "area": None}

_invoke, _exit, _commit = GT.invoke, GT.exit, GT._commit
_refresh = GGT.refresh


def _name(self):
    return NAMES.get((self.handle_type, self.handle_index), "?")


def _crop():
    c = STATE["strip"].crop
    return (c.min_x, c.max_x, c.min_y, c.max_y)


def say(msg):
    print(msg)
    sys.stdout.flush()


def invoke(self, context, event):
    LOG["tag"] = "DRAG on " + _name(self)
    say("\n>>> GRABBED: %s   crop before = %s" % (_name(self), _crop()))
    say("    (min_x is index 0, max_x index 1. Only a max_x handle - "
        "corner TR, corner BR or edge R - can widen this crop.)")
    return _invoke(self, context, event)


def commit(self, context):
    say("    _commit() running: undo_push about to fire")
    return _commit(self, context)


def exit_(self, context, cancel):
    result = _exit(self, context, cancel)
    if self.handle_type != "center":
        say("<<< RELEASED: %s   crop after = %s   (cancel=%s)"
            % (_name(self), _crop(), cancel))
        say("    Now press Ctrl+Z ONCE, with the pointer over the preview.")
        LOG["tag"] = "after Ctrl+Z"
    return result


def refresh(self, context):
    STATE["area"] = context.area
    return _refresh(self, context)


GT.invoke, GT.exit, GT._commit = invoke, exit_, commit
GGT.refresh = refresh
addon.register()

scene = bpy.context.scene
editor = scene.sequence_editor
strip = editor.active_strip or (editor.strips_all
                                if hasattr(editor, "strips_all")
                                else editor.sequences_all)[0]
strip.select = True
editor.active_strip = strip
STATE["strip"] = strip
scene.frame_current = max(scene.frame_current, strip.frame_final_start)
ws = bpy.context.window.workspace
if hasattr(ws, "sequencer_scene"):
    ws.sequencer_scene = scene


def set_crop(values):
    strip.crop.min_x, strip.crop.max_x, strip.crop.min_y, strip.crop.max_y = values


def step_area():
    area = max(bpy.context.window.screen.areas, key=lambda a: a.width * a.height)
    area.type = 'SEQUENCE_EDITOR'
    STATE["area"] = area
    return 1.0


def step_preview():
    sp = STATE["area"].spaces.active
    sp.view_type = 'PREVIEW'
    sp.display_mode = 'IMAGE'
    STATE["area"].tag_redraw()
    return 1.0


def step_tool():
    area = STATE["area"]
    region = next((r for r in area.regions if r.type == 'PREVIEW'), None)
    if region is None:
        region = next(r for r in area.regions if r.type == 'WINDOW')
    with bpy.context.temp_override(window=bpy.context.window, area=area,
                                   region=region):
        bpy.ops.wm.tool_set_by_id(name="sequencer.crop_handles_tool")
        bpy.ops.sequencer.view_all_preview()
    set_crop(CONTROL)
    bpy.ops.ed.undo_push(message="spike baseline")
    area.tag_redraw()
    LOG["last"] = _crop()

    say("")
    say("=" * 72)
    say("PART 1 - does one Ctrl+Z undo a gizmo drag?")
    say("=" * 72)
    say("The crop is set to a normal %s so there is room to drag." % (CONTROL,))
    say("  1. drag any handle a visible distance, and release")
    say("  2. press Ctrl+Z ONCE, pointer over the preview")
    say("  3. read the log: the crop should go back to what it was at GRABBED")
    say("")
    say("When you are done, run  part2()  in Blender's Python console,")
    say("or just close the window.")
    say("")

    def part2():
        set_crop(COLLAPSED)
        bpy.ops.ed.undo_push(message="spike collapsed")
        STATE["area"].tag_redraw()
        LOG["tag"] = "part 2"
        say("")
        say("=" * 72)
        say("PART 2 - which handle does a click take at the collapsed crop?")
        say("=" * 72)
        say("Crop is now %s, exactly as error.blend has it." % (COLLAPSED,))
        say("Aim at each of the three visible squares and drag RIGHT.")
        say("GRABBED tells you which handle you actually got.")
        say("Recovery needs corner TR, corner BR or edge R.")
        say("")

    import builtins
    builtins.part2 = part2
    return None


def watch():
    now = _crop()
    if now != LOG["last"]:
        say("    [crop] %s -> %s   (%s)" % (LOG["last"], now, LOG["tag"]))
        LOG["last"] = now
    return 0.15


_steps = [step_area, step_preview, step_tool]


def driver():
    fn = _steps.pop(0)
    gap = fn()
    if _steps:
        bpy.app.timers.register(driver, first_interval=gap or 1.0)
    else:
        bpy.app.timers.register(watch, first_interval=0.2, persistent=True)
    return None


bpy.app.timers.register(driver, first_interval=2.0)
atexit.register(lambda: say("\n[spike] window closed"))
