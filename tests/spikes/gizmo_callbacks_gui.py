"""
Settle REFACTOR.md R1's remaining suspects, plus R4 and R7, in a real UI.

    "/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" \
        --factory-startup --python <this file> -- [hold]

No --background. Default mode arms a quit timer and answers everything a
redraw alone can settle; "hold" leaves the window open so a hand on the mouse
can settle the ones that need a click.

Questions:
  R1a Gizmo.draw_prepare    - fires on every redraw if it is a callback here
  R1b Gizmo.draw_select     - a real RNA callback, but does it fire for us
  R1c Gizmo.select          - needs a click; not in Gizmo.bl_rna.functions
  R4  duplicate use_* flags  - does Gizmo.setup() fire, so that the group's
                               rewrites are redundant
  R7  color / alpha props    - inert against an overridden draw()? Two
                               screenshots, the second with the palette wrecked.

Controls: draw() and the group's refresh() certainly fire. A print that stays
silent proves nothing unless a print you know fires appears in the same run.
"""

# A spike, not shipped code, and these three are inherent to what it does
# rather than defects in it. Suppressed per file: turning any of them down in
# pyrightconfig.json would blind the shipped code too, which is the mistake
# BLENDER.md -> Type checking records under "a rule turned down to survive its
# own noise is not a rule".
#
#   reportAttributeAccessIssue - the spike replaces methods on registered RNA
#     classes, which is the entire technique
#   reportCallIssue - _original() returns either a real method or a *args
#     stand-in, so no single signature describes it
#   reportGeneralTypeIssues - the stubs' ContextTempOverride implements neither
#     __enter__ nor __exit__, though `with bpy.context.temp_override(...)` is
#     the documented usage
# pyright: reportAttributeAccessIssue=false, reportCallIssue=false
# pyright: reportGeneralTypeIssues=false


import atexit
import sys
from pathlib import Path

import bpy

WORKSPACE = str(Path(__file__).resolve().parents[3])
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)

# Everything after "--" is ours. Blender's own cwd is wherever it was
# launched from, so never fall back to it silently - a missing directory
# scatters screenshots across the workspace.
_ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
HOLD = "hold" in _ARGS
_DIRS = [a for a in _ARGS if a != "hold"]
if not _DIRS:
    raise SystemExit("usage: ... --python <this> -- <output dir> [hold]")
OUT = Path(_DIRS[0])

bpy.context.preferences.view.show_splash = False

import BL_EasyCrop as addon                                   # noqa: E402
from BL_EasyCrop.gizmos.crop_handles_gizmo import (           # noqa: E402
    EASYCROP_GT_crop_handle as GT,
    EASYCROP_GGT_crop_handles as GGT,
)

CALLS = {}
FLAG_LOG = []
SETUP_LOG = []
WRECK = {"on": False}


def _count(name):
    CALLS[name] = CALLS.get(name, 0) + 1
    if CALLS[name] == 1:
        print("[FIRST] " + name)
        sys.stdout.flush()


ABSENT = []


def _original(cls, name):
    """The class's own method, or a no-op stand-in if it defines none.

    A suspect that has since been deleted must not stop the spike loading -
    the three this was written for are all gone now. The counter stays in the
    report, where a permanent 0 is the right answer, and ABSENT says which
    zeros mean "not defined" rather than "defined and never called".

    WARNING: vars() and not getattr(). An undefined name can still resolve on
    the base class, and Gizmo.select resolves to an RNA *property* that would
    raise the moment a wrapper tried to call it - which is the whole reason
    that method was suspect in the first place.
    """
    own = vars(cls).get(name)
    if own is not None:
        return own
    ABSENT.append(cls.__name__ + "." + name)
    return lambda self, *args: None


def instrument():
    """Wrap every suspect and every control, before register_class sees them."""
    gt_setup = _original(GT, "setup")
    gt_draw = _original(GT, "draw")
    gt_prep = _original(GT, "draw_prepare")
    gt_dsel = _original(GT, "draw_select")
    gt_test = _original(GT, "test_select")
    gt_sel = _original(GT, "select")
    gt_invoke = _original(GT, "invoke")
    gt_modal = _original(GT, "modal")
    gt_exit = _original(GT, "exit")

    def setup(self):
        _count("Gizmo.setup")
        before = (self.use_event_handle_all, self.use_draw_modal,
                  self.use_grab_cursor)
        result = gt_setup(self)
        after = (self.use_event_handle_all, self.use_draw_modal,
                 self.use_grab_cursor)
        SETUP_LOG.append((before, after))
        return result

    def draw(self, context):
        _count("Gizmo.draw")
        return gt_draw(self, context)

    def draw_prepare(self, context):
        _count("Gizmo.draw_prepare")
        return gt_prep(self, context)

    def draw_select(self, context, select_id):
        _count("Gizmo.draw_select")
        return gt_dsel(self, context, select_id)

    def test_select(self, context, event):
        _count("Gizmo.test_select")
        return gt_test(self, context, event)

    def select(self, context, event):
        _count("Gizmo.select")
        return gt_sel(self, context, event)

    def invoke(self, context, event):
        _count("Gizmo.invoke")
        return gt_invoke(self, context, event)

    def modal(self, context, event, tweak):
        _count("Gizmo.modal")
        return gt_modal(self, context, event, tweak)

    def exit(self, context, cancel):
        _count("Gizmo.exit")
        return gt_exit(self, context, cancel)

    GT.setup, GT.draw = setup, draw
    GT.draw_prepare, GT.draw_select = draw_prepare, draw_select
    GT.test_select, GT.select = test_select, select
    GT.invoke, GT.modal, GT.exit = invoke, modal, exit

    ggt_poll = GGT.poll.__func__
    ggt_setup, ggt_refresh = GGT.setup, GGT.refresh
    ggt_prep = GGT.draw_prepare

    def poll(cls, context):
        _count("Group.poll")
        return ggt_poll(cls, context)

    def group_setup(self, context):
        _count("Group.setup")
        result = ggt_setup(self, context)
        # R4: read the flags back straight after the group wrote them. What
        # matters is whether Gizmo.setup() ran first and had already set them.
        for i, giz in enumerate(self.gizmos):
            FLAG_LOG.append((i, giz.handle_type,
                             giz.use_event_handle_all, giz.use_draw_modal,
                             giz.use_grab_cursor, giz.use_select_background,
                             tuple(round(c, 3) for c in giz.color),
                             round(giz.alpha, 3), round(giz.scale_basis, 3)))
        return result

    def refresh(self, context):
        _count("Group.refresh")
        result = ggt_refresh(self, context)
        if WRECK["on"]:
            # R7. refresh() is a known-live callback and owns the gizmo list,
            # so it is the honest place to stamp the palette from.
            for giz in self.gizmos:
                giz.color = (1.0, 0.0, 0.0)
                giz.color_highlight = (1.0, 0.0, 0.0)
                giz.alpha = 0.02
                giz.alpha_highlight = 0.02
        return result

    def group_draw_prepare(self, context):
        _count("Group.draw_prepare")
        return ggt_prep(self, context)

    GGT.poll = classmethod(poll)
    GGT.setup, GGT.refresh = group_setup, refresh
    GGT.draw_prepare = group_draw_prepare


instrument()
addon.register()

STATE = {"area": None, "region": None, "strip": None}


def build_scene():
    """A COLOR strip on a fresh sequence editor, selected and active."""
    scene = bpy.context.scene
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    editor = scene.sequence_editor_create()
    strips = editor.strips if hasattr(editor, "strips") else editor.sequences
    try:
        strip = strips.new_effect(name="crop_test", type='COLOR',
                                  channel=1, frame_start=1, frame_end=50)
    except TypeError:
        # new_effect(frame_end=...) became new_effect(length=...) in 5.1.
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
    STATE["strip"] = strip

    # 5.0 decoupled the sequencer scene from the window scene, and a screen
    # assembled by script has it unset - the preview renders black and nothing
    # in the VSE resolves. See BLENDER.md -> Strip settings live in the
    # Properties editor, gated on sequencer_scene.
    workspace = bpy.context.window.workspace
    if hasattr(workspace, "sequencer_scene"):
        workspace.sequencer_scene = scene

    area = max(bpy.context.window.screen.areas, key=lambda a: a.width * a.height)
    area.type = 'SEQUENCE_EDITOR'
    STATE["area"] = area
    return 1.0


def make_preview():
    """Second step: the area has been drawn once, so it accepts configuration."""
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
    print("[setup] region {0} {1}x{2} at ({3},{4})".format(
        region.type, region.width, region.height, region.x, region.y))
    with bpy.context.temp_override(window=bpy.context.window,
                                   area=area, region=region):
        bpy.ops.wm.tool_set_by_id(name="sequencer.crop_handles_tool")
        # Diagnostics, so a run of zeros can be told from a run that never
        # reached the gizmos at all.
        ctx = bpy.context
        registered = bpy.types.GizmoGroup.bl_rna_get_subclass_py(GGT.bl_idname)
        print("[diag] registered class is the patched one: "
              + str(registered is GGT))
        print("[diag] show_gizmo={0} view_type={1} display_mode={2}".format(
            area.spaces.active.show_gizmo, area.spaces.active.view_type,
            area.spaces.active.display_mode))
        print("[diag] active_strip={0} selected={1}".format(
            ctx.scene.sequence_editor.active_strip,
            getattr(ctx.scene.sequence_editor.active_strip, "select", None)))
        print("[diag] poll() called by hand: " + str(GGT.poll(ctx)))
        # That hand call went through the counter; take it back out so
        # the report only counts dispatches Blender made itself.
        CALLS["Group.poll"] = CALLS.get("Group.poll", 1) - 1
    area.tag_redraw()
    return 1.5


def report(label):
    print("\n===== " + label + " =====")
    if ABSENT:
        print("  (not defined by the addon, so 0 is not a measurement: "
              + ", ".join(ABSENT) + ")")
    for name in ("Group.poll", "Group.setup", "Group.refresh",
                 "Group.draw_prepare", "Gizmo.setup", "Gizmo.draw",
                 "Gizmo.draw_prepare", "Gizmo.draw_select",
                 "Gizmo.test_select", "Gizmo.select",
                 "Gizmo.invoke", "Gizmo.modal", "Gizmo.exit"):
        print("  {0:22} {1}".format(name, CALLS.get(name, 0)))
    sys.stdout.flush()


def shot(name):
    OUT.mkdir(parents=True, exist_ok=True)
    path = str(OUT / name)
    with bpy.context.temp_override(window=bpy.context.window,
                                   area=STATE["area"], region=STATE["region"]):
        bpy.ops.screen.screenshot_area(filepath=path)
    print("[shot] " + path)


def after_draw():
    report("after the handles have drawn (no input at all)")
    print("\n----- R4: (handle_all, draw_modal, grab) across Gizmo.setup() -----")
    for i, (before, after) in enumerate(SETUP_LOG):
        print("  gizmo {0:2}  before={1}  after={2}".format(i, before, after))
    print("\n----- R4: flags as the group's setup() left them -----")
    for row in FLAG_LOG:
        print("  gizmo {0} {1:7} handle_all={2} draw_modal={3} grab={4} "
              "sel_bg={5} color={6} alpha={7} scale={8}".format(*row))
    shot("baseline.png")
    return 1.0


def wreck_palette():
    print("\n----- R7: stamping color=(1,0,0) alpha=0.02 from refresh() -----")
    WRECK["on"] = True
    STATE["area"].tag_redraw()
    return 1.5


def shot_wrecked():
    shot("wrecked.png")
    return 1.0


def move_the_crop():
    """Control: the handles must visibly move, or the diff proves nothing."""
    print("\n----- control: widening the crop by 200px -----")
    STATE["strip"].crop.min_x += 200
    STATE["area"].tag_redraw()
    return 1.5


def shot_control():
    shot("control.png")
    return 1.0


def hover_a_handle():
    """Warp the OS pointer onto a corner handle to provoke a pick pass."""
    region = STATE["region"]
    x = region.x + region.width // 2
    y = region.y + region.height // 2
    print("\n[hover] warping to window ({0},{1}) - region centre".format(x, y))
    bpy.context.window.cursor_warp(x, y)
    STATE["area"].tag_redraw()
    return 1.5


def finish():
    report("after a pointer warp into the region")
    print("\nSEEN: " + ", ".join(sorted(k for k, v in CALLS.items() if v)))
    if HOLD:
        # Hand over a clean scene: the palette stamp is inert but confusing,
        # and the control left the crop lopsided.
        WRECK["on"] = False
        for field, value in (("min_x", 120), ("max_x", 120),
                             ("min_y", 80), ("max_y", 80)):
            setattr(STATE["strip"].crop, field, value)
        STATE["area"].tag_redraw()
        print("\n>>> HOLD: the window stays open.")
        print(">>>   1. hover a corner handle - it should light up orange")
        print(">>>   2. click and drag it, then release")
        print(">>>   3. close Blender")
        print(">>> Gizmo.invoke / modal / exit are the control: if they stay 0")
        print(">>> the drag never reached the gizmo and a silent select proves")
        print(">>> nothing. Every change is logged below as it happens.")
        sys.stdout.flush()

        seen = {"last": dict(CALLS)}

        def watch():
            if CALLS != seen["last"]:
                changed = ", ".join(
                    "{0}={1}".format(k, v) for k, v in sorted(CALLS.items())
                    if v != seen["last"].get(k, 0))
                print("[change] " + changed)
                sys.stdout.flush()
                seen["last"] = dict(CALLS)
            return 0.5

        bpy.app.timers.register(watch, first_interval=0.5, persistent=True)
        atexit.register(lambda: report("FINAL - after the hand-driven session"))
        return None
    def quit_now():
        bpy.ops.wm.quit_blender()
        return None

    bpy.app.timers.register(quit_now, first_interval=0.5)
    return None


def chain(*steps):
    """Run steps in order, each returning the gap before the next."""
    queue = list(steps)

    def tick():
        if not queue:
            return None
        gap = queue.pop(0)()
        if gap is None or not queue:
            return None
        return gap

    bpy.app.timers.register(tick, first_interval=1.5, persistent=True)


chain(build_scene, make_preview, activate_tool, after_draw,
      wreck_palette, shot_wrecked, move_the_crop, shot_control,
      hover_a_handle, finish)
