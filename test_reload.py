"""
Quick test script to reload the addon and check gizmo functionality
"""

import bpy
import sys
import importlib

def reload_addon():
    """Reload the BL_EasyCrop addon"""
    
    # First disable the addon
    try:
        bpy.ops.preferences.addon_disable(module="BL_EasyCrop")
        print("✓ Disabled BL_EasyCrop addon")
    except Exception as e:
        print(f"⚠️ Failed to disable addon: {e}")
    
    # Clear any cached modules
    modules_to_remove = [name for name in sys.modules.keys() if name.startswith('BL_EasyCrop')]
    for module_name in modules_to_remove:
        if module_name in sys.modules:
            try:
                importlib.reload(sys.modules[module_name])
                print(f"✓ Reloaded {module_name}")
            except Exception as e:
                print(f"⚠️ Failed to reload {module_name}: {e}")
    
    # Re-enable the addon
    try:
        bpy.ops.preferences.addon_enable(module="BL_EasyCrop")
        print("✓ Enabled BL_EasyCrop addon")
        return True
    except Exception as e:
        print(f"❌ Failed to enable addon: {e}")
        return False

def test_gizmos():
    """Test if gizmos are available and working"""
    
    # Check if gizmo classes are registered
    gizmo_classes = [
        "EASYCROP_GT_crop_handle",
        "EASYCROP_GGT_crop_handles"
    ]
    
    for class_name in gizmo_classes:
        if hasattr(bpy.types, class_name):
            print(f"✓ {class_name} is registered")
        else:
            print(f"❌ {class_name} is NOT registered")
    
    # Check if tools are available
    try:
        workspace = bpy.context.workspace
        if workspace and hasattr(workspace, 'tools'):
            tool_found = False
            for tool in workspace.tools:
                if hasattr(tool, 'idname') and tool.idname == "sequencer.crop_handles_tool":
                    print(f"✓ Crop handles tool found: {tool.idname}")
                    tool_found = True
                    break
            if not tool_found:
                print("⚠️ Crop handles tool not found in workspace")
        else:
            print("⚠️ No workspace or tools available")
    except Exception as e:
        print(f"❌ Error checking tools: {e}")

if __name__ == "__main__":
    print("=== BL_EasyCrop Gizmo Test ===")
    
    if reload_addon():
        test_gizmos()
        print("=== Test Complete ===")
        print("Now try:")
        print("1. Select a video/image strip in VSE")
        print("2. Switch to Preview mode")
        print("3. Select the 'Crop Handles' tool from toolbar")
        print("4. You should see crop handles around the strip")
        print("5. Try dragging the handles to adjust crop")
    else:
        print("=== Test Failed - Addon Reload Error ===")