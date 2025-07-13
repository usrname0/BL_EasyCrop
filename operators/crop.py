import bpy
import gpu
import math
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from bpy.props import BoolProperty

# Try absolute imports first, fall back to relative
try:
    from ..utils.geometry import get_preview_offset, get_strip_corners, get_strip_box, rotate_point
    from ..utils.draw import draw_line
except ImportError:
    try:
        from .utils.geometry import get_preview_offset, get_strip_corners, get_strip_box, rotate_point
        from .utils.draw import draw_line
    except ImportError as e:
        print(f"BL Easy Crop: Failed to import utils: {e}")
        # Define dummy functions to prevent errors
        def get_preview_offset():
            return (0.0, 0.0, 1.0, 1.0)
        def get_strip_corners(strip):
            return []
        def get_strip_box(strip):
            return (0.0, 0.0, 0.0, 0.0)
        def rotate_point(point, angle, origin):
            return point
        def draw_line(v1, v2, width, color):
            pass


# Global variable to store the draw handler
_draw_handle = None
_draw_data = {}
_crop_active = False  # Track if crop mode is active


def is_strip_visible_at_frame(strip, frame):
    """Check if a strip is visible at the given frame"""
    return (strip.frame_final_start <= frame <= strip.frame_final_end and not strip.mute)


def point_in_polygon(point, polygon):
    """Check if a point is inside a polygon using ray casting algorithm"""
    x, y = point.x, point.y
    n = len(polygon)
    inside = False
    
    p1x, p1y = polygon[0].x, polygon[0].y
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n].x, polygon[i % n].y
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    
    return inside


def get_strip_geometry_with_flip_support(strip, scene):
    """
    Calculate strip geometry accounting for Mirror X/Y checkboxes
    Returns corner positions in resolution space
    """
    res_x = scene.render.resolution_x
    res_y = scene.render.resolution_y
    
    # Get actual strip dimensions
    if hasattr(strip, 'elements') and strip.elements:
        elem = strip.elements[0]
        strip_width = elem.orig_width
        strip_height = elem.orig_height
    else:
        strip_width = res_x
        strip_height = res_y
    
    # Get scale and base transform
    scale_x = 1.0
    scale_y = 1.0
    offset_x = 0
    offset_y = 0
    
    if hasattr(strip, 'transform'):
        offset_x = strip.transform.offset_x
        offset_y = strip.transform.offset_y
        if hasattr(strip.transform, 'scale_x'):
            scale_x = strip.transform.scale_x
            scale_y = strip.transform.scale_y
    
    # Check for Mirror X/Y checkboxes
    flip_x = False
    flip_y = False
    
    if hasattr(strip, 'use_flip_x'):
        flip_x = strip.use_flip_x
    elif hasattr(strip, 'flip_x'):
        flip_x = strip.flip_x
    elif hasattr(strip, 'mirror_x'):
        flip_x = strip.mirror_x
    
    if hasattr(strip, 'use_flip_y'):
        flip_y = strip.use_flip_y
    elif hasattr(strip, 'flip_y'):
        flip_y = strip.flip_y
    elif hasattr(strip, 'mirror_y'):
        flip_y = strip.mirror_y
    
    # Get rotation angle
    angle = 0
    if hasattr(strip, 'rotation_start'):
        angle = math.radians(strip.rotation_start)
    elif hasattr(strip, 'rotation'):
        angle = strip.rotation
    elif hasattr(strip, 'transform') and hasattr(strip.transform, 'rotation'):
        angle = strip.transform.rotation
    
    # Get crop values
    crop_left = 0
    crop_right = 0
    crop_bottom = 0
    crop_top = 0
    
    if hasattr(strip, 'crop'):
        crop_left = float(strip.crop.min_x)
        crop_right = float(strip.crop.max_x)
        crop_bottom = float(strip.crop.min_y)
        crop_top = float(strip.crop.max_y)
    
    # Calculate scaled dimensions
    scaled_width = strip_width * scale_x
    scaled_height = strip_height * scale_y
    
    # Calculate position (centered by default, then offset)
    left = (res_x - scaled_width) / 2 + offset_x
    right = (res_x + scaled_width) / 2 + offset_x
    bottom = (res_y - scaled_height) / 2 + offset_y
    top = (res_y + scaled_height) / 2 + offset_y
    
    # Apply crop - crop values are in original image space, so scale them
    left += crop_left * scale_x
    right -= crop_right * scale_x
    bottom += crop_bottom * scale_y
    top -= crop_top * scale_y
    
    # Calculate pivot point for rotation
    pivot_x = res_x / 2 + offset_x
    pivot_y = res_y / 2 + offset_y
    
    # When flipped, mirror the box position around the render center
    if flip_x:
        # Mirror horizontally around the center
        new_left = res_x - right
        new_right = res_x - left
        left = new_left
        right = new_right
        # Also flip the pivot point!
        pivot_x = res_x - pivot_x
    
    if flip_y:
        # Mirror vertically around the center
        new_bottom = res_y - top
        new_top = res_y - bottom
        bottom = new_bottom
        top = new_top
        # Also flip the pivot point!
        pivot_y = res_y - pivot_y
    
    # Create corner vectors
    corners = [
        Vector((left, bottom)),  # Bottom-left
        Vector((left, top)),     # Top-left
        Vector((right, top)),    # Top-right
        Vector((right, bottom))  # Bottom-right
    ]
    
    # Apply rotation if needed (rotation happens after flip)
    if angle != 0:
        # When flipped, rotation direction is reversed
        if flip_x != flip_y:  # XOR - if only one axis is flipped
            angle = -angle
        
        center = Vector((pivot_x, pivot_y))
        rotated_corners = []
        for corner in corners:
            rotated = rotate_point(corner, angle, center)
            rotated_corners.append(rotated)
        corners = rotated_corners
    
    return corners, (pivot_x, pivot_y), (scale_x, scale_y, flip_x, flip_y)


def draw_crop_handles():
    """Draw function for crop handles"""
    global _crop_active
    
    # Exit immediately if crop mode isn't active
    if not _crop_active:
        return
        
    context = bpy.context
    if not context.area or context.area.type != 'SEQUENCE_EDITOR':
        return
    
    # Always get the current active strip to ensure we have latest state
    scene = context.scene
    if not scene.sequence_editor:
        return
        
    strip = scene.sequence_editor.active_strip
    if not strip or not hasattr(strip, 'crop'):
        return
    
    # Check if strip is visible at current frame
    current_frame = scene.frame_current
    if not is_strip_visible_at_frame(strip, current_frame):
        return
    
    # Get stored data - if _draw_data is empty, initialize it
    if not _draw_data:
        _draw_data['active_corner'] = -1
        _draw_data['frame_count'] = 0
    
    active_corner = _draw_data.get('active_corner', -1)
    
    # Get theme colors - use white for handles like native transforms
    active_color = (1.0, 1.0, 1.0, 1.0)  # White for active
    handle_color = (1.0, 1.0, 1.0, 0.7)  # Slightly transparent white
    line_color = (1.0, 1.0, 1.0, 0.5)    # More transparent for lines
    
    # ALWAYS recalculate geometry to get current crop values
    corners, (pivot_x, pivot_y), (scale_x, scale_y, flip_x, flip_y) = get_strip_geometry_with_flip_support(strip, scene)
    
    # Calculate edge midpoints (after rotation)
    edge_midpoints = []
    for i in range(4):
        next_i = (i + 1) % 4
        midpoint = (corners[i] + corners[next_i]) / 2
        edge_midpoints.append(midpoint)
    
    # Get preview transform - we need to use the View2D system
    region = context.region
    if not region:
        return
    
    view2d = context.region.view2d
    res_x = scene.render.resolution_x
    res_y = scene.render.resolution_y
    
    screen_corners = []
    for corner in corners:
        # Transform from resolution space to view space, then to region space
        # Resolution space has (0,0) at bottom-left, view space has (0,0) at center
        view_x = corner.x - res_x / 2
        view_y = corner.y - res_y / 2
        
        # Use Blender's view2d to transform to screen coordinates
        screen_co = view2d.view_to_region(view_x, view_y, clip=False)
        screen_corners.append(Vector(screen_co))
    
    # Transform edge midpoints to screen space
    screen_midpoints = []
    for midpoint in edge_midpoints:
        view_x = midpoint.x - res_x / 2
        view_y = midpoint.y - res_y / 2
        screen_co = view2d.view_to_region(view_x, view_y, clip=False)
        screen_midpoints.append(Vector(screen_co))
    
    # Draw crop outline
    for i in range(4):
        next_i = (i + 1) % 4
        draw_line(screen_corners[i], screen_corners[next_i], 2, (0, 0, 0, 0.5))
        draw_line(screen_corners[i], screen_corners[next_i], 1, line_color)
    
    # Draw crop symbol at center of ORIGINAL strip (not cropped)
    # This matches Blender's behavior where symbols stay centered on the original bounds
    # Calculate center in screen space
    original_center_x = pivot_x  # Already calculated as rotation pivot
    original_center_y = pivot_y
    
    # Apply flip to the symbol position to follow the visual content
    if flip_x:
        original_center_x = res_x - original_center_x
    if flip_y:
        original_center_y = res_y - original_center_y
    
    # Transform to screen coordinates
    screen_center = view2d.view_to_region(
        original_center_x - res_x / 2,
        original_center_y - res_y / 2,
        clip=False
    )
    center_x = screen_center[0]
    center_y = screen_center[1]
    
    # Draw clean white crop symbol with no background
    white_color = (1.0, 1.0, 1.0, 0.8)
    
    # Create shader for lines
    line_shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    
    # Scale for the symbol - keeping it visible but not too large
    outer_size = 8   # Size of the outer corner brackets
    inner_size = 5   # Size of the inner viewing rectangle
    
    # Set consistent line width
    gpu.state.line_width_set(1.5)
    
    line_shader.bind()
    line_shader.uniform_float("color", white_color)
    
    # Top-left corner bracket (L-shape)
    # Vertical line (left side)
    tl_vertical = [
        (center_x - outer_size, center_y + 1),        # Bottom of vertical
        (center_x - outer_size, center_y + outer_size) # Top of vertical
    ]
    
    # Horizontal line (top side)  
    tl_horizontal = [
        (center_x - outer_size, center_y + outer_size), # Left end
        (center_x - 1, center_y + outer_size)           # Right end
    ]
    
    # Bottom-right corner bracket (L-shape)
    # Horizontal line (bottom side)
    br_horizontal = [
        (center_x + 1, center_y - outer_size),          # Left end
        (center_x + outer_size, center_y - outer_size)  # Right end
    ]
    
    # Vertical line (right side)
    br_vertical = [
        (center_x + outer_size, center_y - outer_size), # Bottom
        (center_x + outer_size, center_y - 1)           # Top
    ]
    
    # Inner viewing rectangle (thin frame)
    inner_rect_lines = [
        # Bottom line
        [(center_x - inner_size, center_y - inner_size), 
         (center_x + inner_size, center_y - inner_size)],
        # Right line  
        [(center_x + inner_size, center_y - inner_size),
         (center_x + inner_size, center_y + inner_size)],
        # Top line
        [(center_x + inner_size, center_y + inner_size),
         (center_x - inner_size, center_y + inner_size)],
        # Left line
        [(center_x - inner_size, center_y + inner_size),
         (center_x - inner_size, center_y - inner_size)]
    ]
    
    # Draw all the corner bracket lines
    for line_verts in [tl_vertical, tl_horizontal, br_horizontal, br_vertical]:
        batch = batch_for_shader(line_shader, 'LINES', {"pos": line_verts})
        batch.draw(line_shader)
    
    # Draw the inner rectangle
    for line_verts in inner_rect_lines:
        batch = batch_for_shader(line_shader, 'LINES', {"pos": line_verts})
        batch.draw(line_shader)
    
    # Reset line width
    gpu.state.line_width_set(1.0)
    
    # Draw corner handles
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    
    # Draw all handles as rotated squares
    all_handle_positions = screen_corners + screen_midpoints
    
    # Get rotation angle for handle orientation
    angle = 0
    if hasattr(strip, 'rotation_start'):
        angle = math.radians(strip.rotation_start)
    elif hasattr(strip, 'rotation'):
        angle = strip.rotation
    elif hasattr(strip, 'transform') and hasattr(strip.transform, 'rotation'):
        angle = strip.transform.rotation
    
    for i, pos in enumerate(all_handle_positions):
        # Determine size and color
        size = 8 if i == active_corner else 6
        color = active_color if i == active_corner else handle_color
        
        # Create handle vertices - rotated to match strip
        if abs(angle) > 0.01:  # If strip is rotated
            # Calculate handle rotation
            # For corner handles, rotate 45 degrees less to point at corners
            # For edge handles, align with the edge
            if i < 4:  # Corner handle
                handle_angle = angle
            else:  # Edge handle - align with edge direction
                edge_idx = i - 4
                corner1_idx = edge_idx
                corner2_idx = (edge_idx + 1) % 4
                
                # Get edge angle in screen space
                edge_vec = screen_corners[corner2_idx] - screen_corners[corner1_idx]
                edge_angle = math.atan2(edge_vec.y, edge_vec.x)
                handle_angle = edge_angle - math.pi / 2  # Perpendicular to edge
            
            # Create rotated square
            cos_a = math.cos(handle_angle)
            sin_a = math.sin(handle_angle)
            
            # Define square corners relative to center
            corners_rel = [
                Vector((-size, -size)),
                Vector((size, -size)),
                Vector((size, size)),
                Vector((-size, size))
            ]
            
            # Rotate and translate
            vertices = []
            for corner_rel in corners_rel:
                x = corner_rel.x * cos_a - corner_rel.y * sin_a + pos.x
                y = corner_rel.x * sin_a + corner_rel.y * cos_a + pos.y
                vertices.append((x, y))
            
            # Convert to proper format
            vertices = [
                vertices[0],
                vertices[1],
                vertices[3],
                vertices[2]
            ]
        else:
            # No rotation - draw regular square handle
            vertices = [
                (pos.x - size, pos.y - size),
                (pos.x + size, pos.y - size),
                (pos.x - size, pos.y + size),
                (pos.x + size, pos.y + size)
            ]
        
        indices = ((0, 1, 2), (2, 1, 3))
        
        batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)


class EASYCROP_OT_crop(bpy.types.Operator):
    """Crop strips in the preview window"""
    bl_idname = "easycrop.crop"
    bl_label = "Crop"
    bl_description = "Crop a strip in the Image Preview"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        scene = context.scene
        if not scene.sequence_editor:
            return False
        
        # Check if we're in preview mode
        space = context.space_data
        if space and space.type == 'SEQUENCE_EDITOR':
            if space.view_type not in {'PREVIEW', 'SEQUENCER_PREVIEW'}:
                return False
        
        # Just need any selected strip with crop capability
        if scene.sequence_editor.active_strip and hasattr(scene.sequence_editor.active_strip, 'crop'):
            return True
        
        # Also check if any selected strip has crop
        for strip in context.selected_sequences:
            if hasattr(strip, 'crop'):
                return True
                
        return False
    
    def invoke(self, context, event):
        global _draw_handle, _draw_data, _crop_active
        
        # If crop is already active, handle the click within the existing modal
        if _crop_active:
            # Don't start a new crop operation - let the existing modal handle it
            self.report({'WARNING'}, "Crop mode already active")
            return {'CANCELLED'}
        
        # Get the active strip - if no active strip or not croppable, check if clicking on a strip
        strip = context.scene.sequence_editor.active_strip if context.scene.sequence_editor else None
        current_frame = context.scene.frame_current
        
        # Check if we have a suitable active strip that's visible
        has_suitable_active = (strip and 
                              hasattr(strip, 'crop') and 
                              is_strip_visible_at_frame(strip, current_frame))
        
        # If no suitable active strip, try to find one under the mouse
        if not has_suitable_active:
            mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))
            strips = self.get_visible_strips(context)
            clicked_strip = None
            
            # Check from top to bottom for a croppable strip
            for s in reversed(strips):
                if hasattr(s, 'crop') and self.is_mouse_over_strip(context, s, mouse_pos):
                    clicked_strip = s
                    break
            
            if clicked_strip:
                # Select the clicked strip and make it active
                if not event.shift:
                    bpy.ops.sequencer.select_all(action='DESELECT')
                clicked_strip.select = True
                context.scene.sequence_editor.active_strip = clicked_strip
                strip = clicked_strip
                has_suitable_active = True
            else:
                # No suitable strip found - report and exit
                self.report({'INFO'}, "No croppable strip found - select an image/movie strip")
                return {'CANCELLED'}
        
        # Now we should have a suitable strip - proceed with crop initialization
        if not has_suitable_active:
            self.report({'INFO'}, "No suitable strip for cropping")
            return {'CANCELLED'}
        
        # Initialize instance variables
        self.active_corner = -1
        self.mouse_start = (0.0, 0.0)
        self.crop_start = (0.0, 0.0, 0.0, 0.0)
        self.timer = None
        self.first_click = False
        self.first_mouse_x = 0
        self.first_mouse_y = 0
        
        # Store the current transform overlay state so we can restore it later
        self.prev_show_gizmo = None
        if hasattr(context.space_data, 'show_gizmo'):
            self.prev_show_gizmo = context.space_data.show_gizmo
            # Hide transform gizmos while cropping to avoid conflicts
            context.space_data.show_gizmo = False
        
        # Clean up any existing handler first (safety check for lingering state)
        if _draw_handle is not None:
            try:
                bpy.types.SpaceSequenceEditor.draw_handler_remove(
                    _draw_handle, 'PREVIEW')
            except:
                pass
            _draw_handle = None
        
        # Mark crop as active FIRST
        _crop_active = True
        
        # Initialize draw data immediately - this ensures handles will be visible
        _draw_data = {
            'active_corner': -1,
            'frame_count': 0
        }
        
        # Store the initial crop values
        if strip and hasattr(strip, 'crop') and strip.crop:
            self.crop_start = (
                strip.crop.min_x,
                strip.crop.max_x,
                strip.crop.min_y,
                strip.crop.max_y
            )
        else:
            self.crop_start = (0, 0, 0, 0)
        
        # Set up drawing handler (handles will draw immediately)
        _draw_handle = bpy.types.SpaceSequenceEditor.draw_handler_add(
            draw_crop_handles, (), 'PREVIEW', 'POST_PIXEL')
        
        # Force an immediate redraw
        context.area.tag_redraw()
        
        # Add a timer to force redraws
        wm = context.window_manager
        self.timer = wm.event_timer_add(0.01, window=context.window)
        
        # Add modal handler
        wm.modal_handler_add(self)
        
        return {'RUNNING_MODAL'}
    
    def modal(self, context, event):
        global _draw_data
        
        # Handle timer events to force redraw
        if event.type == 'TIMER':
            # Force redraw on timer
            for area in context.screen.areas:
                if area.type == 'SEQUENCE_EDITOR':
                    area.tag_redraw()
            return {'RUNNING_MODAL'}
        
        strip = context.scene.sequence_editor.active_strip
        if not strip:
            return self.finish(context)
        
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            # Check if clicking on a handle
            corner = self.get_corner_at_mouse(context, event)
            
            if corner >= 0:
                self.active_corner = corner
                _draw_data['active_corner'] = corner
                self.mouse_start = (event.mouse_region_x, event.mouse_region_y)
                # Store current crop values for this drag
                if strip and hasattr(strip, 'crop') and strip.crop:
                    self.crop_start = (
                        strip.crop.min_x,
                        strip.crop.max_x,
                        strip.crop.min_y,
                        strip.crop.max_y
                    )
                else:
                    self.crop_start = (0, 0, 0, 0)
            else:
                # Not clicking on a handle - check if clicking on another strip
                mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))
                strips = self.get_visible_strips(context)
                clicked_strip = None
                
                # Check from top to bottom
                for s in reversed(strips):
                    if self.is_mouse_over_strip(context, s, mouse_pos):
                        clicked_strip = s
                        break
                
                if clicked_strip and clicked_strip != strip:
                    # Clicking on a different strip - exit crop and select it
                    self.finish(context)
                    if not event.shift:
                        bpy.ops.sequencer.select_all(action='DESELECT')
                    clicked_strip.select = True
                    context.scene.sequence_editor.active_strip = clicked_strip
                    # Re-activate crop on the new strip
                    if hasattr(clicked_strip, 'crop'):
                        bpy.ops.easycrop.crop('INVOKE_DEFAULT')
                    return {'FINISHED'}
                else:
                    # Clicking outside any strip or on same strip - just exit crop mode
                    return self.finish(context)
        
        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            self.active_corner = -1
            _draw_data['active_corner'] = -1
        
        elif event.type == 'MOUSEMOVE' and self.active_corner >= 0:
            self.update_crop(context, event)
            # Force immediate redraw to show the changes
            for area in context.screen.areas:
                if area.type == 'SEQUENCE_EDITOR':
                    area.tag_redraw()
            return {'RUNNING_MODAL'}
        
        elif event.type in {'RET', 'NUMPAD_ENTER'}:
            # Exit crop mode on Enter
            return self.finish(context)
        
        elif event.type == 'ESC':
            # Restore original crop values
            if strip and hasattr(strip, 'crop') and strip.crop:
                strip.crop.min_x = int(self.crop_start[0])
                strip.crop.max_x = int(self.crop_start[1])
                strip.crop.min_y = int(self.crop_start[2])
                strip.crop.max_y = int(self.crop_start[3])
            return self.finish(context, cancelled=True)
        
        # Check for transform operators dynamically
        elif self.is_transform_key(context, event):
            # Exit crop mode and activate the transform
            self.finish(context)
            # Find which transform operator to invoke
            transform_op = self.get_transform_operator(context, event)
            if transform_op:
                if transform_op == 'transform.translate':
                    bpy.ops.transform.translate('INVOKE_DEFAULT')
                elif transform_op == 'transform.resize':
                    bpy.ops.transform.resize('INVOKE_DEFAULT')
                elif transform_op == 'transform.rotate':
                    bpy.ops.transform.rotate('INVOKE_DEFAULT')
            return {'FINISHED'}
        
        elif event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        
        return {'RUNNING_MODAL'}
    
    def finish(self, context, cancelled=False):
        """Clean up and exit"""
        global _draw_handle, _draw_data, _crop_active
        
        # Clear the active flag FIRST
        _crop_active = False
        
        # Restore transform gizmo visibility
        if hasattr(self, 'prev_show_gizmo') and self.prev_show_gizmo is not None and hasattr(context.space_data, 'show_gizmo'):
            context.space_data.show_gizmo = self.prev_show_gizmo
        
        # Remove timer
        if hasattr(self, 'timer') and self.timer:
            try:
                context.window_manager.event_timer_remove(self.timer)
            except:
                pass
            self.timer = None
        
        # Remove draw handler - be extra thorough
        if _draw_handle is not None:
            try:
                bpy.types.SpaceSequenceEditor.draw_handler_remove(
                    _draw_handle, 'PREVIEW')
            except:
                pass
            _draw_handle = None
        
        # Clear draw data
        _draw_data.clear()
        
        # Reset operator state
        self.active_corner = -1
        self.first_click = False
        
        # Force redraw all sequence editor areas
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'SEQUENCE_EDITOR':
                    for region in area.regions:
                        region.tag_redraw()
        
        return {'CANCELLED'} if cancelled else {'FINISHED'}
    
    def get_corner_at_mouse(self, context, event):
        """Check if mouse is over a corner or edge handle"""
        mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))
        corners, midpoints = self.get_crop_corners(context)
        
        # Check corner handles first (0-3)
        for i, corner in enumerate(corners):
            if (corner - mouse_pos).length < 10:
                return i
        
        # Check edge handles (4-7)
        for i, midpoint in enumerate(midpoints):
            if (midpoint - mouse_pos).length < 10:
                return i + 4
        
        return -1
    
    def get_crop_corners(self, context):
        """Get the corner and edge midpoint positions in screen space"""
        strip = context.scene.sequence_editor.active_strip
        scene = context.scene
        if not strip or not context.region:
            return [], []
        
        # Use the new flip-aware geometry calculation
        corners, (pivot_x, pivot_y), (scale_x, scale_y, flip_x, flip_y) = get_strip_geometry_with_flip_support(strip, scene)
        
        # Calculate edge midpoints (after rotation)
        edge_midpoints = []
        for i in range(4):
            next_i = (i + 1) % 4
            midpoint = (corners[i] + corners[next_i]) / 2
            edge_midpoints.append(midpoint)
        
        # Use Blender's view2d system for accurate transformation
        view2d = context.region.view2d
        res_x = scene.render.resolution_x
        res_y = scene.render.resolution_y
        
        screen_corners = []
        for corner in corners:
            # Transform from resolution space to view space
            view_x = corner.x - res_x / 2
            view_y = corner.y - res_y / 2
            
            # Use view2d to get screen coordinates
            screen_co = view2d.view_to_region(view_x, view_y, clip=False)
            screen_corners.append(Vector(screen_co))
        
        screen_midpoints = []
        for midpoint in edge_midpoints:
            view_x = midpoint.x - res_x / 2
            view_y = midpoint.y - res_y / 2
            screen_co = view2d.view_to_region(view_x, view_y, clip=False)
            screen_midpoints.append(Vector(screen_co))
        
        return screen_corners, screen_midpoints
    
    def cancel(self, context):
        """Called when operator is cancelled by Blender"""
        return self.finish(context, cancelled=True)
    
    def update_crop(self, context, event):
        """Update crop values based on mouse drag with flip support"""
        strip = context.scene.sequence_editor.active_strip
        scene = context.scene
        
        # Ensure we have a valid strip with crop capability
        if not strip or not hasattr(strip, 'crop') or not strip.crop:
            return
        
        # Calculate mouse delta
        dx = event.mouse_region_x - self.mouse_start[0]
        dy = event.mouse_region_y - self.mouse_start[1]
        
        # Use view2d to convert screen delta to resolution space
        view2d = context.region.view2d
        
        # Get two points to calculate the scale
        p1 = view2d.region_to_view(0, 0)
        p2 = view2d.region_to_view(1, 1)
        
        # Calculate pixels per unit in view space
        scale_x = abs(p2[0] - p1[0])
        scale_y = abs(p2[1] - p1[1])
        
        # Convert mouse delta to view space units
        dx_view = dx * scale_x
        dy_view = dy * scale_y
        
        # Get the strip's scale and flip state
        strip_scale_x = strip.transform.scale_x if hasattr(strip, 'transform') and hasattr(strip.transform, 'scale_x') else 1.0
        strip_scale_y = strip.transform.scale_y if hasattr(strip, 'transform') and hasattr(strip.transform, 'scale_y') else 1.0
        
        # Check for Mirror X/Y checkboxes (flip transforms)
        flip_x = False
        flip_y = False
        
        if hasattr(strip, 'use_flip_x'):
            flip_x = strip.use_flip_x
        elif hasattr(strip, 'flip_x'):
            flip_x = strip.flip_x
        elif hasattr(strip, 'mirror_x'):
            flip_x = strip.mirror_x
        
        if hasattr(strip, 'use_flip_y'):
            flip_y = strip.use_flip_y
        elif hasattr(strip, 'flip_y'):
            flip_y = strip.flip_y
        elif hasattr(strip, 'mirror_y'):
            flip_y = strip.mirror_y
        
        # Handle rotation if present
        angle = 0
        if hasattr(strip, 'rotation_start'):
            angle = -math.radians(strip.rotation_start)  # Negative to reverse rotation, convert from degrees
        elif hasattr(strip, 'transform') and hasattr(strip.transform, 'rotation'):
            angle = -strip.transform.rotation  # Already in radians, just negate
        
        # When flipped, rotation direction is reversed
        if flip_x != flip_y:  # XOR - if only one axis is flipped
            angle = -angle
        
        # Rotate the delta if strip is rotated
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
        
        # IMPORTANT: When strips are flipped, we need to invert the mouse deltas
        # because dragging "right" on a flipped strip should increase the "left" crop value
        if flip_x:
            dx_res = -dx_res
        if flip_y:
            dy_res = -dy_res
        
        # Get the original strip dimensions (before crop/scale)
        strip_width = strip.elements[0].orig_width if hasattr(strip, 'elements') and strip.elements else scene.render.resolution_x
        strip_height = strip.elements[0].orig_height if hasattr(strip, 'elements') and strip.elements else scene.render.resolution_y
        
        # When strips are flipped, we need to remap which handles control which crop boundaries
        # because the visual handle positions change but the crop value semantics stay the same
        
        # Determine effective handle mapping based on flip state
        # Corner mapping: 0=BL, 1=TL, 2=TR, 3=BR (in screen space)
        # Edge mapping: 4=Left, 5=Top, 6=Right, 7=Bottom (in screen space)
        
        if self.active_corner < 4:
            # Corner handles - need to remap based on both X and Y flips
            corner_map = self.active_corner
            
            # Remap corner based on flips
            if flip_x and flip_y:
                # Both flipped: BL<->TR, TL<->BR
                corner_remap = {0: 2, 1: 3, 2: 0, 3: 1}
                corner_map = corner_remap[self.active_corner]
            elif flip_x:
                # X flipped: BL<->BR, TL<->TR  
                corner_remap = {0: 3, 1: 2, 2: 1, 3: 0}
                corner_map = corner_remap[self.active_corner]
            elif flip_y:
                # Y flipped: BL<->TL, BR<->TR
                corner_remap = {0: 1, 1: 0, 2: 3, 3: 2}
                corner_map = corner_remap[self.active_corner]
            
            # Now use the remapped corner for logic
            if corner_map == 0:  # Bottom-left (in original image space)
                # X direction: moving right increases left crop
                new_min_x = int(max(0, self.crop_start[0] + dx_res))
                if new_min_x + strip.crop.max_x < strip_width:
                    strip.crop.min_x = new_min_x
                
                # Y direction: moving up increases bottom crop
                new_min_y = int(max(0, self.crop_start[2] + dy_res))
                if new_min_y + strip.crop.max_y < strip_height:
                    strip.crop.min_y = new_min_y
                        
            elif corner_map == 1:  # Top-left (in original image space)
                # X direction: moving right increases left crop
                new_min_x = int(max(0, self.crop_start[0] + dx_res))
                if new_min_x + strip.crop.max_x < strip_width:
                    strip.crop.min_x = new_min_x
                
                # Y direction: moving up decreases top crop
                new_max_y = int(max(0, self.crop_start[3] - dy_res))
                if strip.crop.min_y + new_max_y < strip_height:
                    strip.crop.max_y = new_max_y
                        
            elif corner_map == 2:  # Top-right (in original image space)
                # X direction: moving right decreases right crop
                new_max_x = int(max(0, self.crop_start[1] - dx_res))
                if strip.crop.min_x + new_max_x < strip_width:
                    strip.crop.max_x = new_max_x
                
                # Y direction: moving up decreases top crop
                new_max_y = int(max(0, self.crop_start[3] - dy_res))
                if strip.crop.min_y + new_max_y < strip_height:
                    strip.crop.max_y = new_max_y
                        
            elif corner_map == 3:  # Bottom-right (in original image space)
                # X direction: moving right decreases right crop
                new_max_x = int(max(0, self.crop_start[1] - dx_res))
                if strip.crop.min_x + new_max_x < strip_width:
                    strip.crop.max_x = new_max_x
                
                # Y direction: moving up increases bottom crop
                new_min_y = int(max(0, self.crop_start[2] + dy_res))
                if new_min_y + strip.crop.max_y < strip_height:
                    strip.crop.min_y = new_min_y
        else:
            # Edge handles - need to remap based on flips
            edge_index = self.active_corner - 4
            edge_map = edge_index
            
            # Remap edges based on flips
            if flip_x and flip_y:
                # Both flipped: Left<->Right, Top<->Bottom
                edge_remap = {0: 2, 1: 3, 2: 0, 3: 1}
                edge_map = edge_remap[edge_index]
            elif flip_x:
                # X flipped: Left<->Right
                edge_remap = {0: 2, 1: 1, 2: 0, 3: 3}
                edge_map = edge_remap[edge_index]
            elif flip_y:
                # Y flipped: Top<->Bottom
                edge_remap = {0: 0, 1: 3, 2: 2, 3: 1}
                edge_map = edge_remap[edge_index]
            
            # Now use the remapped edge for logic
            if edge_map == 0:  # Left edge (in original image space)
                new_min_x = int(max(0, self.crop_start[0] + dx_res))
                if new_min_x + strip.crop.max_x < strip_width:
                    strip.crop.min_x = new_min_x
                        
            elif edge_map == 1:  # Top edge (in original image space)
                new_max_y = int(max(0, self.crop_start[3] - dy_res))
                if strip.crop.min_y + new_max_y < strip_height:
                    strip.crop.max_y = new_max_y
                        
            elif edge_map == 2:  # Right edge (in original image space)
                new_max_x = int(max(0, self.crop_start[1] - dx_res))
                if strip.crop.min_x + new_max_x < strip_width:
                    strip.crop.max_x = new_max_x
                        
            elif edge_map == 3:  # Bottom edge (in original image space)
                new_min_y = int(max(0, self.crop_start[2] + dy_res))
                if new_min_y + strip.crop.max_y < strip_height:
                    strip.crop.min_y = new_min_y
    
    def is_transform_key(self, context, event):
        """Check if the pressed key is bound to a transform operator"""
        if event.value != 'PRESS':
            return False
            
        # Get the active keyconfig
        wm = context.window_manager
        kc = wm.keyconfigs.active
        
        # Check common transform operators
        transform_ops = ['transform.translate', 'transform.resize', 'transform.rotate']
        
        # Look through keymaps for transform operators
        for keymap_name in ['Sequencer', 'SequencerPreview']:
            if keymap_name in kc.keymaps:
                km = kc.keymaps[keymap_name]
                for kmi in km.keymap_items:
                    if kmi.active and kmi.idname in transform_ops:
                        if (kmi.type == event.type and 
                            kmi.shift == event.shift and
                            kmi.ctrl == event.ctrl and
                            kmi.alt == event.alt):
                            return True
        
        return False
    
    def get_transform_operator(self, context, event):
        """Get which transform operator is bound to the pressed key"""
        # Get the active keyconfig
        wm = context.window_manager
        kc = wm.keyconfigs.active
        
        # Look through keymaps for transform operators
        for keymap_name in ['Sequencer', 'SequencerPreview']:
            if keymap_name in kc.keymaps:
                km = kc.keymaps[keymap_name]
                for kmi in km.keymap_items:
                    if kmi.active and kmi.type == event.type:
                        if (kmi.shift == event.shift and
                            kmi.ctrl == event.ctrl and
                            kmi.alt == event.alt):
                            if kmi.idname in ['transform.translate', 'transform.resize', 'transform.rotate']:
                                return kmi.idname
        
        return None
    
    def get_visible_strips(self, context):
        """Get all strips visible at the current frame"""
        scene = context.scene
        if not scene.sequence_editor:
            return []
        
        current_frame = scene.frame_current
        strips = []
        
        for strip in scene.sequence_editor.sequences:
            # Check if strip is visible at current frame
            if is_strip_visible_at_frame(strip, current_frame):
                strips.append(strip)
        
        # Sort by channel (higher channels on top)
        strips.sort(key=lambda s: s.channel)
        
        return strips
    
    def is_mouse_over_strip(self, context, strip, mouse_pos):
        """Check if mouse is over the given strip with flip support"""
        # Use the new flip-aware geometry
        scene = context.scene
        corners, (pivot_x, pivot_y), (scale_x, scale_y, flip_x, flip_y) = get_strip_geometry_with_flip_support(strip, scene)
        
        # Convert to screen space
        view2d = context.region.view2d
        res_x = scene.render.resolution_x
        res_y = scene.render.resolution_y
        
        screen_corners = []
        for corner in corners:
            view_x = corner.x - res_x / 2
            view_y = corner.y - res_y / 2
            screen_co = view2d.view_to_region(view_x, view_y, clip=False)
            screen_corners.append(Vector(screen_co))
        
        return point_in_polygon(mouse_pos, screen_corners)


class EASYCROP_OT_activate_tool(bpy.types.Operator):
    """Activate crop tool - direct activation like built-in transforms"""
    bl_idname = "easycrop.activate_tool"
    bl_label = "Activate Crop Tool"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}
    
    @classmethod
    def poll(cls, context):
        return (context.scene.sequence_editor is not None and
                context.space_data and 
                context.space_data.type == 'SEQUENCE_EDITOR' and
                context.space_data.view_type in {'PREVIEW', 'SEQUENCER_PREVIEW'})
    
    def invoke(self, context, event):
        # Just like Blender's built-in transforms: immediately activate the crop operator
        # The crop operator will handle all the logic about what to crop
        return bpy.ops.easycrop.crop('INVOKE_DEFAULT')


class EASYCROP_OT_select_and_crop(bpy.types.Operator):
    """Select strip and activate crop mode"""
    bl_idname = "easycrop.select_and_crop"
    bl_label = "Select and Crop"
    bl_description = "Select a strip in the preview and activate crop mode"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}
    
    @classmethod
    def poll(cls, context):
        return (context.scene.sequence_editor is not None and
                context.space_data and 
                context.space_data.type == 'SEQUENCE_EDITOR' and
                context.space_data.view_type in {'PREVIEW', 'SEQUENCER_PREVIEW'})
    
    def invoke(self, context, event):
        # First, check if we're clicking on a strip
        mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))
        
        # Get all visible strips at current frame
        strips = self.get_visible_strips(context)
        clicked_strip = None
        
        # Check from top to bottom (reversed order)
        for strip in reversed(strips):
            if hasattr(strip, 'crop') and self.is_mouse_over_strip(context, strip, mouse_pos):
                clicked_strip = strip
                break
        
        if clicked_strip:
            # Select the strip
            if not event.shift:
                bpy.ops.sequencer.select_all(action='DESELECT')
            
            clicked_strip.select = True
            context.scene.sequence_editor.active_strip = clicked_strip
            
            # Give a tiny delay to ensure selection is processed
            context.area.tag_redraw()
            
            # Now activate crop mode
            return bpy.ops.easycrop.crop('INVOKE_DEFAULT')
        else:
            # No strip clicked - if we have an active strip with crop that's visible, activate immediately
            seq_editor = context.scene.sequence_editor
            active_strip = seq_editor.active_strip if seq_editor else None
            current_frame = context.scene.frame_current
            
            if (active_strip and 
                hasattr(active_strip, 'crop') and 
                is_strip_visible_at_frame(active_strip, current_frame)):
                
                # Check if crop is already active
                if not _crop_active:
                    return bpy.ops.easycrop.crop('INVOKE_DEFAULT')
        
        return {'FINISHED'}
    
    def get_visible_strips(self, context):
        """Get all strips visible at the current frame"""
        scene = context.scene
        if not scene.sequence_editor:
            return []
        
        current_frame = scene.frame_current
        strips = []
        
        for strip in scene.sequence_editor.sequences:
            # Check if strip is visible at current frame
            if is_strip_visible_at_frame(strip, current_frame):
                strips.append(strip)
        
        # Sort by channel (higher channels on top)
        strips.sort(key=lambda s: s.channel)
        
        return strips
    
    def is_mouse_over_strip(self, context, strip, mouse_pos):
        """Check if mouse is over the given strip with flip support"""
        # Use the new flip-aware geometry
        scene = context.scene
        corners, (pivot_x, pivot_y), (scale_x, scale_y, flip_x, flip_y) = get_strip_geometry_with_flip_support(strip, scene)
        
        # Convert to screen space
        view2d = context.region.view2d
        res_x = scene.render.resolution_x
        res_y = scene.render.resolution_y
        
        screen_corners = []
        for corner in corners:
            view_x = corner.x - res_x / 2
            view_y = corner.y - res_y / 2
            screen_co = view2d.view_to_region(view_x, view_y, clip=False)
            screen_corners.append(Vector(screen_co))
        
        return point_in_polygon(mouse_pos, screen_corners)