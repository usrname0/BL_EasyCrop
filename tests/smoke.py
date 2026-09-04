"""
Headless register/unregister smoke test for BL Easy Crop.

The cheap check that BLENDER.md -> Registration recommends: import the package,
register it, assert the operators, gizmos, keymaps and tool actually exist, then
unregister and assert they are gone again. It is what catches a broken import or
a failed class registration, which used to present as the tool silently not
appearing in the toolbar.

Run against one Blender:

    "/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b \
        --factory-startup --python tests/smoke.py

or across all installed versions with tests/run.py.
"""

import sys
import traceback
from pathlib import Path

import bpy

# The addon uses relative imports, so it has to be imported as a package: put
# the workspace root on the path and import the project folder by name.
WORKSPACE = str(Path(__file__).resolve().parents[2])
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)

import BL_EasyCrop as addon  # noqa: E402

GGT_NAME = "EASYCROP_GGT_crop_handles"
GT_NAME = "EASYCROP_GT_crop_handle"
TOOL_IDNAME = "sequencer.crop_handles_tool"

# Blender derives an operator's bpy.types name from its bl_idname, not from the
# Python class name, so EASYCROP_OT_crop registers as SEQUENCER_OT_crop.
OPERATOR_TYPES = ("SEQUENCER_OT_crop", "SEQUENCER_OT_clear_crop")


def operators_registered():
    """Which of the addon's operators are actually registered.

    WARNING: do not test this with hasattr(bpy.ops.sequencer, "crop").
    bpy.ops submodules fabricate attributes on access - hasattr is True for any
    name at all, including one nothing has ever registered, and only the call
    raises AttributeError. An operator check written that way passes against a
    completely dead addon.
    """
    return tuple(hasattr(bpy.types, name) for name in OPERATOR_TYPES)


def gizmos_registered():
    """Return (group, handle) registration flags.

    Gizmo subclasses never appear as `bpy.types.<name>` attributes the way
    operators do - see BLENDER.md -> Gizmos. Ask the RNA registry instead.
    """
    return (bpy.types.GizmoGroup.bl_rna_get_subclass_py(GGT_NAME) is not None,
            bpy.types.Gizmo.bl_rna_get_subclass_py(GT_NAME) is not None)


def tool_registered():
    """Whether the WorkSpaceTool subclass is present."""
    return any(getattr(t, "bl_idname", None) == TOOL_IDNAME
               for t in bpy.types.WorkSpaceTool.__subclasses__())


def main():
    version = bpy.app.version_string
    failures = []

    def check(label, got, want=True):
        if got != want:
            failures.append(f"{label}: expected {want}, got {got}")

    # Nothing should be registered yet; if these pass before register() the
    # assertions are not testing anything.
    for name, present in zip(OPERATOR_TYPES, operators_registered()):
        check(f"{name} absent before register", present, False)

    addon.register()

    for name, present in zip(OPERATOR_TYPES, operators_registered()):
        check(f"{name} registered", present)
    group, handle = gizmos_registered()
    check("gizmo group registered", group)
    check("gizmo handle registered", handle)
    check("toolbar tool registered", tool_registered())
    check("two keymap items", len(addon.addon_keymaps), 2)

    addon.unregister()

    for name, present in zip(OPERATOR_TYPES, operators_registered()):
        check(f"{name} unregistered", present, False)
    group, handle = gizmos_registered()
    check("gizmo group unregistered", group, False)
    check("gizmo handle unregistered", handle, False)
    check("keymaps cleared", len(addon.addon_keymaps), 0)

    if failures:
        print(f"SMOKE {version} FAIL")
        for line in failures:
            print(f"  - {line}")
        return 1

    print(f"SMOKE {version} PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print(f"SMOKE {bpy.app.version_string} ERROR")
        traceback.print_exc()
        sys.exit(1)
