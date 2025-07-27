"""
BL Easy Crop - Test Gizmo Activation

Temporary operator to manually activate crop handles gizmo for testing.
"""

import bpy


class EASYCROP_OT_test_gizmo_activation(bpy.types.Operator):
    """Test operator to manually activate crop handles gizmo"""
    bl_idname = "sequencer.test_crop_handles_gizmo"
    bl_label = "Test Crop Handles Gizmo"
    bl_description = "Manually activate crop handles gizmo for testing"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return (context.scene.sequence_editor is not None and
                context.scene.sequence_editor.active_strip is not None and
                hasattr(context.scene.sequence_editor.active_strip, 'crop'))
    
    def execute(self, context):
        # Temporarily enable the crop handles gizmo by modifying its poll method
        try:
            from ..gizmos.crop_handles_gizmo import EASYCROP_GGT_crop_handles
            
            # Store the original poll method
            if not hasattr(EASYCROP_GGT_crop_handles, '_original_poll'):
                EASYCROP_GGT_crop_handles._original_poll = EASYCROP_GGT_crop_handles.poll
            
            # Override poll to always return True for basic testing
            @classmethod  
            def test_poll(cls, context):
                # Basic checks from original poll
                if not context.space_data or context.space_data.type != 'SEQUENCE_EDITOR':
                    return False
                if hasattr(context.space_data, 'display_mode'):
                    if context.space_data.display_mode != 'IMAGE':
                        return False
                if not context.scene.sequence_editor:
                    return False
                active_strip = context.scene.sequence_editor.active_strip
                if not active_strip or not hasattr(active_strip, 'crop'):
                    return False
                if not active_strip.select:
                    return False
                
                # Don't show if modal crop mode is already active
                from ..operators.crop_core import get_crop_state
                crop_state = get_crop_state()
                if crop_state['active']:
                    return False
                
                print("🟢 TEST GIZMO ACTIVATED! Handles should appear as circles.")
                print("🎯 Try dragging the circle handles - they should move if event capture works.")
                return True
            
            # Apply the test poll method
            EASYCROP_GGT_crop_handles.poll = test_poll
            
            # Force refresh gizmos
            for area in context.screen.areas:
                if area.type == 'SEQUENCE_EDITOR':
                    area.tag_redraw()
            
            self.report({'INFO'}, "Crop handles gizmo activated for testing")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Failed to activate test gizmo: {e}")
            return {'CANCELLED'}


class EASYCROP_OT_test_gizmo_deactivation(bpy.types.Operator):
    """Test operator to deactivate crop handles gizmo"""
    bl_idname = "sequencer.test_crop_handles_gizmo_off"
    bl_label = "Deactivate Test Gizmo"
    bl_description = "Deactivate test crop handles gizmo"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        try:
            from ..gizmos.crop_handles_gizmo import EASYCROP_GGT_crop_handles
            
            # Restore original poll method
            if hasattr(EASYCROP_GGT_crop_handles, '_original_poll'):
                EASYCROP_GGT_crop_handles.poll = EASYCROP_GGT_crop_handles._original_poll
                delattr(EASYCROP_GGT_crop_handles, '_original_poll')
            
            # Force refresh gizmos
            for area in context.screen.areas:
                if area.type == 'SEQUENCE_EDITOR':
                    area.tag_redraw()
            
            self.report({'INFO'}, "Test gizmo deactivated")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Failed to deactivate test gizmo: {e}")
            return {'CANCELLED'}