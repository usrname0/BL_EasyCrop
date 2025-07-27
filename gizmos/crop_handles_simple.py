"""
BL Easy Crop - Simple Crop Handles Gizmo

A simplified version that focuses on just getting basic gizmos working
without crashes.
"""

import bpy
import math
from bpy.types import Gizmo, GizmoGroup
from mathutils import Vector, Matrix

from ..operators.crop_core import (
    get_crop_state, is_strip_visible_at_frame, 
    get_strip_geometry_with_flip_support
)


class EASYCROP_GGT_crop_handles_simple(GizmoGroup):
    """Simple crop handles gizmo group - basic functionality only"""
    bl_idname = "EASYCROP_GGT_crop_handles_simple"
    bl_label = "Crop Handles (Simple)"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'PREVIEW'
    bl_options = {'SHOW_MODAL_ALL', 'PERSISTENT'}
    
    @classmethod
    def poll(cls, context):
        """Check if gizmo group should be active"""
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
            
        current_frame = context.scene.frame_current
        if not is_strip_visible_at_frame(active_strip, current_frame):
            return False
        
        crop_state = get_crop_state()
        if crop_state['active']:
            return False
        
        # Always show when basic conditions are met
        return True
    
    def setup(self, context):
        """Setup the gizmo group with simple gizmos"""
        print("🔧 Setting up SIMPLE crop handles gizmo group...")
        
        # Create just 4 corner handles for now
        for i in range(4):
            gizmo = self.gizmos.new("GIZMO_GT_arrow_3d")
            gizmo.color = (1.0, 1.0, 1.0)
            gizmo.alpha = 0.8
            gizmo.color_highlight = (1.0, 0.5, 0.0)
            gizmo.alpha_highlight = 1.0
            gizmo.draw_style = 'BOX'
            gizmo.length = 20.0  # Make them visible
            
            # Don't set any targets for now - just make them visible
            print(f"✓ Created simple corner handle {i}")
        
        print(f"🎯 Created {len(self.gizmos)} simple crop handle gizmos total")
    
    def refresh(self, context):
        """Refresh gizmo positions - simplified"""
        scene = context.scene
        if not scene.sequence_editor or not scene.sequence_editor.active_strip:
            return
            
        active_strip = scene.sequence_editor.active_strip
        if not hasattr(active_strip, 'crop'):
            return
            
        try:
            print("🔄 Refreshing SIMPLE gizmo positions")
            
            # Get strip geometry
            corners, (pivot_x, pivot_y), (scale_x, scale_y, flip_x, flip_y) = get_strip_geometry_with_flip_support(active_strip, scene)
            
            # Convert positions and set matrix
            res_x = scene.render.resolution_x
            res_y = scene.render.resolution_y
            
            # Convert to screen coordinates like the modal operator does
            region = context.region
            if region and region.view2d:
                view2d = region.view2d
                
                # Position corner handles (0-3) using screen coordinates
                for i in range(4):
                    if i < len(self.gizmos):
                        corner = corners[i]
                        view_x = corner.x - res_x / 2
                        view_y = corner.y - res_y / 2
                        
                        # Convert to screen coordinates (same as modal operator)
                        screen_co = view2d.view_to_region(view_x, view_y, clip=False)
                        
                        print(f"   Corner {i}: strip({corner.x:.1f}, {corner.y:.1f}) -> view({view_x:.1f}, {view_y:.1f}) -> screen({screen_co[0]:.1f}, {screen_co[1]:.1f})")
                        
                        # Use screen coordinates for gizmo positioning
                        self.gizmos[i].matrix_basis = Matrix.Translation((screen_co[0], screen_co[1], 0))
            else:
                print("❌ No region or view2d available for coordinate conversion")
            
        except Exception as e:
            print(f"Simple handle gizmo refresh error: {e}")
            import traceback
            traceback.print_exc()
    
    def draw_prepare(self, context):
        """Prepare for drawing"""
        self.refresh(context)


def register_crop_handles_simple_gizmo():
    """Register the simple crop handles gizmo classes"""
    try:
        print("=== REGISTERING SIMPLE CROP HANDLES GIZMO ===")
        
        bpy.utils.register_class(EASYCROP_GGT_crop_handles_simple)
        print("✓ Registered EASYCROP_GGT_crop_handles_simple")
        
        # Ensure the gizmo group type is active
        try:
            wm = bpy.context.window_manager
            if hasattr(wm, 'gizmo_group_type_ensure'):
                wm.gizmo_group_type_ensure(EASYCROP_GGT_crop_handles_simple.bl_idname)
                print("✓ gizmo_group_type_ensure() called successfully")
        except Exception as e:
            print(f"ℹ gizmo_group_type_ensure() not needed: {e}")
            
        print("=== SIMPLE CROP HANDLES GIZMO REGISTRATION COMPLETE ===")
        return True
        
    except Exception as e:
        print(f"Failed to register simple crop handles gizmo: {e}")
        import traceback
        traceback.print_exc()
        return False


def unregister_crop_handles_simple_gizmo():
    """Unregister the simple crop handles gizmo classes"""
    try:
        print("=== UNREGISTERING SIMPLE CROP HANDLES GIZMO ===")
        
        bpy.utils.unregister_class(EASYCROP_GGT_crop_handles_simple)
        print("✓ Unregistered EASYCROP_GGT_crop_handles_simple")
        
        print("=== SIMPLE CROP HANDLES GIZMO UNREGISTRATION COMPLETE ===")
        
    except Exception as e:
        print(f"Failed to unregister simple crop handles gizmo: {e}")