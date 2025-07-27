"""
BL Easy Crop - Crop Gizmo

A gizmo that automatically activates crop mode when the crop tool is selected
and there's an active croppable strip. This eliminates the need for an extra
click on the strip to start cropping.
"""

import bpy
from bpy.types import Gizmo, GizmoGroup
from mathutils import Vector, Matrix

from ..operators.crop_core import (
    get_crop_state, is_strip_visible_at_frame, 
    get_strip_geometry_with_flip_support
)


class EASYCROP_GT_crop_activation(Gizmo):
    """Crop activation gizmo - automatically starts crop mode"""
    bl_idname = "EASYCROP_GT_crop_activation"
    
    def setup(self):
        """Setup the gizmo"""
        pass
        
    def draw(self, context):
        """Draw the gizmo - crop symbol like the modal operator"""
        import gpu
        from gpu_extras.batch import batch_for_shader
        
        # Set color based on highlight state
        if self.is_highlight:
            color = (1.0, 0.5, 0.0, 1.0)  # Orange when highlighted
        else:
            color = (1.0, 1.0, 1.0, 0.8)  # White like modal operator
        
        try:
            # Draw the same crop symbol as the modal operator
            center_pos = self.matrix_basis.translation
            center_x = center_pos.x
            center_y = center_pos.y
            
            # Symbol dimensions (same as crop_drawing.py)
            outer_size = 8
            inner_size = 5
            
            line_shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            gpu.state.line_width_set(1.5)
            line_shader.bind()
            line_shader.uniform_float("color", color)
            
            # Corner brackets (same as crop_drawing.py)
            # Top-left L-shape
            tl_vertical = [
                (center_x - outer_size, center_y + 1),
                (center_x - outer_size, center_y + outer_size)
            ]
            tl_horizontal = [
                (center_x - outer_size, center_y + outer_size),
                (center_x - 1, center_y + outer_size)
            ]
            
            # Bottom-right L-shape  
            br_horizontal = [
                (center_x + 1, center_y - outer_size),
                (center_x + outer_size, center_y - outer_size)
            ]
            br_vertical = [
                (center_x + outer_size, center_y - outer_size),
                (center_x + outer_size, center_y - 1)
            ]
            
            # Inner viewing rectangle
            inner_rect_lines = [
                [(center_x - inner_size, center_y - inner_size), 
                 (center_x + inner_size, center_y - inner_size)],
                [(center_x + inner_size, center_y - inner_size),
                 (center_x + inner_size, center_y + inner_size)],
                [(center_x + inner_size, center_y + inner_size),
                 (center_x - inner_size, center_y + inner_size)],
                [(center_x - inner_size, center_y + inner_size),
                 (center_x - inner_size, center_y - inner_size)]
            ]
            
            # Draw all elements
            for line_verts in [tl_vertical, tl_horizontal, br_horizontal, br_vertical]:
                batch = batch_for_shader(line_shader, 'LINES', {"pos": line_verts})
                batch.draw(line_shader)
            
            for line_verts in inner_rect_lines:
                batch = batch_for_shader(line_shader, 'LINES', {"pos": line_verts})
                batch.draw(line_shader)
            
            gpu.state.line_width_set(1.0)
            
        except Exception as e:
            print(f"Gizmo draw error: {e}")
            # Fallback to circle if crop symbol fails
            try:
                if self.is_highlight:
                    self.color = (1.0, 0.5, 0.0)
                    self.alpha = 1.0
                else:
                    self.color = (1.0, 1.0, 1.0)
                    self.alpha = 0.8
                final_matrix = self.matrix_basis @ Matrix.Scale(10.0, 4)
                self.draw_preset_circle(final_matrix, select_id=self.select_id)
            except:
                pass
    
    def invoke(self, context, event):
        """Handle gizmo click - simulate C key press to trigger crop"""
        # Check if crop is already active
        crop_state = get_crop_state()
        if crop_state['active']:
            return {'CANCELLED'}
        
        # Get the active strip
        strip = context.scene.sequence_editor.active_strip if context.scene.sequence_editor else None
        if not strip or not hasattr(strip, 'crop'):
            return {'CANCELLED'}
        
        # Simulate C key press to trigger crop mode via keymap
        try:
            # Create a fake keyboard event for 'C' key
            fake_event = type('obj', (object,), {
                'type': 'C',
                'value': 'PRESS',
                'shift': False,
                'ctrl': False,
                'alt': False,
                'oskey': False,
                'mouse_region_x': event.mouse_region_x,
                'mouse_region_y': event.mouse_region_y
            })()
            
            # Trigger the keymap directly
            bpy.ops.sequencer.crop('INVOKE_DEFAULT')
            return {'FINISHED'}
        except Exception:
            return {'CANCELLED'}


class EASYCROP_GGT_crop_tool(GizmoGroup):
    """Crop tool gizmo group - auto-triggers when crop tool is selected"""
    bl_idname = "EASYCROP_GGT_crop_tool"
    bl_label = "Crop Tool"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'PREVIEW'
    bl_options = {'SHOW_MODAL_ALL'}
    
    # Class variable to track if we've auto-triggered
    _auto_triggered = False
    
    @classmethod
    def poll(cls, context):
        """Check if gizmo group should be active"""
        # Only show in VSE preview
        if not context.space_data or context.space_data.type != 'SEQUENCE_EDITOR':
            return False
            
        # Check display mode
        if hasattr(context.space_data, 'display_mode'):
            if context.space_data.display_mode != 'IMAGE':
                return False
        
        # Only show when there's a sequence editor and active strip
        if not context.scene.sequence_editor:
            return False
            
        active_strip = context.scene.sequence_editor.active_strip
        if not active_strip or not hasattr(active_strip, 'crop'):
            return False
            
        # Only show for visible strips
        current_frame = context.scene.frame_current
        if not is_strip_visible_at_frame(active_strip, current_frame):
            return False
        
        # Don't show if crop mode is already active (avoid conflicts)
        crop_state = get_crop_state()
        if crop_state['active']:
            return False
        
        # DISABLE: Don't auto-show the single gizmo anymore (we have the handles version)
        return False
        
        # TODO: Enable tool detection once positioning is confirmed working
        # try:
        #     workspace = context.workspace
        #     if workspace:
        #         # Check if crop gizmo tool is active
        #         active_tool = workspace.tools.from_space_sequencer_mode('PREVIEW', create=False)
        #         if active_tool and active_tool.idname == "sequencer.crop_gizmo_tool":
        #             return True
        # except:
        #     pass
        # return False
    
    def setup(self, context):
        """Setup the gizmo group"""
        # Create the crop activation gizmo
        gizmo = self.gizmos.new(EASYCROP_GT_crop_activation.bl_idname)
        gizmo.select_id = 0
        
        # Position it at strip center initially
        gizmo.matrix_basis = Matrix.Translation((0, 0, 0))
    
    def refresh(self, context):
        """Refresh gizmo positions"""
        # Get the active strip
        scene = context.scene
        if not scene.sequence_editor or not scene.sequence_editor.active_strip:
            return
            
        active_strip = scene.sequence_editor.active_strip
        if not hasattr(active_strip, 'crop'):
            return
            
        if len(self.gizmos) > 0:
            # Position gizmo using the same coordinate system as modal operator drawing
            try:
                corners, (pivot_x, pivot_y), (scale_x, scale_y, flip_x, flip_y) = get_strip_geometry_with_flip_support(active_strip, scene)
                
                # Use the same coordinate conversion as crop_drawing.py:122-126
                res_x = scene.render.resolution_x
                res_y = scene.render.resolution_y
                
                # Convert to view coordinates (same as modal operator)
                view_x = pivot_x - res_x / 2
                view_y = pivot_y - res_y / 2
                
                # But for gizmos, we need to get the actual screen position
                region = context.region
                if region and region.view2d:
                    view2d = region.view2d
                    screen_co = view2d.view_to_region(view_x, view_y, clip=False)
                    
                    print(f"Pivot: ({pivot_x}, {pivot_y}) → View: ({view_x}, {view_y}) → Screen: ({screen_co[0]}, {screen_co[1]})")
                    
                    # Use screen coordinates for gizmo positioning
                    self.gizmos[0].matrix_basis = Matrix.Translation((screen_co[0], screen_co[1], 0))
                else:
                    # Fallback to direct view coordinates
                    self.gizmos[0].matrix_basis = Matrix.Translation((view_x, view_y, 0))
                
            except Exception as e:
                print(f"Gizmo refresh error: {e}")
                # Fallback to center position
                self.gizmos[0].matrix_basis = Matrix.Translation((500, 300, 0))
    
    def draw_prepare(self, context):
        """Prepare for drawing"""
        self.refresh(context)


def register_crop_gizmo():
    """Register the crop gizmo classes"""
    try:
        print("=== REGISTERING CROP GIZMO ===")
        
        bpy.utils.register_class(EASYCROP_GT_crop_activation)
        print("✓ Registered EASYCROP_GT_crop_activation")
        
        bpy.utils.register_class(EASYCROP_GGT_crop_tool)
        print("✓ Registered EASYCROP_GGT_crop_tool")
        
        # Ensure the gizmo group type is active
        try:
            wm = bpy.context.window_manager
            if hasattr(wm, 'gizmo_group_type_ensure'):
                wm.gizmo_group_type_ensure(EASYCROP_GGT_crop_tool.bl_idname)
                print("✓ gizmo_group_type_ensure() called successfully")
        except Exception as e:
            print(f"ℹ gizmo_group_type_ensure() not needed: {e}")
            
        print("=== CROP GIZMO REGISTRATION COMPLETE ===")
        return True
        
    except Exception as e:
        print(f"Failed to register crop gizmo: {e}")
        import traceback
        traceback.print_exc()
        return False


def unregister_crop_gizmo():
    """Unregister the crop gizmo classes"""
    try:
        print("=== UNREGISTERING CROP GIZMO ===")
        
        bpy.utils.unregister_class(EASYCROP_GGT_crop_tool)
        print("✓ Unregistered EASYCROP_GGT_crop_tool")
        
        bpy.utils.unregister_class(EASYCROP_GT_crop_activation)
        print("✓ Unregistered EASYCROP_GT_crop_activation")
        
        print("=== CROP GIZMO UNREGISTRATION COMPLETE ===")
        
    except Exception as e:
        print(f"Failed to unregister crop gizmo: {e}")