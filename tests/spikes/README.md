# Spikes

Not part of `tests/run.py`. These need a GUI, and one of them needs a hand on the
mouse, so neither can be a pass/fail check. They are kept because the questions
they answer come back, and because reviving one should start from the
measurement rather than from an argument.

`/tests/` is in the manifest's `paths_exclude_pattern`, so nothing here ships.

## `gizmo_callbacks_gui.py`

Counts every callback on both gizmo classes in a live session. Settled
`REFACTOR.md` R1, R4 and R7 on 2026-09-04.

    blender.exe --factory-startup --python tests/spikes/gizmo_callbacks_gui.py \
        -- <output dir> [hold]

Default mode arms a quit timer and answers everything a redraw alone can settle.
`hold` leaves the window open and logs each counter change as it happens, for the
questions that need a click or a drag.

Reach for it when a gizmo method's status is in doubt and
`bpy.types.Gizmo.bl_rna.functions` has not already settled it - **ask RNA first**,
on *both* classes. It proves a name dead in a minute; only a UI proves a live
name unused, and the three suspects here needed one screen between them.

Two things it exists to stop you getting wrong:

- **The controls matter more than the subject.** `Gizmo.draw`, `Group.refresh`
  and, for anything drag-gated, `invoke`/`modal`/`exit` all have to be loud in
  the same run. A silent callback in a run where nothing fired says nothing.
- **A screen assembled by script needs `workspace.sequencer_scene` set** on
  Blender 5.x, or the preview is black and the gizmo group is never polled -
  while the toolbar still draws with the tool correctly selected. That failure
  mode reads exactly like a broken addon.

## `compare_shot.py`

Shoots the crop handles from whichever copy of the addon it is pointed at, with
the pointer parked so hover state cannot differ between runs.

    blender.exe --factory-startup --python tests/spikes/compare_shot.py \
        -- <workspace root containing BL_EasyCrop> <out dir> <name>

Used to prove a change to drawing code changed nothing on screen, which nothing
headless can do. Get the "before" tree with `git archive HEAD | tar -x -C ...`,
shoot both, diff the PNGs. **Include a third shot with a palette constant
deliberately altered** and require it to be non-zero - otherwise a zero diff is
equally consistent with a stale screenshot. `../../BLENDER.md` -> *Comparing two
builds by screenshot* has the full method.
