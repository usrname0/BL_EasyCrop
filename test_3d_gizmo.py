"""
BL Easy Crop v2.0.0 - 3D Viewport Test Gizmo

This is a control experiment to verify our gizmo implementation works
in the 3D viewport where gizmos are known to function properly.
"""

import bpy
from bpy.types import Gizmo, GizmoGroup
from mathutils import Vector, Matrix


class SimpleTestGizmo(Gizmo):
    """Simple test gizmo for 3D viewport"""
    bl_idname = "EASYCROP_GT_simple_test"
    
    def setup(self):
        """Setup the gizmo"""
        print("SimpleTestGizmo.setup() called")
        
    def draw(self, context):
        """Draw the gizmo"""
        print(f"SimpleTestGizmo.draw() called - matrix_basis: {self.matrix_basis.translation}")
        
        # Set gizmo color based on state
        if self.is_highlight:
            self.color = (1.0, 0.0, 0.0)  # Red when highlighted
            self.alpha = 1.0
        else:
            self.color = (0.0, 1.0, 0.0)  # Green normally
            self.alpha = 0.8
            
        # Try different drawing methods - maybe draw_preset_circle ignores matrix_basis
        try:
            # Method 1: Try with explicit matrix multiplication
            final_matrix = self.matrix_basis @ Matrix.Scale(0.5, 4)
            self.draw_preset_circle(final_matrix, select_id=self.select_id)
        except Exception as e:
            print(f"Draw error: {e}")
            # Fallback: try drawing with custom geometry
            try:
                import gpu
                from gpu_extras.batch import batch_for_shader
                # This is a fallback if the preset doesn't work
                pass
            except:
                pass
    
    def invoke(self, context, event):
        """Handle gizmo click"""
        print("SimpleTestGizmo.invoke() called - Gizmo clicked!")
        return {'RUNNING_MODAL'}
    
    def modal(self, context, event, tweak):
        """Handle gizmo drag"""
        print(f"SimpleTestGizmo.modal() called - Delta: {tweak.delta}")
        
        # Move the gizmo with mouse delta
        self.matrix_basis.translation += Vector((tweak.delta[0] * 0.01, tweak.delta[1] * 0.01, 0))
        
        return {'RUNNING_MODAL'}
    
    def exit(self, context, cancel):
        """Handle gizmo exit"""
        print(f"SimpleTestGizmo.exit() called - Cancel: {cancel}")


class SimpleTestGizmoGroup(GizmoGroup):
    """Simple test gizmo group for 3D viewport"""
    bl_idname = "EASYCROP_GGT_simple_test"
    bl_label = "Simple Test Gizmo"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'SHOW_MODAL_ALL'}
    
    @classmethod
    def poll(cls, context):
        """Check if gizmo group should be active"""
        # Only show in 3D viewport
        if not context.space_data or context.space_data.type != 'VIEW_3D':
            return False
            
        # Only show when there's an active object
        if not context.active_object:
            return False
            
        return True
    
    def setup(self, context):
        """Setup the gizmo group"""
        print("SimpleTestGizmoGroup.setup() called")
        
        # Create a single test gizmo
        gizmo = self.gizmos.new(SimpleTestGizmo.bl_idname)
        gizmo.select_id = 0
        
        # Position it at the active object's location using world matrix
        if context.active_object:
            gizmo.matrix_basis = context.active_object.matrix_world.normalized()
        
        print(f"Created {len(self.gizmos)} test gizmo(s)")
    
    def refresh(self, context):
        """Refresh gizmo positions"""
        print("SimpleTestGizmoGroup.refresh() called")
        
        # Update gizmo position to follow active object
        if context.active_object and len(self.gizmos) > 0:
            obj = context.active_object
            print(f"Object location: {obj.location}")
            old_matrix = self.gizmos[0].matrix_basis.copy()
            
            # Use the object's world matrix normalized (this is the correct approach)
            self.gizmos[0].matrix_basis = obj.matrix_world.normalized()
                
            print(f"Gizmo matrix updated from {old_matrix.translation} to {self.gizmos[0].matrix_basis.translation}")
    
    def draw_prepare(self, context):
        """Prepare for drawing"""
        print("SimpleTestGizmoGroup.draw_prepare() called")
        self.refresh(context)


def register_3d_test_gizmo():
    """Register the 3D test gizmo classes"""
    try:
        print("=== REGISTERING 3D TEST GIZMO ===")
        
        bpy.utils.register_class(SimpleTestGizmo)
        print("✓ Registered SimpleTestGizmo")
        
        bpy.utils.register_class(SimpleTestGizmoGroup)
        print("✓ Registered SimpleTestGizmoGroup")
        
        # Verify registration
        try:
            gizmo_type = bpy.types.EASYCROP_GT_simple_test
            print("✓ SimpleTestGizmo verified in bpy.types")
        except AttributeError:
            print("✗ SimpleTestGizmo NOT found in bpy.types")
        
        try:
            gizmo_group_type = bpy.types.EASYCROP_GGT_simple_test
            print("✓ SimpleTestGizmoGroup verified in bpy.types")
        except AttributeError:
            print("✗ SimpleTestGizmoGroup NOT found in bpy.types")
            
        # Try to ensure the gizmo group type is active
        try:
            # In newer Blender versions, use the workspace tool system
            wm = bpy.context.window_manager
            if hasattr(wm, 'gizmo_group_type_ensure'):
                wm.gizmo_group_type_ensure(SimpleTestGizmoGroup.bl_idname)
                print("✓ gizmo_group_type_ensure() called successfully")
            else:
                print("ℹ gizmo_group_type_ensure() not available - this is normal")
        except Exception as e:
            print(f"✗ gizmo_group_type_ensure() failed: {e}")
            
        print("=== 3D TEST GIZMO REGISTRATION COMPLETE ===")
        return True
        
    except Exception as e:
        print(f"Failed to register 3D test gizmo: {e}")
        import traceback
        traceback.print_exc()
        return False


def unregister_3d_test_gizmo():
    """Unregister the 3D test gizmo classes"""
    try:
        print("=== UNREGISTERING 3D TEST GIZMO ===")
        
        bpy.utils.unregister_class(SimpleTestGizmoGroup)
        print("✓ Unregistered SimpleTestGizmoGroup")
        
        bpy.utils.unregister_class(SimpleTestGizmo)
        print("✓ Unregistered SimpleTestGizmo")
        
        print("=== 3D TEST GIZMO UNREGISTRATION COMPLETE ===")
        
    except Exception as e:
        print(f"Failed to unregister 3D test gizmo: {e}")