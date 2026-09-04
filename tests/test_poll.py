"""
poll() must answer, not raise, when the context has no strip selection.

Both operators gate on context.scene.sequence_editor and then iterate
get_selected_strips(context). selected_strips is a *context member*, not a
property on the scene: outside a sequencer area it is None even with a
sequence_editor present, and iterating None raises TypeError from inside poll.

Measured 2026-09-04, before the fix, with a sequence_editor created and no VSE
area in the context:

    4.4.3   selected_strips == []    poll() -> False
    4.5.3   selected_strips == []    poll() -> False
    5.0.1   selected_strips is None  poll() raises TypeError
    5.1.2   selected_strips is None  poll() raises TypeError
    5.2.1   selected_strips is None  poll() raises TypeError

So this was a real 5.x defect on both entry points, not a type checker's
opinion - it is what reportOptionalIterable was pointing at while it sat
demoted to "information". get_selected_strips now returns () instead of None.

Asserted on poll() rather than on the helper on purpose: a green test on
get_selected_strips says nothing about whether the callers survive what it
returns, which is exactly how this got in.

    "/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b \
        --factory-startup --python tests/test_poll.py
"""

import sys
import traceback
from pathlib import Path

import bpy

WORKSPACE = str(Path(__file__).resolve().parents[2])
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)

from BL_EasyCrop import EASYCROP_OT_clear_crop  # noqa: E402
from BL_EasyCrop.operators.crop_core import get_selected_strips  # noqa: E402
from BL_EasyCrop.operators.crop_operators import EASYCROP_OT_crop  # noqa: E402

OPERATORS = (EASYCROP_OT_clear_crop, EASYCROP_OT_crop)

failures = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}: expected {want}, got {got}")


def test_poll_answers_without_a_selection():
    """The defect itself: poll() raised TypeError on 5.x instead of saying no."""
    bpy.context.scene.sequence_editor_create()

    for operator in OPERATORS:
        try:
            answer = operator.poll(bpy.context)
        except Exception as exc:
            failures.append(
                f"{operator.__name__}.poll() raised {type(exc).__name__}: {exc}")
            continue
        check(f"{operator.__name__}.poll() declines", answer, False)


def test_poll_answers_with_no_sequence_editor_at_all():
    """The other end of the same path, and the one 4.4 always survived."""
    scene = bpy.context.scene
    if scene.sequence_editor:
        scene.sequence_editor_clear()

    for operator in OPERATORS:
        try:
            answer = operator.poll(bpy.context)
        except Exception as exc:
            failures.append(
                f"{operator.__name__}.poll() raised {type(exc).__name__}: {exc}")
            continue
        check(f"{operator.__name__}.poll() declines", answer, False)


def test_selection_helper_is_always_iterable():
    """What poll() relies on, pinned separately so a regression says which half.

    This is the helper test that on its own would have proved nothing - see the
    module docstring. It earns its place only next to the two above.
    """
    bpy.context.scene.sequence_editor_create()
    strips = get_selected_strips(bpy.context)

    check("never None", strips is None, False)
    try:
        count = len(list(strips))
    except TypeError as exc:
        failures.append(f"not iterable: {exc}")
        return
    check("empty with nothing selected", count, 0)


TESTS = (
    test_poll_answers_without_a_selection,
    test_poll_answers_with_no_sequence_editor_at_all,
    test_selection_helper_is_always_iterable,
)


def main():
    version = bpy.app.version_string
    for test in TESTS:
        try:
            test()
        except Exception as exc:
            failures.append(f"{test.__name__} raised {type(exc).__name__}: {exc}")

    if failures:
        print(f"POLL {version} FAIL")
        for line in failures:
            print(f"  - {line}")
        return 1

    print(f"POLL {version} PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print(f"POLL {bpy.app.version_string} ERROR")
        traceback.print_exc()
        sys.exit(1)
