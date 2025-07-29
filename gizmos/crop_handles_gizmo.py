"""
BL Easy Crop - Crop Handles Gizmo System

A complete gizmo-based cropping system with individual handles for corners and edges.
Based on the modal operator but using gizmos for better integration.
"""

import bpy
import math
import gpu
from gpu_extras.batch import batch_for_shader
from bpy.types import Gizmo, GizmoGroup
from mathutils import Vector, Matrix

from ..operators.crop_core import (
    get_crop_state, is_strip_visible_at_frame, 
    get_strip_geometry_with_flip_support
)


class EASYCROP_GT_crop_handle(Gizmo):
    """Individual crop handle gizmo"""
    bl_idname = "EASYCROP_GT_crop_handle"
    bl_target_properties = ()
    
    def setup(self):
        """Setup the handle gizmo"""
        # Store handle type and index
        self.handle_type = "corner"  # or "edge" or "center"
        self.handle_index = 0
        
        # CRITICAL: Essential properties for always-visible gizmos
        self.use_draw_modal = True
        self.use_draw_select = True  
        self.use_event_handle_all = True
        
        # Prevent hiding
        self.use_select_background = False
        self.use_grab_cursor = True
        
        # CRITICAL: Set visibility properties explicitly
        self.hide = False  # Explicitly show the gizmo
        self.alpha = 0.8  # Ensure visible transparency
        self.alpha_highlight = 1.0
        
        # Set colors for visibility
        self.color = (1.0, 1.0, 1.0)
        self.color_highlight = (1.0, 0.5, 0.0)
        
        # Set gizmo scale to match modal operator
        self.scale_basis = 6.0  # Match modal operator handle size
        
        # Set gizmo to be interactive
        self.select_id = 0  # Will be overridden in group setup
        
        # Note: handle_type and handle_index are set after creation in group setup
    
    def draw_prepare(self, context):
        """Prepare for drawing - ensure gizmo is visible"""
        self.hide = False  # Force visibility
        self.alpha = 0.8 if not self.is_highlight else 1.0
    
    def draw(self, context):
        """Draw the handle gizmo using built-in methods"""
        print(f"🎨 DRAW called for {self.handle_type}[{self.handle_index}] highlight={self.is_highlight}")
        
        # Ensure gizmo is not hidden
        self.hide = False
        
        # Set colors based on state
        if self.is_highlight:
            self.color = self.color_highlight
            self.alpha = self.alpha_highlight
        else:
            self.color = (1.0, 1.0, 1.0)
            self.alpha = 0.8
        
        # Use custom GPU drawing with proper highlight colors
        try:
            # Use the color set by the highlight system
            if self.is_highlight:
                color = (*self.color_highlight, self.alpha_highlight)
            else:
                color = (*self.color, self.alpha)
            
            if self.handle_type == "center":
                # Center handle - use custom crop symbol drawing
                self._draw_crop_symbol(color)
            else:
                # Corner and edge handles - use custom square drawing with highlight color
                self._draw_handle_square(color, context)
                    
            print(f"✅ Successfully drew {self.handle_type}[{self.handle_index}] handle with custom drawing")
                    
        except Exception as e:
            print(f"❌ Custom drawing failed for {self.handle_type}[{self.handle_index}]: {e}")
            import traceback
            traceback.print_exc()
    
    def draw_select(self, context, select_id):
        """Draw during selection/modal operations - keeps handles visible"""
        print(f"🎨 DRAW_SELECT called for {self.handle_type}[{self.handle_index}]")
        self._draw_handle_common(context, during_modal=True)
    
    def _draw_handle_common(self, context, during_modal=False):
        """Common drawing logic for both normal and modal states"""
        if self.handle_type == "center":
            # Center symbol (crop icon) - always white
            color = (1.0, 1.0, 1.0, 0.8)
            if during_modal:
                # Make center slightly more transparent during modal
                color = (1.0, 1.0, 1.0, 0.6)
            self._draw_crop_symbol(color)
        else:
            # Handle using ONLY square drawing for proper appearance
            try:
                # Draw square handles (no circles)
                if self.is_highlight or during_modal:
                    square_color = (1.0, 0.5, 0.0, 1.0)  # Orange when highlighted or during modal
                else:
                    square_color = (1.0, 1.0, 1.0, 0.7)  # White normally
                
                self._draw_handle_square(square_color, context)
                
            except Exception as e:
                print(f"Handle draw error: {e}")
                # Fallback
                color = (1.0, 1.0, 1.0, 0.7)
                self._draw_handle_square(color, context)
    
    
    def _draw_crop_symbol(self, color):
        """Draw the crop symbol (for center handle)"""
        
        try:
            center_pos = self.matrix_basis.translation
            center_x = center_pos.x
            center_y = center_pos.y
            
            # Symbol dimensions - match modal operator exactly
            outer_size = 8
            inner_size = 5
            
            line_shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            gpu.state.line_width_set(1.5)  # Match modal operator exactly
            line_shader.bind()
            line_shader.uniform_float("color", color)
            
            # Corner brackets
            tl_vertical = [(center_x - outer_size, center_y + 1), (center_x - outer_size, center_y + outer_size)]
            tl_horizontal = [(center_x - outer_size, center_y + outer_size), (center_x - 1, center_y + outer_size)]
            br_horizontal = [(center_x + 1, center_y - outer_size), (center_x + outer_size, center_y - outer_size)]
            br_vertical = [(center_x + outer_size, center_y - outer_size), (center_x + outer_size, center_y - 1)]
            
            # Inner viewing rectangle
            inner_rect_lines = [
                [(center_x - inner_size, center_y - inner_size), (center_x + inner_size, center_y - inner_size)],
                [(center_x + inner_size, center_y - inner_size), (center_x + inner_size, center_y + inner_size)],
                [(center_x + inner_size, center_y + inner_size), (center_x - inner_size, center_y + inner_size)],
                [(center_x - inner_size, center_y + inner_size), (center_x - inner_size, center_y - inner_size)]
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
            print(f"Crop symbol draw error: {e}")
    
    def _draw_handle_square(self, color, context):
        """Draw a handle square (for corner and edge handles) with rotation - match modal operator exactly"""
        
        try:
            center_pos = self.matrix_basis.translation
            center_x = center_pos.x
            center_y = center_pos.y
            
            # Handle size - match modal operator exactly
            size = 6
            
            # Get rotation directly from strip like modal operator does
            strip = context.scene.sequence_editor.active_strip
            rotation_angle = 0
            if strip:
                if hasattr(strip, 'rotation_start'):
                    rotation_angle = math.radians(strip.rotation_start)
                elif hasattr(strip, 'rotation'):
                    rotation_angle = strip.rotation
                elif hasattr(strip, 'transform') and hasattr(strip.transform, 'rotation'):
                    rotation_angle = strip.transform.rotation
            
            # Apply rotation to square vertices like modal operator
            if abs(rotation_angle) > 0.01:  # If there's meaningful rotation
                cos_a = math.cos(rotation_angle)
                sin_a = math.sin(rotation_angle)
                
                # Define square corners relative to center
                corners_rel = [
                    (-size, -size), (size, -size), (size, size), (-size, size)
                ]
                
                # Rotate and translate
                vertices = []
                for x_rel, y_rel in corners_rel:
                    x = x_rel * cos_a - y_rel * sin_a + center_x
                    y = x_rel * sin_a + y_rel * cos_a + center_y
                    vertices.append((x, y))
                
                # Reorder vertices like modal operator for proper triangle winding
                vertices = [vertices[0], vertices[1], vertices[3], vertices[2]]
            else:
                # No rotation - regular square
                vertices = [
                    (center_x - size, center_y - size),
                    (center_x + size, center_y - size),
                    (center_x - size, center_y + size),
                    (center_x + size, center_y + size)
                ]
            
            indices = ((0, 1, 2), (2, 1, 3))
            
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
            shader.bind()
            shader.uniform_float("color", color)
            batch.draw(shader)
            
        except Exception as e:
            print(f"Handle square draw error: {e}")
    
    # Removed _get_strip_rotation method - now getting rotation directly like modal operator
    
    def test_select(self, context, event):
        """Test if point is over this gizmo"""
        # Use a simple distance check - but only return select_id if we're actually close
        gizmo_pos = self.matrix_basis.translation
        mouse_pos = event  # event is (x, y) tuple
        
        distance = ((gizmo_pos.x - mouse_pos[0])**2 + (gizmo_pos.y - mouse_pos[1])**2)**0.5
        threshold = 25  # Generous threshold
        
        if distance <= threshold:
            print(f"✅ Gizmo {self.handle_type}[{self.handle_index}] hit at distance {distance}")
            return self.select_id
        else:
            return -1
    
    def select(self, context, event):
        """Handle gizmo selection/click"""
        print(f"🎯 GIZMO SELECT CALLED: {self.handle_type}[{self.handle_index}]")
        return True  # Allow selection
    
    def invoke(self, context, event):
        """Start handle dragging"""
        print(f"🟢 GIZMO INVOKE CALLED: {self.handle_type}[{self.handle_index}] at screen pos ({event.mouse_region_x}, {event.mouse_region_y})")
        print(f"   Event type: {event.type}, value: {event.value}")
        print(f"   🎨 use_draw_select = {getattr(self, 'use_draw_select', 'NOT_SET')}")
        
        if self.handle_type == "center":
            # Center handle starts modal crop mode (like current single gizmo)
            try:
                print("🎯 Center handle clicked - starting modal crop mode")
                bpy.ops.sequencer.crop('INVOKE_DEFAULT')
                return {'FINISHED'}
            except Exception as e:
                print(f"❌ Failed to start modal crop: {e}")
                return {'CANCELLED'}
        else:
            # Start crop handle drag - store initial values like modal operator
            print(f"🟡 Starting crop handle drag for {self.handle_type}[{self.handle_index}]")
            
            # CRITICAL: Store initial mouse position for delta calculation
            self.init_mouse_pos = (event.mouse_region_x, event.mouse_region_y)
            print(f"📍 Initial mouse position: {self.init_mouse_pos}")
            
            # Mark drag as active to prevent gizmo repositioning
            EASYCROP_GGT_crop_handles._drag_active = True
            
            # CRITICAL: Disable transform gizmos during crop drag
            try:
                if hasattr(context.space_data, 'show_gizmo'):
                    self._saved_gizmo_state = context.space_data.show_gizmo
                    context.space_data.show_gizmo = False
                    print("🚫 Disabled transform gizmos during crop drag")
            except Exception as e:
                print(f"⚠️ Could not disable transform gizmos: {e}")
            
            # RE-ENABLE modal drawing handler to keep handles visible during drag
            try:
                self._modal_draw_handler = bpy.types.SpaceSequenceEditor.draw_handler_add(
                    self._draw_handles_during_modal, (), 'PREVIEW', 'POST_PIXEL')
                print("🎨 Added modal drawing handler for drag visibility")
            except Exception as e:
                print(f"⚠️ Could not add modal drawing handler: {e}")
            
            # Store initial crop values for this drag operation (like modal operator)
            strip = context.scene.sequence_editor.active_strip
            if strip and hasattr(strip, 'crop') and strip.crop:
                self.crop_start = (strip.crop.min_x, strip.crop.max_x, strip.crop.min_y, strip.crop.max_y)
                print(f"📝 Stored initial crop values: {self.crop_start}")
            else:
                self.crop_start = (0, 0, 0, 0)
                print("⚠️ No crop data found - using defaults")
                
            print("🔥 RETURNING RUNNING_MODAL - should start dragging")
            return {'RUNNING_MODAL'}
    
    def modal(self, context, event, tweak):
        """Handle dragging modal operation"""
        if self.handle_type == "center":
            return {'FINISHED'}
        
        print(f"🔄 GIZMO MODAL CALLED: {self.handle_type}[{self.handle_index}]")
        print(f"   Event type: {event.type}, value: {event.value}")
        print(f"   Mouse pos: ({event.mouse_region_x}, {event.mouse_region_y})")
        
        # Calculate delta from initial position - tweak object varies
        if hasattr(self, 'init_mouse_pos'):
            current_mouse = (event.mouse_region_x, event.mouse_region_y)
            delta = (current_mouse[0] - self.init_mouse_pos[0], current_mouse[1] - self.init_mouse_pos[1])
            print(f"   Calculated delta: {delta}")
        else:
            # Fallback to zero delta if no initial position stored
            delta = (0, 0)
            print(f"   No initial position - using zero delta")
        
        # CORRECT APPROACH: Update crop values, NOT gizmo position
        # The gizmos should stay put while the strip gets smaller/larger
        try:
            strip = context.scene.sequence_editor.active_strip
            if strip and hasattr(strip, 'crop'):
                print(f"📊 Before crop update: min_x={strip.crop.min_x}, max_x={strip.crop.max_x}, min_y={strip.crop.min_y}, max_y={strip.crop.max_y}")
                
                # Update crop values (this will make the strip smaller/larger)
                self._update_crop_from_gizmo_drag(context, delta, strip)
                
                print(f"📈 After crop update: min_x={strip.crop.min_x}, max_x={strip.crop.max_x}, min_y={strip.crop.min_y}, max_y={strip.crop.max_y}")
                
                # Force redraw to show the cropping effect
                for area in context.screen.areas:
                    if area.type == 'SEQUENCE_EDITOR':
                        area.tag_redraw()
                
                # The drawing handler should be handling the handle visibility
                        
                # DON'T move the gizmo - it should stay at the crop boundary
                # This is the key difference from strip transform
                        
            else:
                print("❌ No strip or crop data found in modal")
                
        except Exception as e:
            print(f"❌ Gizmo crop update error: {e}")
            import traceback
            traceback.print_exc()
        
        return {'RUNNING_MODAL'}
    
    def _draw_handles_during_modal(self):
        """Custom drawing function to keep handles visible during modal"""
        try:
            # Get current context - this is tricky in a drawing handler
            import bpy
            context = bpy.context
            
            # Draw all handles manually using GPU drawing
            scene = context.scene
            if not scene.sequence_editor or not scene.sequence_editor.active_strip:
                return
                
            active_strip = scene.sequence_editor.active_strip
            if not hasattr(active_strip, 'crop'):
                return
            
            # Use direct GPU drawing to ensure handles are visible
            self._draw_handles_with_gpu(context, active_strip, scene)
                
        except Exception as e:
            print(f"⚠️ Modal drawing error: {e}")
    
    def _draw_handles_with_gpu(self, context, strip, scene):
        """Draw handles directly with GPU during modal operations"""
        try:
            from ..operators.crop_core import get_strip_geometry_with_flip_support
            
            # Get strip geometry
            corners, (pivot_x, pivot_y), (scale_x, scale_y, flip_x, flip_y) = get_strip_geometry_with_flip_support(strip, scene)
            
            # Calculate edge midpoints
            edge_midpoints = []
            for i in range(4):
                next_i = (i + 1) % 4
                midpoint = (corners[i] + corners[next_i]) / 2
                edge_midpoints.append(midpoint)
            
            # Convert to screen coordinates
            region = context.region
            if not region or not region.view2d:
                return
                
            view2d = region.view2d
            res_x = scene.render.resolution_x
            res_y = scene.render.resolution_y
            
            # Get shader for drawing
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            gpu.state.blend_set('ALPHA')
            
            # Get which handle is being dragged (stored in handle_type and handle_index)
            active_handle_type = getattr(self, 'handle_type', None)
            active_handle_index = getattr(self, 'handle_index', None)
            
            # Also check for hover state from the gizmo system
            is_highlighted = getattr(self, 'is_highlight', False)
            
            # Draw corner handles (squares)
            for i, corner in enumerate(corners):
                view_x = corner.x - res_x / 2
                view_y = corner.y - res_y / 2
                screen_co = view2d.view_to_region(view_x, view_y, clip=False)
                
                if screen_co:
                    # Color priority: Active (dragging) > Hovered > Normal
                    if active_handle_type == "corner" and active_handle_index == i:
                        color = (1.0, 0.5, 0.0, 1.0)  # Orange for active (dragging) handle
                    elif is_highlighted and active_handle_type == "corner" and active_handle_index == i:
                        color = (1.0, 0.5, 0.0, 0.8)  # Orange for hovered handle
                    else:
                        color = (1.0, 1.0, 1.0, 0.8)  # White for inactive handles
                    self._draw_square_at_position(shader, screen_co, color, 13)
            
            # Draw edge handles (squares)
            for i, midpoint in enumerate(edge_midpoints):
                view_x = midpoint.x - res_x / 2
                view_y = midpoint.y - res_y / 2
                screen_co = view2d.view_to_region(view_x, view_y, clip=False)
                
                if screen_co:
                    # Color priority: Active (dragging) > Hovered > Normal
                    if active_handle_type == "edge" and active_handle_index == i:
                        color = (1.0, 0.5, 0.0, 1.0)  # Orange for active (dragging) handle
                    elif is_highlighted and active_handle_type == "edge" and active_handle_index == i:
                        color = (1.0, 0.5, 0.0, 0.8)  # Orange for hovered handle
                    else:
                        color = (1.0, 1.0, 1.0, 0.8)  # White for inactive handles
                    self._draw_square_at_position(shader, screen_co, color, 13)
            
            # Draw center handle (crop symbol)
            center_view_x = pivot_x - res_x / 2
            center_view_y = pivot_y - res_y / 2
            center_screen = view2d.view_to_region(center_view_x, center_view_y, clip=False)
            
            if center_screen:
                self._draw_crop_symbol_at_position(shader, center_screen, (1.0, 1.0, 1.0, 0.8))
            
            print(f"🎨 Successfully drew {len(corners)} corner + {len(edge_midpoints)} edge + 1 center handles with GPU")
            
        except Exception as e:
            print(f"⚠️ GPU drawing error: {e}")
            import traceback
            traceback.print_exc()
    
    def _draw_square_at_position(self, shader, position, color, size):
        """Draw a square handle at the given screen position with rotation like modal operator"""
        try:
            x, y = position
            half_size = size / 2
            
            # This is used during modal drawing - apply rotation like modal operator
            context = bpy.context
            strip = context.scene.sequence_editor.active_strip
            angle = 0
            if strip:
                if hasattr(strip, 'rotation_start'):
                    angle = math.radians(strip.rotation_start)
                elif hasattr(strip, 'rotation'):
                    angle = strip.rotation
                elif hasattr(strip, 'transform') and hasattr(strip.transform, 'rotation'):
                    angle = strip.transform.rotation
            
            # Create rotated square vertices exactly like modal operator  
            if abs(angle) > 0.01:  # If strip is rotated
                cos_a = math.cos(angle)
                sin_a = math.sin(angle)
                
                # Define square corners relative to center - match modal operator exactly
                corners_rel = [
                    (-half_size, -half_size), (half_size, -half_size), 
                    (half_size, half_size), (-half_size, half_size)
                ]
                
                # Rotate and translate
                vertices = []
                for x_rel, y_rel in corners_rel:
                    rot_x = x_rel * cos_a - y_rel * sin_a + x
                    rot_y = x_rel * sin_a + y_rel * cos_a + y
                    vertices.append((rot_x, rot_y))
                
                # Reorder vertices like modal operator for proper winding
                vertices = [vertices[0], vertices[1], vertices[3], vertices[2]]
            else:
                # No rotation - regular square
                vertices = [
                    (x - half_size, y - half_size),
                    (x + half_size, y - half_size),
                    (x - half_size, y + half_size),
                    (x + half_size, y + half_size)
                ]
            
            indices = [(0, 1, 2), (2, 1, 3)]
            
            batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
            shader.bind()
            shader.uniform_float("color", color)
            batch.draw(shader)
            
        except Exception as e:
            print(f"⚠️ Square drawing error: {e}")
    
    def _draw_crop_symbol_at_position(self, shader, position, color):
        """Draw crop symbol at the given screen position"""
        try:
            x, y = position
            size = 8  # Match modal operator exactly
            
            # Draw simple cross for crop symbol
            # Horizontal line
            h_vertices = [(x - size, y), (x + size, y), (x + size, y + 1), (x - size, y + 1)]
            h_indices = [(0, 1, 2), (2, 3, 0)]
            
            # Vertical line  
            v_vertices = [(x, y - size), (x + 1, y - size), (x + 1, y + size), (x, y + size)]
            v_indices = [(0, 1, 2), (2, 3, 0)]
            
            # Draw horizontal line
            batch_h = batch_for_shader(shader, 'TRIS', {"pos": h_vertices}, indices=h_indices)
            shader.bind()
            shader.uniform_float("color", color)
            batch_h.draw(shader)
            
            # Draw vertical line
            batch_v = batch_for_shader(shader, 'TRIS', {"pos": v_vertices}, indices=v_indices)
            batch_v.draw(shader)
            
        except Exception as e:
            print(f"⚠️ Crop symbol drawing error: {e}")
    
    
    def exit(self, context, cancel):
        """Handle gizmo exit"""
        if self.handle_type != "center":
            print(f"🏁 Gizmo drag finished for {self.handle_type}[{self.handle_index}], cancelled: {cancel}")
            
            # Clear drag state to allow gizmo repositioning again
            EASYCROP_GGT_crop_handles._drag_active = False
            
            # Remove modal drawing handler
            try:
                if hasattr(self, '_modal_draw_handler') and self._modal_draw_handler:
                    bpy.types.SpaceSequenceEditor.draw_handler_remove(self._modal_draw_handler, 'PREVIEW')
                    self._modal_draw_handler = None
                    print("🎨 Removed modal drawing handler")
            except Exception as e:
                print(f"⚠️ Could not remove modal drawing handler: {e}")
            
            # Restore transform gizmos
            try:
                if hasattr(self, '_saved_gizmo_state') and hasattr(context.space_data, 'show_gizmo'):
                    context.space_data.show_gizmo = self._saved_gizmo_state
                    print("✅ Restored transform gizmos after crop drag")
            except Exception as e:
                print(f"⚠️ Could not restore transform gizmos: {e}")
            
            # If cancelled, restore original crop values (like modal operator ESC)
            if cancel and hasattr(self, 'crop_start'):
                strip = context.scene.sequence_editor.active_strip
                if strip and hasattr(strip, 'crop') and strip.crop:
                    print(f"🔄 Restoring crop values: {self.crop_start}")
                    strip.crop.min_x = int(self.crop_start[0])
                    strip.crop.max_x = int(self.crop_start[1])
                    strip.crop.min_y = int(self.crop_start[2])
                    strip.crop.max_y = int(self.crop_start[3])
                    
                    # Force redraw to show restored values
                    for area in context.screen.areas:
                        if area.type == 'SEQUENCE_EDITOR':
                            area.tag_redraw()
            else:
                print("✅ Crop drag completed successfully")
    
    def _update_crop_from_gizmo_drag(self, context, delta, strip):
        """Update crop values from gizmo drag (adapted from modal operator)"""
        scene = context.scene
        
        # Gizmo delta is already in screen pixel space, not normalized
        dx = delta[0]  # Screen space delta x in pixels
        dy = delta[1]  # Screen space delta y in pixels
        
        # Convert screen delta to view space (same as modal operator)
        region = context.region
        if not region or not region.view2d:
            return
            
        view2d = region.view2d
        # Convert screen pixel delta to view space delta
        p1 = view2d.region_to_view(0, 0)
        p2 = view2d.region_to_view(dx, dy)
        
        dx_view = p2[0] - p1[0]
        dy_view = p2[1] - p1[1]
        
        # Get strip properties (same as modal operator)
        strip_scale_x = strip.transform.scale_x if hasattr(strip, 'transform') and hasattr(strip.transform, 'scale_x') else 1.0
        strip_scale_y = strip.transform.scale_y if hasattr(strip, 'transform') and hasattr(strip.transform, 'scale_y') else 1.0
        
        # Check for flip states (same as modal operator)
        flip_x = False
        flip_y = False
        
        for attr_name in ['use_flip_x', 'flip_x', 'mirror_x']:
            if hasattr(strip, attr_name):
                flip_x = getattr(strip, attr_name)
                break
        
        for attr_name in ['use_flip_y', 'flip_y', 'mirror_y']:
            if hasattr(strip, attr_name):
                flip_y = getattr(strip, attr_name)
                break
        
        # Handle rotation (same as modal operator)
        angle = 0
        if hasattr(strip, 'rotation_start'):
            angle = -math.radians(strip.rotation_start)
        elif hasattr(strip, 'transform') and hasattr(strip.transform, 'rotation'):
            angle = -strip.transform.rotation
        
        # Adjust rotation for flip
        if flip_x != flip_y:
            angle = -angle
        
        # Apply rotation to delta
        if angle != 0:
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)
            rotated_dx = dx_view * cos_a - dy_view * sin_a
            rotated_dy = dx_view * sin_a + dy_view * cos_a
            dx_view = rotated_dx
            dy_view = rotated_dy
        
        # Convert to strip's original image space
        dx_res = dx_view / strip_scale_x
        dy_res = dy_view / strip_scale_y
        
        # Invert deltas for flipped strips
        if flip_x:
            dx_res = -dx_res
        if flip_y:
            dy_res = -dy_res
        
        # Get strip dimensions
        strip_width = scene.render.resolution_x
        strip_height = scene.render.resolution_y
        
        if hasattr(strip, 'elements') and strip.elements and len(strip.elements) > 0:
            elem = strip.elements[0]
            if hasattr(elem, 'orig_width') and hasattr(elem, 'orig_height'):
                strip_width = elem.orig_width
                strip_height = elem.orig_height
        
        # Apply crop changes based on handle type and index
        self._apply_gizmo_crop_changes(strip, dx_res, dy_res, strip_width, strip_height, flip_x, flip_y)
    
    def _apply_gizmo_crop_changes(self, strip, dx_res, dy_res, strip_width, strip_height, flip_x, flip_y):
        """Apply crop changes based on gizmo handle (adapted from modal operator)"""
        # CRITICAL FIX: Use stored initial values, not current crop values
        # This is the key difference from the old buggy approach
        
        if self.handle_type == "corner":
            # Corner handles - remap based on flips (same as modal operator)
            corner_map = self.handle_index
            
            # IMPORTANT: Apply the same flip remapping as the modal operator
            if flip_x and flip_y:
                corner_remap = {0: 2, 1: 3, 2: 0, 3: 1}
                corner_map = corner_remap[self.handle_index]
            elif flip_x:
                corner_remap = {0: 3, 1: 2, 2: 1, 3: 0}
                corner_map = corner_remap[self.handle_index]
            elif flip_y:
                corner_remap = {0: 1, 1: 0, 2: 3, 3: 2}
                corner_map = corner_remap[self.handle_index]
            
            print(f"🔄 Corner remap: {self.handle_index} -> {corner_map} (flip_x={flip_x}, flip_y={flip_y})")
            
            # Apply crop changes based on remapped corner - using stored initial values
            if corner_map == 0:  # Bottom-left
                new_min_x = int(max(0, self.crop_start[0] + dx_res))
                if new_min_x + strip.crop.max_x < strip_width:
                    strip.crop.min_x = new_min_x
                
                new_min_y = int(max(0, self.crop_start[2] + dy_res))
                if new_min_y + strip.crop.max_y < strip_height:
                    strip.crop.min_y = new_min_y
                        
            elif corner_map == 1:  # Top-left
                new_min_x = int(max(0, self.crop_start[0] + dx_res))
                if new_min_x + strip.crop.max_x < strip_width:
                    strip.crop.min_x = new_min_x
                
                new_max_y = int(max(0, self.crop_start[3] - dy_res))
                if strip.crop.min_y + new_max_y < strip_height:
                    strip.crop.max_y = new_max_y
                        
            elif corner_map == 2:  # Top-right
                new_max_x = int(max(0, self.crop_start[1] - dx_res))
                if strip.crop.min_x + new_max_x < strip_width:
                    strip.crop.max_x = new_max_x
                
                new_max_y = int(max(0, self.crop_start[3] - dy_res))
                if strip.crop.min_y + new_max_y < strip_height:
                    strip.crop.max_y = new_max_y
                        
            elif corner_map == 3:  # Bottom-right
                new_max_x = int(max(0, self.crop_start[1] - dx_res))
                if strip.crop.min_x + new_max_x < strip_width:
                    strip.crop.max_x = new_max_x
                
                new_min_y = int(max(0, self.crop_start[2] + dy_res))
                if new_min_y + strip.crop.max_y < strip_height:
                    strip.crop.min_y = new_min_y
                    
        elif self.handle_type == "edge":
            # Edge handles - remap based on flips (same as modal operator)
            edge_index = self.handle_index
            edge_map = edge_index
            
            # IMPORTANT: Apply the same flip remapping as the modal operator
            if flip_x and flip_y:
                edge_remap = {0: 2, 1: 3, 2: 0, 3: 1}
                edge_map = edge_remap[edge_index]
            elif flip_x:
                edge_remap = {0: 2, 1: 1, 2: 0, 3: 3}
                edge_map = edge_remap[edge_index]
            elif flip_y:
                edge_remap = {0: 0, 1: 3, 2: 2, 3: 1}
                edge_map = edge_remap[edge_index]
            
            print(f"🔄 Edge remap: {edge_index} -> {edge_map} (flip_x={flip_x}, flip_y={flip_y})")
            
            # Apply crop changes based on remapped edge - using stored initial values
            if edge_map == 0:  # Left edge
                new_min_x = int(max(0, self.crop_start[0] + dx_res))
                if new_min_x + strip.crop.max_x < strip_width:
                    strip.crop.min_x = new_min_x
                        
            elif edge_map == 1:  # Top edge
                new_max_y = int(max(0, self.crop_start[3] - dy_res))
                if strip.crop.min_y + new_max_y < strip_height:
                    strip.crop.max_y = new_max_y
                        
            elif edge_map == 2:  # Right edge
                new_max_x = int(max(0, self.crop_start[1] - dx_res))
                if strip.crop.min_x + new_max_x < strip_width:
                    strip.crop.max_x = new_max_x
                        
            elif edge_map == 3:  # Bottom edge
                new_min_y = int(max(0, self.crop_start[2] + dy_res))
                if new_min_y + strip.crop.max_y < strip_height:
                    strip.crop.min_y = new_min_y


class EASYCROP_GGT_crop_handles(GizmoGroup):
    """Crop handles gizmo group - full handle system"""
    bl_idname = "EASYCROP_GGT_crop_handles"
    bl_label = "Crop Handles"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'PREVIEW'
    bl_options = {'SHOW_MODAL_ALL', 'PERSISTENT', 'SCALE'}
    
    # Class variable to track if any gizmo is being dragged
    _drag_active = False
    
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
        
        # IMPORTANT: Only show for SELECTED strips (fixes disappearing when deselected)
        if not active_strip.select:
            return False
            
        # Only show for visible strips
        current_frame = context.scene.frame_current
        if not is_strip_visible_at_frame(active_strip, current_frame):
            return False
        
        # Don't show if modal crop mode is already active (avoid conflicts)
        crop_state = get_crop_state()
        if crop_state['active']:
            return False
        
        # Check if crop handles tool is active (toolbar button clicked)
        try:
            # Method 1: Check workspace tool via bpy.context
            if hasattr(bpy.context, 'workspace') and bpy.context.workspace:
                workspace = bpy.context.workspace
                
                # Check active tool in sequencer space
                if hasattr(workspace, 'tools') and workspace.tools:
                    # Try to get the active tool for sequencer preview
                    for tool in workspace.tools:
                        if hasattr(tool, 'idname') and tool.idname == "sequencer.crop_handles_tool":
                            return True
            
            # Method 2: Check via context.tool_settings if available
            if hasattr(context, 'tool_settings'):
                # This approach might work in some cases
                pass
                
        except Exception as e:
            print(f"Tool detection error: {e}")
        
        # Only show gizmos when explicitly activated via toolbar
        try:
            if hasattr(bpy.context, 'workspace') and bpy.context.workspace:
                workspace = bpy.context.workspace
                for tool in workspace.tools:
                    if hasattr(tool, 'idname') and tool.idname == "sequencer.crop_handles_tool":
                        return True
        except:
            pass
        
        return False
    
    def setup(self, context):
        """Setup the gizmo group with all handles"""
        print("🔧 Setting up crop handles gizmo group...")
        
        # Create corner handles (4)
        for i in range(4):
            gizmo = self.gizmos.new(EASYCROP_GT_crop_handle.bl_idname)
            # Set properties AFTER creation but BEFORE setup calls
            gizmo.handle_type = "corner"
            gizmo.handle_index = i
            gizmo.select_id = i
            
            # CRITICAL: Configure gizmo for drag interaction
            gizmo.use_event_handle_all = True
            gizmo.use_draw_modal = True  
            gizmo.use_grab_cursor = True
            gizmo.use_draw_select = True  # Enable select drawing for visibility during modal
            
            print(f"✓ Created corner handle {i} with type={gizmo.handle_type}, index={gizmo.handle_index}")
        
        # Create edge handles (4)  
        for i in range(4):
            gizmo = self.gizmos.new(EASYCROP_GT_crop_handle.bl_idname)
            # Set properties AFTER creation but BEFORE setup calls
            gizmo.handle_type = "edge"
            gizmo.handle_index = i
            gizmo.select_id = i + 4
            
            # CRITICAL: Configure gizmo for drag interaction
            gizmo.use_event_handle_all = True
            gizmo.use_draw_modal = True
            gizmo.use_grab_cursor = True
            gizmo.use_draw_select = True  # Enable select drawing for visibility during modal
            
            print(f"✓ Created edge handle {i} with type={gizmo.handle_type}, index={gizmo.handle_index}")
        
        # Create center handle (1)
        gizmo = self.gizmos.new(EASYCROP_GT_crop_handle.bl_idname)
        # Set properties AFTER creation but BEFORE setup calls
        gizmo.handle_type = "center"
        gizmo.handle_index = 0
        gizmo.select_id = 8
        
        # Center handle needs click handling but not dragging
        gizmo.use_event_handle_all = True
        gizmo.use_draw_select = True  # Enable select drawing
        print(f"✓ Created center handle with type={gizmo.handle_type}, index={gizmo.handle_index}")
        
        print(f"🎯 Created {len(self.gizmos)} crop handle gizmos total")
    
    def refresh(self, context):
        """Refresh gizmo positions"""
        # CRITICAL: Don't reposition gizmos during active drag!
        # This prevents the "all gizmos move with strip" issue
        if self._drag_active:
            print("🚫 Skipping gizmo refresh during drag")
            return
            
        scene = context.scene
        if not scene.sequence_editor or not scene.sequence_editor.active_strip:
            return
            
        active_strip = scene.sequence_editor.active_strip
        if not hasattr(active_strip, 'crop'):
            return
            
        try:
            print("🔄 Refreshing gizmo positions (no drag active)")
            
            # Get strip geometry (same as modal operator)
            corners, (pivot_x, pivot_y), (scale_x, scale_y, flip_x, flip_y) = get_strip_geometry_with_flip_support(active_strip, scene)
            
            # Calculate edge midpoints (same as modal operator)
            edge_midpoints = []
            for i in range(4):
                next_i = (i + 1) % 4
                midpoint = (corners[i] + corners[next_i]) / 2
                edge_midpoints.append(midpoint)
            
            # Convert all positions to screen coordinates
            res_x = scene.render.resolution_x
            res_y = scene.render.resolution_y
            region = context.region
            
            if region and region.view2d:
                view2d = region.view2d
                
                # Position handles exactly like modal operator - no visual mapping at positioning level
                # The flip remapping happens during crop value updates, not handle positioning
                
                # Convert corners to screen coordinates for rotation calculation
                screen_corners = []
                for corner in corners:
                    view_x = corner.x - res_x / 2
                    view_y = corner.y - res_y / 2
                    screen_co = view2d.view_to_region(view_x, view_y, clip=False)
                    screen_corners.append(Vector(screen_co))
                
                # Position corner handles (0-3) with geometry-based rotation like modal operator
                for i in range(4):
                    if i < len(self.gizmos):
                        screen_co = screen_corners[i]
                        
                        # Calculate rotation based on geometry like fixed modal operator
                        rotation_angle = 0
                        
                        # Check if we need rotation (same threshold as modal operator)
                        raw_angle = 0
                        if hasattr(active_strip, 'rotation_start'):
                            raw_angle = math.radians(active_strip.rotation_start)
                        elif hasattr(active_strip, 'transform') and hasattr(active_strip.transform, 'rotation'):
                            raw_angle = active_strip.transform.rotation
                        
                        if abs(raw_angle) > 0.01:  # If strip is rotated
                            # Use geometry-based calculation like modal operator corner handles
                            corner_idx = i
                            next_edge_idx = corner_idx
                            corner1_idx = next_edge_idx  
                            corner2_idx = (next_edge_idx + 1) % 4
                            
                            next_edge_vec = screen_corners[corner2_idx] - screen_corners[corner1_idx]
                            next_edge_angle = math.atan2(next_edge_vec.y, next_edge_vec.x)
                            rotation_angle = next_edge_angle - math.pi / 2  # Same calculation as modal operator
                        
                        # Create transformation matrix with geometry-based rotation
                        transform_matrix = Matrix.Translation((screen_co[0], screen_co[1], 0))
                        if abs(rotation_angle) > 0.01:  # Only apply rotation if significant
                            rotation_matrix = Matrix.Rotation(rotation_angle, 4, 'Z')  # Normal rotation with strip
                            transform_matrix = transform_matrix @ rotation_matrix
                        
                        self.gizmos[i].matrix_basis = transform_matrix
                        
                        # CRITICAL: Force visibility
                        self.gizmos[i].hide = False
                        self.gizmos[i].alpha = 0.8
                        print(f"📍 Corner {i}: view({screen_co[0]:.1f}, {screen_co[1]:.1f}) -> screen({screen_co[0]:.1f}, {screen_co[1]:.1f}) [geom_angle={math.degrees(rotation_angle):.1f}°, flip_x={flip_x}, flip_y={flip_y}]")
                
                # Position edge handles (4-7) with geometry-based rotation like modal operator
                for i in range(4):
                    gizmo_idx = i + 4
                    if gizmo_idx < len(self.gizmos):
                        midpoint = edge_midpoints[i]
                        view_x = midpoint.x - res_x / 2
                        view_y = midpoint.y - res_y / 2
                        # Convert to screen coordinates like the modal operator does
                        screen_co = view2d.view_to_region(view_x, view_y, clip=False)
                        
                        # Calculate rotation based on geometry like modal operator edge handles
                        rotation_angle = 0
                        
                        # Check if we need rotation (same threshold as modal operator)
                        raw_angle = 0
                        if hasattr(active_strip, 'rotation_start'):
                            raw_angle = math.radians(active_strip.rotation_start)
                        elif hasattr(active_strip, 'transform') and hasattr(active_strip.transform, 'rotation'):
                            raw_angle = active_strip.transform.rotation
                        
                        if abs(raw_angle) > 0.01:  # If strip is rotated
                            # Use geometry-based calculation like modal operator edge handles
                            edge_idx = i
                            corner1_idx = edge_idx
                            corner2_idx = (edge_idx + 1) % 4
                            
                            # Get edge angle in screen space
                            edge_vec = screen_corners[corner2_idx] - screen_corners[corner1_idx]
                            edge_angle = math.atan2(edge_vec.y, edge_vec.x)
                            rotation_angle = edge_angle - math.pi / 2  # Same calculation as modal operator
                        
                        # Create transformation matrix with geometry-based rotation
                        transform_matrix = Matrix.Translation((screen_co[0], screen_co[1], 0))
                        if abs(rotation_angle) > 0.01:  # Only apply rotation if significant
                            rotation_matrix = Matrix.Rotation(rotation_angle, 4, 'Z')  # Normal rotation with strip
                            transform_matrix = transform_matrix @ rotation_matrix
                        
                        self.gizmos[gizmo_idx].matrix_basis = transform_matrix
                        
                        # CRITICAL: Force visibility
                        self.gizmos[gizmo_idx].hide = False
                        self.gizmos[gizmo_idx].alpha = 0.8
                        print(f"📍 Edge {i}: view({view_x:.1f}, {view_y:.1f}) -> screen({screen_co[0]:.1f}, {screen_co[1]:.1f}) [geom_angle={math.degrees(rotation_angle):.1f}°, flip_x={flip_x}, flip_y={flip_y}]")
                
                # Position center handle (8)
                if len(self.gizmos) > 8:
                    view_x = pivot_x - res_x / 2
                    view_y = pivot_y - res_y / 2
                    # Convert to screen coordinates like the modal operator does
                    screen_co = view2d.view_to_region(view_x, view_y, clip=False)
                    self.gizmos[8].matrix_basis = Matrix.Translation((screen_co[0], screen_co[1], 0))
                    
                    # CRITICAL: Force visibility
                    self.gizmos[8].hide = False
                    self.gizmos[8].alpha = 0.8
                    print(f"📍 Center: view({view_x:.1f}, {view_y:.1f}) -> screen({screen_co[0]:.1f}, {screen_co[1]:.1f})")
            
        except Exception as e:
            print(f"Handle gizmo refresh error: {e}")
    
    def draw_prepare(self, context):
        """Prepare for drawing"""
        self.refresh(context)
    
    def draw_select(self, context):
        """Draw during modal operations - ensure handles stay visible"""
        print(f"🎨 GROUP DRAW_SELECT called for {len(self.gizmos)} gizmos")
        # Force all handles to draw during modal operations
        # This helps keep non-active handles visible during drag operations
        try:
            # Get strip geometry for drawing all handles
            scene = context.scene
            if scene.sequence_editor and scene.sequence_editor.active_strip:
                active_strip = scene.sequence_editor.active_strip
                if hasattr(active_strip, 'crop'):
                    # Draw all handles manually during modal
                    self._draw_all_handles_manual(context, during_modal=True)
        except Exception as e:
            print(f"Error drawing handles during modal: {e}")
    
    def _draw_all_handles_manual(self, context, during_modal=False):
        """Manually draw all handles - fallback for modal operations"""
        try:
            for i, gizmo in enumerate(self.gizmos):
                if hasattr(gizmo, '_draw_handle_common'):
                    print(f"  🎨 Manually drawing gizmo {i} ({gizmo.handle_type}[{gizmo.handle_index}])")
                    gizmo._draw_handle_common(context, during_modal=during_modal)
        except Exception as e:
            print(f"Manual draw error: {e}")


def register_crop_handles_gizmo():
    """Register the crop handles gizmo classes"""
    try:
        print("=== REGISTERING CROP HANDLES GIZMO ===")
        
        bpy.utils.register_class(EASYCROP_GT_crop_handle)
        print("✓ Registered EASYCROP_GT_crop_handle")
        
        bpy.utils.register_class(EASYCROP_GGT_crop_handles)
        print("✓ Registered EASYCROP_GGT_crop_handles")
        
        # Ensure the gizmo group type is active
        try:
            wm = bpy.context.window_manager
            if hasattr(wm, 'gizmo_group_type_ensure'):
                wm.gizmo_group_type_ensure(EASYCROP_GGT_crop_handles.bl_idname)
                print("✓ gizmo_group_type_ensure() called successfully")
        except Exception as e:
            # This error is expected for PERSISTENT gizmo groups
            if "PERSISTENT" in str(e):
                print("ℹ PERSISTENT gizmo group registration - this is normal")
            else:
                print(f"ℹ gizmo_group_type_ensure() not needed: {e}")
            
        print("=== CROP HANDLES GIZMO REGISTRATION COMPLETE ===")
        return True
        
    except Exception as e:
        print(f"Failed to register crop handles gizmo: {e}")
        import traceback
        traceback.print_exc()
        return False


def unregister_crop_handles_gizmo():
    """Unregister the crop handles gizmo classes"""
    try:
        print("=== UNREGISTERING CROP HANDLES GIZMO ===")
        
        bpy.utils.unregister_class(EASYCROP_GGT_crop_handles)
        print("✓ Unregistered EASYCROP_GGT_crop_handles")
        
        bpy.utils.unregister_class(EASYCROP_GT_crop_handle)
        print("✓ Unregistered EASYCROP_GT_crop_handle")
        
        print("=== CROP HANDLES GIZMO UNREGISTRATION COMPLETE ===")
        
    except Exception as e:
        print(f"Failed to unregister crop handles gizmo: {e}")