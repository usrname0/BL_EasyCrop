"""
BL Easy Crop - Easy cropping tool for Blender's Video Sequence Editor

This addon provides an intuitive cropping interface for the VSE with visual handles
and real-time preview. It's adapted from VSE Transform Tools for Blender 4.4+.

Copyright (C) 2024 BL Easy Crop Contributors
License: GPL-3.0-or-later
"""

bl_info = {
    "name": "BL Easy Crop",
    "description": "Easy cropping tool for Blender's Video Sequence Editor",
    "author": "Adapted from VSE Transform Tools",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "Sequencer > Preview > Toolbar",
    "warning": "",
    "doc_url": "",
    "tracker_url": "",
    "category": "Sequencer"
}

import bpy
from bpy.types import Operator, Panel, Menu, WorkSpaceTool

# Import operators with better error reporting
try:
    from .operators.crop import (
        EASYCROP_OT_crop, 
        EASYCROP_OT_select_and_crop, 
        EASYCROP_OT_activate_tool, 
        is_strip_visible_at_frame,
        get_crop_state,
        set_crop_active,
        clear_crop_state
    )
    operators_imported = True
except ImportError as e:
    print(f"BL Easy Crop: Import error: {e}")
    EASYCROP_OT_crop = None
    EASYCROP_OT_select_and_crop = None
    EASYCROP_OT_activate_tool = None
    operators_imported = False


class EASYCROP_TOOL_crop(WorkSpaceTool):
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_context_mode = 'PREVIEW'
    
    bl_idname = "easycrop.crop_tool"
    bl_label = "Crop"
    bl_description = "Crop strips in the preview"
    bl_icon = "ops.sequencer.blade"  # Best available icon
    bl_widget = None
    
    # More specific keymap - only trigger on areas where it makes sense
    bl_keymap = (
        # Primary crop activation - only when we have a suitable context
        ("easycrop.select_and_crop", {"type": 'LEFTMOUSE', "value": 'PRESS'}, None),
    )
    
    @staticmethod  
    def draw_settings(context, layout, tool):
        # Check current state and provide helpful feedback
        seq_editor = context.scene.sequence_editor
        if not seq_editor:
            layout.label(text="No sequence editor", icon='ERROR')
            return
            
        active_strip = seq_editor.active_strip
        current_frame = context.scene.frame_current
        
        # Check if we have a valid active strip
        if not active_strip:
            layout.label(text="No active strip", icon='INFO')
            layout.label(text="Select a strip to crop")
            return
            
        # Check if active strip has crop capability
        if not hasattr(active_strip, 'crop'):
            layout.label(text="Active strip cannot be cropped", icon='INFO')
            layout.label(text="Select an image/movie strip")
            return
            
        # Check if active strip is visible at current frame
        if not is_strip_visible_at_frame(active_strip, current_frame):
            layout.label(text="Active strip not visible at current frame", icon='INFO')
            layout.label(text="Move timeline to strip or select visible strip")
            return
            
        # Strip is ready for cropping
        crop_state = get_crop_state()
        if crop_state['active']:
            layout.label(text="Crop mode active", icon='CHECKMARK')
            layout.label(text="• Drag handles to crop")
            layout.label(text="• Click other strips to switch")
            layout.label(text="• Press Enter to finish")
        else:
            layout.label(text="Crop tool active", icon='CHECKMARK')
            layout.label(text=f"Ready to crop: {active_strip.name}")
            layout.label(text="Click strip in preview to start cropping")
            layout.separator()
            # Manual button as backup
            layout.operator("easycrop.crop", text="Start Cropping Now")


# Registration
classes = [
    EASYCROP_OT_crop,
    EASYCROP_OT_select_and_crop,
    EASYCROP_OT_activate_tool,
]

addon_keymaps = []


def register():
    """Register the addon"""
    # Check if operators were imported successfully
    if not operators_imported:
        print("BL Easy Crop: Failed to import operators - check operators/__init__.py exists")
        return
    
    # Register classes
    for cls in classes:
        if cls is not None:  # Skip None classes if import failed
            try:
                bpy.utils.register_class(cls)
            except Exception as e:
                print(f"BL Easy Crop: Failed to register {cls.__name__}: {e}")
    
    # Register keymaps
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        # Register for preview region specifically
        km = kc.keymaps.new(name="SequencerPreview", space_type="SEQUENCE_EDITOR", region_type="WINDOW")
        
        # Crop operator - C key
        kmi = km.keymap_items.new("easycrop.crop", 'C', 'PRESS')
        addon_keymaps.append((km, kmi))
        
        # Also register for the general Sequencer context to catch it from timeline
        km2 = kc.keymaps.new(name="Sequencer", space_type="SEQUENCE_EDITOR")
        kmi2 = km2.keymap_items.new("easycrop.crop", 'C', 'PRESS')
        addon_keymaps.append((km2, kmi2))
    
    # Register the tool - place it right after transform tool
    try:
        # Use the exact builtin tool identifier and specify no separator
        bpy.utils.register_tool(EASYCROP_TOOL_crop, after={"builtin.transform"}, separator=False)
    except Exception as e:
        print(f"BL Easy Crop: Tool placement failed: {e}")
        # Fallback to simple registration if placement fails
        try:
            bpy.utils.register_tool(EASYCROP_TOOL_crop)
        except Exception as e2:
            print(f"BL Easy Crop: Tool registration failed: {e2}")


def unregister():
    """Unregister the addon"""
    # Force cleanup of any active crop mode
    try:
        clear_crop_state()
    except:
        pass
    
    # Force restore gizmos in case they were disabled
    try:
        import bpy
        for area in bpy.context.screen.areas:
            if area.type == 'SEQUENCE_EDITOR':
                for space in area.spaces:
                    if space.type == 'SEQUENCE_EDITOR' and hasattr(space, 'show_gizmo'):
                        space.show_gizmo = True
    except:
        pass
    
    # Unregister the tool
    try:
        bpy.utils.unregister_tool(EASYCROP_TOOL_crop)
    except:
        pass
    
    # Clean up any lingering draw handlers
    try:
        from .operators.crop_core import get_draw_handle
        if get_draw_handle() is not None:
            bpy.types.SpaceSequenceEditor.draw_handler_remove(get_draw_handle(), 'PREVIEW')
    except:
        pass
    
    # Remove keymaps
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    
    # Unregister classes
    for cls in reversed(classes):
        if cls is not None:
            try:
                bpy.utils.unregister_class(cls)
            except:
                pass


if __name__ == "__main__":
    register()