bl_info = {
    "name": "BL Easy Crop",
    "description": "Easy cropping tool for Blender's Video Sequence Editor",
    "author": "Adapted from VSE Transform Tools",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "Sequencer > Preview",
    "warning": "",
    "doc_url": "",
    "tracker_url": "",
    "category": "Sequencer"
}

import bpy
from bpy.types import Operator, Panel, Menu, WorkSpaceTool

# Import operators with better error reporting
try:
    from .operators.crop import EASYCROP_OT_crop
    operators_imported = True
except ImportError as e:
    print(f"BL Easy Crop: Import error: {e}")
    EASYCROP_OT_crop = None
    operators_imported = False


class EASYCROP_MT_menu(Menu):
    """Main menu for Easy Crop tools"""
    bl_label = "Easy Crop"
    bl_idname = "EASYCROP_MT_menu"

    @classmethod
    def poll(cls, context):
        st = context.space_data
        return st.view_type in {'PREVIEW', 'SEQUENCER_PREVIEW'}

    def draw(self, context):
        layout = self.layout
        layout.operator_context = 'INVOKE_REGION_PREVIEW'
        
        layout.operator("easycrop.crop", text="Crop Strip")


class EASYCROP_TOOL_crop(WorkSpaceTool):
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_context_mode = 'PREVIEW'
    
    bl_idname = "easycrop.crop_tool"
    bl_label = "Crop"
    bl_description = "Crop strips in the preview"
    bl_icon = "ops.mesh.knife_tool"
    bl_widget = None
    bl_keymap = (
        ("easycrop.crop", {"type": 'LEFTMOUSE', "value": 'PRESS'}, None),
    )
    
    @staticmethod  
    def draw_settings(context, layout, tool):
        # Check if we should auto-activate
        if (context.scene.sequence_editor and 
            context.scene.sequence_editor.active_strip and
            hasattr(context.scene.sequence_editor.active_strip, 'crop')):
            try:
                from .operators import crop
                if not crop._crop_active:
                    # Show a message that they need to click
                    layout.label(text="Click in preview to start cropping", icon='INFO')
            except:
                pass


# Menu append functions
def add_menu_func(self, context):
    st = context.space_data
    if st and st.type == 'SEQUENCE_EDITOR':
        if st.view_type in {'PREVIEW', 'SEQUENCER_PREVIEW'}:
            self.layout.menu("EASYCROP_MT_menu")
            self.layout.separator()


# Registration
classes = [
    EASYCROP_OT_crop,
    EASYCROP_MT_menu,
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
    
    # Add menu entries
    bpy.types.SEQUENCER_MT_editor_menus.append(add_menu_func)
    
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
    
    # Register the tool - place it after transform tool
    try:
        bpy.utils.register_tool(EASYCROP_TOOL_crop, after={"builtin.transform"}, separator=False, group=True)
    except Exception as e:
        # Fallback to simple registration if placement fails
        try:
            bpy.utils.register_tool(EASYCROP_TOOL_crop)
        except Exception as e2:
            print(f"BL Easy Crop: Tool registration failed: {e2}")


def unregister():
    """Unregister the addon"""
    # Force cleanup of any active crop mode
    try:
        from .operators import crop
        crop._crop_active = False
        crop._draw_data.clear()
    except:
        pass
    
    # Unregister the tool
    try:
        bpy.utils.unregister_tool(EASYCROP_TOOL_crop)
    except:
        pass
    
    # Clean up any lingering draw handlers
    try:
        from .operators import crop
        if hasattr(crop, '_draw_handle') and crop._draw_handle is not None:
            bpy.types.SpaceSequenceEditor.draw_handler_remove(crop._draw_handle, 'PREVIEW')
            crop._draw_handle = None
    except:
        pass
    
    # Remove keymaps
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    
    # Remove menu entries
    bpy.types.SEQUENCER_MT_editor_menus.remove(add_menu_func)
    
    # Unregister classes
    for cls in reversed(classes):
        if cls is not None:
            try:
                bpy.utils.unregister_class(cls)
            except:
                pass


if __name__ == "__main__":
    register()