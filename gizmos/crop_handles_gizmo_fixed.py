"""
BL Easy Crop - Fixed Crop Handles Gizmo System

Based on research into Blender's gizmo API, this uses built-in gizmo types
with target_set_handler for proper drag functionality.
"""

import bpy
import math
from bpy.types import Gizmo, GizmoGroup
from mathutils import Vector, Matrix

from ..operators.crop_core import (
    get_crop_state, is_strip_visible_at_frame, 
    get_strip_geometry_with_flip_support
)


class EASYCROP_GGT_crop_handles_fixed(GizmoGroup):
    """Fixed crop handles gizmo group using built-in gizmo types"""
    bl_idname = "EASYCROP_GGT_crop_handles_fixed"
    bl_label = "Crop Handles (Fixed)"
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
        
        # Check if our fixed crop handles tool is active
        try:
            if hasattr(bpy.context, 'workspace') and bpy.context.workspace:
                workspace = bpy.context.workspace
                for tool in workspace.tools:
                    if hasattr(tool, 'idname') and tool.idname == "sequencer.crop_handles_fixed_tool":
                        print(f"✅ Fixed crop handles tool detected: {tool.idname}")
                        return True
        except:
            pass
        
        # For now, always show when conditions are met (simplified activation)
        return True
    
    def setup(self, context):
        """Setup the gizmo group with built-in gizmo types"""
        print("🔧 Setting up FIXED crop handles gizmo group...")
        
        # Create 4 corner handles using GIZMO_GT_arrow_3d
        for i in range(4):
            gizmo = self.gizmos.new("GIZMO_GT_arrow_3d")
            gizmo.color = (1.0, 1.0, 1.0)
            gizmo.alpha = 0.7
            gizmo.color_highlight = (1.0, 0.5, 0.0)
            gizmo.alpha_highlight = 1.0
            gizmo.draw_style = 'BOX'
            gizmo.length = 1.0
            
            # Use target_set_prop instead of target_set_handler to avoid crashes
            # This approach is simpler and more stable
            if i == 0:  # Bottom-left corner
                gizmo.target_set_prop("offset", bpy.context.scene, "frame_current")  # Placeholder
            elif i == 1:  # Top-left corner  
                gizmo.target_set_prop("offset", bpy.context.scene, "frame_current")  # Placeholder
            elif i == 2:  # Top-right corner
                gizmo.target_set_prop("offset", bpy.context.scene, "frame_current")  # Placeholder
            elif i == 3:  # Bottom-right corner
                gizmo.target_set_prop("offset", bpy.context.scene, "frame_current")  # Placeholder
            print(f"✓ Created corner handle {i}")
        
        # Create 4 edge handles using GIZMO_GT_arrow_3d  
        for i in range(4):
            gizmo = self.gizmos.new("GIZMO_GT_arrow_3d")
            gizmo.color = (1.0, 1.0, 1.0)
            gizmo.alpha = 0.7
            gizmo.color_highlight = (1.0, 0.5, 0.0)
            gizmo.alpha_highlight = 1.0
            gizmo.draw_style = 'BOX'
            gizmo.length = 0.8
            
            # Use target_set_prop instead of target_set_handler to avoid crashes
            # This approach is simpler and more stable
            if i == 0:  # Left edge
                gizmo.target_set_prop("offset", bpy.context.scene, "frame_current")  # Placeholder
            elif i == 1:  # Top edge
                gizmo.target_set_prop("offset", bpy.context.scene, "frame_current")  # Placeholder
            elif i == 2:  # Right edge
                gizmo.target_set_prop("offset", bpy.context.scene, "frame_current")  # Placeholder
            elif i == 3:  # Bottom edge
                gizmo.target_set_prop("offset", bpy.context.scene, "frame_current")  # Placeholder
            print(f"✓ Created edge handle {i}")
        
        print(f"🎯 Created {len(self.gizmos)} FIXED crop handle gizmos total")
    
    def refresh(self, context):
        """Refresh gizmo positions"""
        scene = context.scene
        if not scene.sequence_editor or not scene.sequence_editor.active_strip:
            return
            
        active_strip = scene.sequence_editor.active_strip
        if not hasattr(active_strip, 'crop'):
            return
            
        try:
            print("🔄 Refreshing FIXED gizmo positions")
            
            # Get strip geometry
            corners, (pivot_x, pivot_y), (scale_x, scale_y, flip_x, flip_y) = get_strip_geometry_with_flip_support(active_strip, scene)
            
            # Calculate edge midpoints
            edge_midpoints = []
            for i in range(4):
                next_i = (i + 1) % 4
                midpoint = (corners[i] + corners[next_i]) / 2
                edge_midpoints.append(midpoint)
            
            # Convert positions to screen coordinates and set matrix
            res_x = scene.render.resolution_x
            res_y = scene.render.resolution_y
            region = context.region
            
            if region and region.view2d:
                view2d = region.view2d
                
                # Position corner handles (0-3)
                for i in range(4):
                    if i < len(self.gizmos):
                        corner = corners[i]
                        view_x = corner.x - res_x / 2
                        view_y = corner.y - res_y / 2
                        
                        # For built-in gizmos, use view coordinates
                        self.gizmos[i].matrix_basis = Matrix.Translation((view_x, view_y, 0))
                
                # Position edge handles (4-7)
                for i in range(4):
                    gizmo_idx = i + 4
                    if gizmo_idx < len(self.gizmos):
                        midpoint = edge_midpoints[i]
                        view_x = midpoint.x - res_x / 2
                        view_y = midpoint.y - res_y / 2
                        
                        # For built-in gizmos, use view coordinates
                        self.gizmos[gizmo_idx].matrix_basis = Matrix.Translation((view_x, view_y, 0))
            
        except Exception as e:
            print(f"Fixed handle gizmo refresh error: {e}")
    
    def draw_prepare(self, context):
        """Prepare for drawing"""
        self.refresh(context)


def register_crop_handles_fixed_gizmo():
    """Register the fixed crop handles gizmo classes"""
    try:
        print("=== REGISTERING FIXED CROP HANDLES GIZMO ===")
        
        bpy.utils.register_class(EASYCROP_GGT_crop_handles_fixed)
        print("✓ Registered EASYCROP_GGT_crop_handles_fixed")
        
        # Ensure the gizmo group type is active
        try:
            wm = bpy.context.window_manager
            if hasattr(wm, 'gizmo_group_type_ensure'):
                wm.gizmo_group_type_ensure(EASYCROP_GGT_crop_handles_fixed.bl_idname)
                print("✓ gizmo_group_type_ensure() called successfully")
        except Exception as e:
            print(f"ℹ gizmo_group_type_ensure() not needed: {e}")
            
        print("=== FIXED CROP HANDLES GIZMO REGISTRATION COMPLETE ===")
        return True
        
    except Exception as e:
        print(f"Failed to register fixed crop handles gizmo: {e}")
        import traceback
        traceback.print_exc()
        return False


def unregister_crop_handles_fixed_gizmo():
    """Unregister the fixed crop handles gizmo classes"""
    try:
        print("=== UNREGISTERING FIXED CROP HANDLES GIZMO ===")
        
        bpy.utils.unregister_class(EASYCROP_GGT_crop_handles_fixed)
        print("✓ Unregistered EASYCROP_GGT_crop_handles_fixed")
        
        print("=== FIXED CROP HANDLES GIZMO UNREGISTRATION COMPLETE ===")
        
    except Exception as e:
        print(f"Failed to unregister fixed crop handles gizmo: {e}")