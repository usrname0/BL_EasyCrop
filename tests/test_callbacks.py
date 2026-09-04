"""
Every callback this addon defines must be one Blender will actually dispatch.

A method with a protocol-looking name on the wrong class is invisible dead
code. It reads as a callback, orphan scanning skips it because the name looks
like an override, and nothing will ever point at it. BL_EasyCrop carried three:

    EASYCROP_GGT_crop_handles.draw_select   a Gizmo callback on a GizmoGroup
    EASYCROP_GT_crop_handle.draw_prepare    a GizmoGroup callback on a Gizmo
    EASYCROP_GT_crop_handle.select          not a callback at all - RNA
                                            declares Gizmo.select a bool
                                            property, so the method shadowed it

All three were removed on 2026-09-04, the last two after a GUI session in which
they recorded zero calls while draw() ran 288 times, test_select 7394 times and
two hand-driven drags took invoke/modal/exit.

The check here is not a list of the three names. It is the rule they all broke:

    a public method on a registered class must appear in that class's own
    bl_rna.functions, and must not collide with one of its bl_rna properties

bl_rna.functions enumerates the callback set Blender dispatches, so a public
method missing from it can never fire, whatever it is called. Reading RNA at run
time rather than hardcoding the callback names means this stays true across
Blender versions instead of going stale - see BLENDER.md -> Which callbacks
belong to Gizmo and which to GizmoGroup.

Private helpers are exempt by their leading underscore: a name Blender was
never going to call is not claiming to be a callback.

Run against one Blender:

    "/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b \
        --factory-startup --python tests/test_callbacks.py

or across all installed versions with tests/run.py.
"""

import sys
import traceback
from pathlib import Path

import bpy

WORKSPACE = str(Path(__file__).resolve().parents[2])
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)

from BL_EasyCrop.gizmos.crop_handles_gizmo import (  # noqa: E402
    EASYCROP_GT_crop_handle, EASYCROP_GGT_crop_handles)

failures = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}: expected {want}, got {got}")


def public_methods(cls):
    """Callables the class itself defines, minus private helpers and bl_*.

    Only the class's own __dict__ - an inherited method is Blender's own and
    is not this addon claiming anything.
    """
    return sorted(
        name for name, value in vars(cls).items()
        if callable(value) or isinstance(value, (classmethod, staticmethod))
        if not name.startswith("_") and not name.startswith("bl_"))


def test_gizmo_defines_only_gizmo_callbacks():
    """Every public method on the handle must be in Gizmo.bl_rna.functions."""
    # bl_rna is typed BlenderRNA by the stubs and is a Struct at run time,
    # so .functions is real and only the stub disagrees.
    dispatched = set(bpy.types.Gizmo.bl_rna.functions.keys())  # pyright: ignore[reportAttributeAccessIssue]
    for name in public_methods(EASYCROP_GT_crop_handle):
        check(f"Gizmo.{name} is a callback Blender dispatches",
              name in dispatched, True)


def test_group_defines_only_group_callbacks():
    """Same rule on the group, which is where draw_select was hiding."""
    # bl_rna is typed BlenderRNA by the stubs and is a Struct at run time,
    # so .functions is real and only the stub disagrees.
    dispatched = set(bpy.types.GizmoGroup.bl_rna.functions.keys())  # pyright: ignore[reportAttributeAccessIssue]
    for name in public_methods(EASYCROP_GGT_crop_handles):
        check(f"GizmoGroup.{name} is a callback Blender dispatches",
              name in dispatched, True)


def test_no_method_shadows_an_rna_property():
    """The select / select_id shape: a method sitting on top of a property.

    Defining one does not make it a callback. It makes every Python read of
    that property return a bound method instead of its value, which is always
    truthy and never what the reader wanted.
    """
    for cls, base in ((EASYCROP_GT_crop_handle, bpy.types.Gizmo),
                      (EASYCROP_GGT_crop_handles, bpy.types.GizmoGroup)):
        properties = set(base.bl_rna.properties.keys())
        for name in public_methods(cls):
            check(f"{cls.__name__}.{name} shadows no RNA property",
                  name in properties, False)


def test_the_three_removed_names_stay_removed():
    """Named explicitly, because these are the ones that came back before.

    The rules above already cover them. This is the failure message that says
    which mistake was repeated, rather than leaving a reader to work out why
    a name is not in a list of RNA functions.
    """
    check("Gizmo.draw_prepare is gone (it is a GizmoGroup callback)",
          "draw_prepare" in vars(EASYCROP_GT_crop_handle), False)
    check("Gizmo.select is gone (RNA declares it a bool property)",
          "select" in vars(EASYCROP_GT_crop_handle), False)
    check("GizmoGroup.draw_select is gone (it is a Gizmo callback)",
          "draw_select" in vars(EASYCROP_GGT_crop_handles), False)

    # Gizmo.draw_select is real and Blender does dispatch it - it was removed
    # because it never fired for this group, not because it could not.
    check("Gizmo.draw_select is real on this Blender",
          "draw_select" in bpy.types.Gizmo.bl_rna.functions, True)  # pyright: ignore[reportAttributeAccessIssue]
    check("Gizmo.draw_select is gone (measured never to fire here)",
          "draw_select" in vars(EASYCROP_GT_crop_handle), False)
    check("_draw_handle_common went with its only caller",
          "_draw_handle_common" in vars(EASYCROP_GT_crop_handle), False)


TESTS = (
    test_gizmo_defines_only_gizmo_callbacks,
    test_group_defines_only_group_callbacks,
    test_no_method_shadows_an_rna_property,
    test_the_three_removed_names_stay_removed,
)


def main():
    version = bpy.app.version_string
    for test in TESTS:
        try:
            test()
        except Exception:
            failures.append(f"{test.__name__} raised:\n{traceback.format_exc()}")

    if failures:
        print(f"CALLBACKS {version} FAIL")
        for line in failures:
            print(f"  - {line}")
        return 1

    print(f"CALLBACKS {version} PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
