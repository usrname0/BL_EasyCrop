"""
BL Easy Crop - Clean, simple version

This version includes:
- Working menu integration with proper context handling
- Simple toolbar tool (standard Blender behavior)
- Proper keymap handling with Alt+C for clear crop
- Respects user's custom transform keybindings
"""

bl_info = {
    "name": "BL Easy Crop",
    "description": "Easy cropping tool for Blender's Video Sequence Editor",
    "author": "Adapted from VSE Transform Tools",
    "version": (1, 0, 2),
    "blender": (4, 4, 0),
    "location": "Sequencer > Preview > Toolbar",
    "warning": "",
    "doc_url": "",
    "tracker_url": "",
    "category": "Sequencer"
}

import bpy
import os
from bpy.types import Operator, WorkSpaceTool

# Import operators with error handling
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
    operators_imported = False


class EASYCROP_OT_clear_crop(bpy.types.Operator):
    """Clear crop from selected strips"""
    bl_idname = "sequencer.clear_crop"
    bl_label = "Clear Crop"
    bl_description = "Clear crop from all selected strips"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        if not context.scene.sequence_editor:
            return False
        
        # Check if any selected strips have crop capability
        for strip in context.selected_sequences:
            if hasattr(strip, 'crop'):
                return True
        return False
    
    def execute(self, context):
        cleared_count = 0
        
        for strip in context.selected_sequences:
            if hasattr(strip, 'crop') and strip.crop:
                # Reset all crop values to 0
                strip.crop.min_x = 0
                strip.crop.max_x = 0
                strip.crop.min_y = 0
                strip.crop.max_y = 0
                cleared_count += 1
        
        if cleared_count > 0:
            self.report({'INFO'}, f"Cleared crop from {cleared_count} strip(s)")
        else:
            self.report({'INFO'}, "No strips with crop found")
        
        return {'FINISHED'}


class EASYCROP_TOOL_crop(WorkSpaceTool):
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_context_mode = 'PREVIEW'
    
    bl_idname = "sequencer.crop_tool"
    bl_label = "Crop"
    bl_description = "Crop strips in the preview"
    bl_icon = os.path.join(os.path.dirname(__file__), "crop")
    bl_widget = None
    
    # Standard tool behavior - click to use crop
    bl_keymap = (
        ("sequencer.select_and_crop", {"type": 'LEFTMOUSE', "value": 'PRESS'}, None),
    )
    
    @staticmethod  
    def draw_settings(context, layout, tool):
        # Simple statu
        # s display
        seq_editor = context.scene.sequence_editor
        if not seq_editor:
            layout.label(text="No sequence editor")
            return
            
        active_strip = seq_editor.active_strip
        current_frame = context.scene.frame_current
        
        # Show current state
        crop_state = get_crop_state()
        if crop_state['active']:
            layout.label(text="Crop mode active", icon='CHECKMARK')
            layout.label(text="• Drag handles to crop")
            layout.label(text="• Click other strips to switch")
            layout.label(text="• Press Enter to finish")
        elif active_strip and hasattr(active_strip, 'crop'):
            if is_strip_visible_at_frame(active_strip, current_frame):
                layout.label(text=f"Ready: {active_strip.name}")
                layout.label(text="Click strip in preview to start cropping")
            else:
                layout.label(text="Strip not at current frame")
        else:
            layout.label(text="Select a croppable strip")


# Menu functions
def menu_func_strip_transform(self, context):
    """Add Easy Crop to Strip > Transform menu"""
    if context.space_data.view_type in {'PREVIEW', 'SEQUENCER_PREVIEW'}:
        self.layout.operator_context = 'INVOKE_REGION_PREVIEW'
        self.layout.operator("sequencer.crop", text="Crop")


def menu_func_image_transform(self, context):
    """Add Easy Crop to Image > Transform menu"""
    if context.space_data.view_type in {'PREVIEW', 'SEQUENCER_PREVIEW'}:
        self.layout.operator_context = 'INVOKE_REGION_PREVIEW'
        self.layout.operator("sequencer.crop", text="Crop")


def menu_func_image_clear(self, context):
    """Add Clear Crop to Image > Clear menu"""
    if context.space_data.view_type in {'PREVIEW', 'SEQUENCER_PREVIEW'}:
        self.layout.operator("sequencer.clear_crop", text="Crop")


# Registration
classes = [
    EASYCROP_OT_crop,
    EASYCROP_OT_select_and_crop,
    EASYCROP_OT_activate_tool,
    EASYCROP_OT_clear_crop,
]

addon_keymaps = []


def register():
    """Register the addon"""
    if not operators_imported:
        print("BL Easy Crop: Failed to import operators")
        return
    
    # Register classes
    for cls in classes:
        if cls is not None:
            try:
                bpy.utils.register_class(cls)
            except Exception as e:
                print(f"BL Easy Crop: Failed to register {cls.__name__}: {e}")
    
    # Register keymaps - only in Preview area
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        # Preview region keymaps only
        km = kc.keymaps.new(name="SequencerPreview", space_type="SEQUENCE_EDITOR", region_type="WINDOW")
        
        # Crop operator - C key  
        kmi = km.keymap_items.new("sequencer.crop", 'C', 'PRESS')
        addon_keymaps.append((km, kmi))
        
        # Clear crop operator - Alt+C key
        kmi_clear = km.keymap_items.new("sequencer.clear_crop", 'C', 'PRESS', alt=True)
        addon_keymaps.append((km, kmi_clear))
    
    # Register the tool
    try:
        bpy.utils.register_tool(EASYCROP_TOOL_crop, after={"builtin.transform"}, separator=False)
    except Exception as e:
        print(f"BL Easy Crop: Tool placement failed: {e}")
        try:
            bpy.utils.register_tool(EASYCROP_TOOL_crop)
        except Exception as e2:
            print(f"BL Easy Crop: Tool registration failed: {e2}")
    
    # Add menu items
    try:
        bpy.types.SEQUENCER_MT_strip_transform.append(menu_func_strip_transform)
        bpy.types.SEQUENCER_MT_image_transform.append(menu_func_image_transform)
        bpy.types.SEQUENCER_MT_image_clear.append(menu_func_image_clear)
    except Exception as e:
        print(f"BL Easy Crop: Menu integration failed: {e}")


def unregister():
    """Unregister the addon"""
    # Force cleanup of any active crop mode
    try:
        clear_crop_state()
    except:
        pass
    
    # Force restore gizmos in case they were disabled
    try:
        for area in bpy.context.screen.areas:
            if area.type == 'SEQUENCE_EDITOR':
                for space in area.spaces:
                    if space.type == 'SEQUENCE_EDITOR' and hasattr(space, 'show_gizmo'):
                        space.show_gizmo = True
    except:
        pass
    
    # Remove menu items
    try:
        bpy.types.SEQUENCER_MT_strip_transform.remove(menu_func_strip_transform)
        bpy.types.SEQUENCER_MT_image_transform.remove(menu_func_image_transform)
        bpy.types.SEQUENCER_MT_image_clear.remove(menu_func_image_clear)
    except:
        pass
    
    # Unregister the tool
    try:
        bpy.utils.unregister_tool(EASYCROP_TOOL_crop)
    except:
        pass
    
    # Clean up draw handlers
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