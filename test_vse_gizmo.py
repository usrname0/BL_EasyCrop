"""
BL Easy Crop v2.0.0 - VSE Test Gizmo

This is a simple test gizmo for the VSE based on the working 3D gizmo pattern.
Should appear as a green circle that follows the active strip.
"""

import bpy
from bpy.types import Gizmo, GizmoGroup
from mathutils import Vector, Matrix


class SimpleVSETestGizmo(Gizmo):
    """Simple test gizmo for VSE"""
    bl_idname = "EASYCROP_GT_vse_test"
    
    def setup(self):
        """Setup the gizmo"""
        print("SimpleVSETestGizmo.setup() called")
        
    def draw(self, context):
        """Draw the gizmo"""
        print(f"SimpleVSETestGizmo.draw() called - matrix_basis: {self.matrix_basis.translation}")
        
        # Set gizmo color based on state
        if self.is_highlight:
            self.color = (1.0, 0.0, 0.0)  # Red when highlighted
            self.alpha = 1.0
        else:
            self.color = (0.0, 1.0, 0.0)  # Green normally
            self.alpha = 0.8
            
        # Use the same working pattern from 3D gizmo - explicit matrix multiplication
        try:
            # This is the key fix that made 3D gizmos work!
            final_matrix = self.matrix_basis @ Matrix.Scale(20.0, 4)  # Larger scale for VSE
            self.draw_preset_circle(final_matrix, select_id=self.select_id)
            print(f"VSE Draw successful with final_matrix: {final_matrix.translation}")
        except Exception as e:
            print(f"VSE Draw error: {e}")
    
    def invoke(self, context, event):
        """Handle gizmo click"""
        print("SimpleVSETestGizmo.invoke() called - VSE Gizmo clicked!")
        return {'RUNNING_MODAL'}
    
    def modal(self, context, event, tweak):
        """Handle gizmo drag"""
        print(f"SimpleVSETestGizmo.modal() called - Delta: {tweak.delta}")
        
        # Move the gizmo with mouse delta (just for testing)
        self.matrix_basis.translation += Vector((tweak.delta[0] * 0.1, tweak.delta[1] * 0.1, 0))
        
        return {'RUNNING_MODAL'}
    
    def exit(self, context, cancel):
        """Handle gizmo exit"""
        print(f"SimpleVSETestGizmo.exit() called - Cancel: {cancel}")


class SimpleVSETestGizmoGroup(GizmoGroup):
    """Simple test gizmo group for VSE"""
    bl_idname = "EASYCROP_GGT_vse_test"
    bl_label = "VSE Test Gizmo"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'PREVIEW'  # Back to PREVIEW for the preview region
    bl_options = {'SHOW_MODAL_ALL'}  # Remove '3D' option for VSE
    
    @classmethod
    def poll(cls, context):
        """Check if gizmo group should be active"""
        print("SimpleVSETestGizmoGroup.poll() called!")
        print(f"Current region type: {context.region.type if context.region else 'No region'}")
        
        # Only show in VSE preview
        if not context.space_data or context.space_data.type != 'SEQUENCE_EDITOR':
            print("- Not in sequence editor")
            return False
            
        # Both Preview and Sequencer modes report as 'SEQUENCER'
        # We can check display_mode to distinguish if needed
        if hasattr(context.space_data, 'display_mode'):
            display_mode = context.space_data.display_mode
            # Only show in image preview mode (not waveform, etc.)
            if display_mode != 'IMAGE':
                return False
            
        # Only show when there's a sequence editor and active strip
        if not context.scene.sequence_editor:
            print("- No sequence editor")
            return False
            
        if not context.scene.sequence_editor.active_strip:
            print("- No active strip")
            return False
            
        print("- VSE Poll passed!")
        return True
    
    def setup(self, context):
        """Setup the gizmo group"""
        print("SimpleVSETestGizmoGroup.setup() called")
        
        # Create a single test gizmo
        gizmo = self.gizmos.new(SimpleVSETestGizmo.bl_idname)
        gizmo.select_id = 0
        
        # Position it at strip center initially (we'll update in refresh)
        gizmo.matrix_basis = Matrix.Translation((0, 0, 0))
        
        print(f"Created {len(self.gizmos)} VSE test gizmo(s)")
    
    def refresh(self, context):
        """Refresh gizmo positions"""
        print("SimpleVSETestGizmoGroup.refresh() called")
        
        # Get the active strip
        scene = context.scene
        if not scene.sequence_editor or not scene.sequence_editor.active_strip:
            return
            
        active_strip = scene.sequence_editor.active_strip
        if not hasattr(active_strip, 'crop'):
            return
            
        if len(self.gizmos) > 0:
            # VSE coordinate system - try moving towards center
            # Preview area might be centered differently than 3D viewport
            test_location = Vector((200, 200, 0))  # Try positive coordinates
            print(f"Setting VSE gizmo to test location: {test_location}")
            
            self.gizmos[0].matrix_basis = Matrix.Translation(test_location)
            print(f"VSE Gizmo matrix set to: {self.gizmos[0].matrix_basis.translation}")
    
    def draw_prepare(self, context):
        """Prepare for drawing"""
        print("SimpleVSETestGizmoGroup.draw_prepare() called")
        self.refresh(context)


def register_vse_test_gizmo():
    """Register the VSE test gizmo classes"""
    try:
        print("=== REGISTERING VSE TEST GIZMO ===")
        print("About to register SimpleVSETestGizmo...")
        
        bpy.utils.register_class(SimpleVSETestGizmo)
        print("✓ Registered SimpleVSETestGizmo")
        
        print("About to register SimpleVSETestGizmoGroup...")
        bpy.utils.register_class(SimpleVSETestGizmoGroup)
        print("✓ Registered SimpleVSETestGizmoGroup")
        
        # Verify registration
        try:
            gizmo_type = bpy.types.EASYCROP_GT_vse_test
            print("✓ SimpleVSETestGizmo verified in bpy.types")
        except AttributeError:
            print("✗ SimpleVSETestGizmo NOT found in bpy.types")
        
        try:
            gizmo_group_type = bpy.types.EASYCROP_GGT_vse_test
            print("✓ SimpleVSETestGizmoGroup verified in bpy.types")
        except AttributeError:
            print("✗ SimpleVSETestGizmoGroup NOT found in bpy.types")
            
        # Try to ensure the gizmo group type is active (similar to 3D gizmo)
        try:
            wm = bpy.context.window_manager
            if hasattr(wm, 'gizmo_group_type_ensure'):
                wm.gizmo_group_type_ensure(SimpleVSETestGizmoGroup.bl_idname)
                print("✓ gizmo_group_type_ensure() called successfully for VSE")
            else:
                print("ℹ gizmo_group_type_ensure() not available")
        except Exception as e:
            print(f"✗ gizmo_group_type_ensure() failed: {e}")
            
        print("=== VSE TEST GIZMO REGISTRATION COMPLETE ===")
        return True
        
    except Exception as e:
        print(f"Failed to register VSE test gizmo: {e}")
        import traceback
        traceback.print_exc()
        return False


def unregister_vse_test_gizmo():
    """Unregister the VSE test gizmo classes"""
    try:
        print("=== UNREGISTERING VSE TEST GIZMO ===")
        
        bpy.utils.unregister_class(SimpleVSETestGizmoGroup)
        print("✓ Unregistered SimpleVSETestGizmoGroup")
        
        bpy.utils.unregister_class(SimpleVSETestGizmo)
        print("✓ Unregistered SimpleVSETestGizmo")
        
        print("=== VSE TEST GIZMO UNREGISTRATION COMPLETE ===")
        
    except Exception as e:
        print(f"Failed to unregister VSE test gizmo: {e}")