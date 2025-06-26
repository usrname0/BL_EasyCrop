import bpy
from mathutils import Vector
from mathutils.geometry import intersect_point_quad_2d

from .utils.geometry import get_strip_corners, get_preview_offset, mouse_to_res
from .utils.selection import get_visible_strips


class EASYCROP_OT_select(bpy.types.Operator):
    """Select strips in the preview window to maintain focus"""
    bl_idname = "easycrop.select" 
    bl_label = "Select Strip (Easy Crop)"
    bl_description = "Select visible sequences from the preview"
    bl_options = {'UNDO', 'INTERNAL'}
    
    @classmethod
    def poll(cls, context):
        return (context.scene.sequence_editor is not None and
                context.space_data and 
                context.space_data.type == 'SEQUENCE_EDITOR' and
                context.space_data.view_type in {'PREVIEW', 'SEQUENCER_PREVIEW'})
    
    def invoke(self, context, event):
        # Only handle left mouse clicks
        if event.type != 'LEFTMOUSE' or event.value != 'PRESS':
            return {'PASS_THROUGH'}
        
        # Check if we clicked on a strip
        mouse_vec = Vector([event.mouse_region_x, event.mouse_region_y])
        res_pos = mouse_to_res(mouse_vec)
        
        strips = get_visible_strips()
        clicked_strip = None
        
        # Find clicked strip (check from top to bottom)
        for strip in reversed(strips):
            corners = get_strip_corners(strip)
            if len(corners) == 4:
                if intersect_point_quad_2d(res_pos, corners[0], corners[1], corners[2], corners[3]):
                    clicked_strip = strip
                    break
        
        if clicked_strip:
            # Select the strip and make it active
            if not event.shift:
                bpy.ops.sequencer.select_all(action='DESELECT')
            
            clicked_strip.select = True
            context.scene.sequence_editor.active_strip = clicked_strip
            
            # This is important - it ensures the preview has focus
            context.area.tag_redraw()
            return {'FINISHED'}
        
        # If no strip clicked, pass through to allow normal preview interaction
        return {'PASS_THROUGH'}