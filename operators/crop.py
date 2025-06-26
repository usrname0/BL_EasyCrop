import bpy
import gpu
import math
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from bpy.props import IntProperty, FloatVectorProperty, BoolProperty

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


def draw_crop_handles():
    """Draw function for crop handles"""
    global _crop_active
    
    # Exit immediately if crop mode isn't active
    if not _crop_active or not _draw_data:
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
    
    # Get stored data
    active_corner = _draw_data.get('active_corner', -1)
    
    # Get theme colors - use white for handles like native transforms
    theme = context.preferences.themes[0].sequence_editor
    active_color = (1.0, 1.0, 1.0, 1.0)  # White for active
    handle_color = (1.0, 1.0, 1.0, 0.7)  # Slightly transparent white
    line_color = (1.0, 1.0, 1.0, 0.5)    # More transparent for lines
    
    # Get the cropped corners directly
    res_x = scene.render.resolution_x
    res_y = scene.render.resolution_y
    
    # Force get fresh strip box - don't use the utility function
    # Calculate it directly here to ensure it's up to date
    
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
    
    # Get rotation angle - check multiple possible rotation properties
    angle = 0
    if hasattr(strip, 'rotation_start'):
        angle = math.radians(strip.rotation_start)  # This one is in degrees
    elif hasattr(strip, 'rotation'):
        angle = strip.rotation  # This one might already be in radians
    elif hasattr(strip, 'transform') and hasattr(strip.transform, 'rotation'):
        angle = strip.transform.rotation  # This one is already in radians!
    
    # Calculate the strip's transform following Blender's actual behavior:
    # 1. Start with original strip size
    # 2. Apply crop (removes pixels from edges)
    # 3. Scale the cropped result
    # 4. Position - but rotation pivot stays at original strip center!
    # 5. Rotate around the original strip's center (not cropped center)
    
    # Step 1 & 2: Apply crop to get the actual displayed size
    crop_left = 0
    crop_right = 0  
    crop_bottom = 0
    crop_top = 0
    
    if hasattr(strip, 'crop'):
        crop_left = float(strip.crop.min_x)
        crop_right = float(strip.crop.max_x)
        crop_bottom = float(strip.crop.min_y)
        crop_top = float(strip.crop.max_y)
    
    # Size after crop
    cropped_width = strip_width - crop_left - crop_right
    cropped_height = strip_height - crop_bottom - crop_top
    
    # Step 3: Apply scale
    scaled_width = cropped_width * scale_x
    scaled_height = cropped_height * scale_y
    
    # Step 4: Calculate position
    # The key insight: Blender rotates around the original strip center,
    # but the crop changes where the visible content is relative to that center
    
    # Center of the full scaled strip (if it wasn't cropped)
    full_scaled_width = strip_width * scale_x
    full_scaled_height = strip_height * scale_y
    
    # The rotation pivot (center of original strip)
    pivot_x = res_x / 2 + offset_x
    pivot_y = res_y / 2 + offset_y
    
    # Where the cropped content sits within the full strip space
    # Top-left of the full strip
    full_left = pivot_x - full_scaled_width / 2
    full_bottom = pivot_y - full_scaled_height / 2
    
    # The cropped rectangle within that space
    left = full_left + crop_left * scale_x
    right = full_left + (strip_width - crop_right) * scale_x
    bottom = full_bottom + crop_bottom * scale_y
    top = full_bottom + (strip_height - crop_top) * scale_y
    
    # Calculate center for rotation - this is the pivot point (original strip center)
    center = Vector((pivot_x, pivot_y))
    
    # Create corner vectors
    corners = [
        Vector((left, bottom)),  # Bottom-left
        Vector((left, top)),     # Top-left
        Vector((right, top)),    # Top-right
        Vector((right, bottom))  # Bottom-right
    ]
    
    # Apply rotation if needed
    if angle != 0:
        rotated_corners = []
        for corner in corners:
            rotated = rotate_point(corner, angle, center)
            rotated_corners.append(rotated)
        corners = rotated_corners
    
    # Calculate edge midpoints (after rotation)
    edge_midpoints = []
    for i in range(4):
        next_i = (i + 1) % 4
        midpoint = (corners[i] + corners[next_i]) / 2
        edge_midpoints.append(midpoint)
    
    # Get preview transform - we need to use the View2D system
    region = context.region
    view2d = context.region.view2d
    
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
    
    # Draw crop symbol at center
    if len(screen_corners) == 4:
        # Calculate center of the box
        center_x = sum(c.x for c in screen_corners) / 4
        center_y = sum(c.y for c in screen_corners) / 4
        
        # Draw crop symbol - two overlapping right angles
        symbol_size = 12
        symbol_gap = 4
        
        # First corner (top-left style)
        corner1_points = [
            Vector((center_x - symbol_size + symbol_gap, center_y - symbol_gap)),
            Vector((center_x - symbol_gap, center_y - symbol_gap)),
            Vector((center_x - symbol_gap, center_y - symbol_size + symbol_gap))
        ]
        
        # Second corner (bottom-right style)
        corner2_points = [
            Vector((center_x + symbol_size - symbol_gap, center_y + symbol_gap)),
            Vector((center_x + symbol_gap, center_y + symbol_gap)),
            Vector((center_x + symbol_gap, center_y + symbol_size - symbol_gap))
        ]
        
        # Draw the crop symbol lines
        symbol_color = (1.0, 1.0, 1.0, 0.8)
        
        # First corner
        draw_line(corner1_points[0], corner1_points[1], 2, symbol_color)
        draw_line(corner1_points[1], corner1_points[2], 2, symbol_color)
        
        # Second corner
        draw_line(corner2_points[0], corner2_points[1], 2, symbol_color)
        draw_line(corner2_points[1], corner2_points[2], 2, symbol_color)
    
    # Draw corner handles
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    
    # Draw all handles as rotated squares
    all_handle_positions = screen_corners + screen_midpoints
    
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
    
    # Property to track if activated from tool
    from_tool: BoolProperty(
        name="From Tool",
        default=False,
        options={'SKIP_SAVE', 'HIDDEN'}
    )
    
    # Use class variables that will be set per instance
    active_corner = -1
    mouse_start = (0.0, 0.0)
    crop_start = (0.0, 0.0, 0.0, 0.0)
    timer = None
    first_click = False
    first_mouse_x = 0
    first_mouse_y = 0
    
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
        
        # More lenient check - just need any selected strip with crop
        if scene.sequence_editor.active_strip and hasattr(scene.sequence_editor.active_strip, 'crop'):
            return True
        
        # Also check if any selected strip has crop
        for strip in context.selected_sequences:
            if hasattr(strip, 'crop'):
                return True
                
        return False
    
    def invoke(self, context, event):
        global _draw_handle, _draw_data, _crop_active
        
        # Clean up any existing handler first (safety check for lingering state)
        if _draw_handle is not None:
            try:
                bpy.types.SpaceSequenceEditor.draw_handler_remove(
                    _draw_handle, 'PREVIEW')
            except:
                pass
            _draw_handle = None
        
        # Check if crop is already active (prevent double activation)
        if _crop_active:
            self.report({'WARNING'}, "Crop mode already active")
            return {'CANCELLED'}
        
        # Mark crop as active
        _crop_active = True
        
        # Get the active strip, or the first selected strip
        strip = context.scene.sequence_editor.active_strip
        if not strip or not hasattr(strip, 'crop'):
            # Try to find a selected strip with crop
            for s in context.selected_sequences:
                if hasattr(s, 'crop'):
                    strip = s
                    # Make it active
                    context.scene.sequence_editor.active_strip = s
                    break
        
        # If still no strip, cancel
        if not strip:
            return {'CANCELLED'}
        
        # Check if we're being activated by the tool
        from_tool = False
        tool_active = False
        try:
            # Check if the crop tool is active
            tool = context.workspace.tools.from_space_sequencer('PREVIEW')
            tool_active = (tool and tool.idname == "easycrop.crop_tool")
            # Tool activation is when we have the tool active but not a direct left click
            # (left clicks when tool is active are for handle interaction)
            from_tool = tool_active and event.type != 'LEFTMOUSE'
        except:
            from_tool = False
        
        # Initialize instance variables
        self.active_corner = -1
        self.mouse_start = (0.0, 0.0)
        
        # Store initial crop values
        self.crop_start = (
            strip.crop.min_x,
            strip.crop.max_x,
            strip.crop.min_y,
            strip.crop.max_y
        )
        
        # Initialize draw data
        _draw_data = {
            'active_corner': -1,
            'frame_count': 0
        }
        
        # Set up drawing handler
        _draw_handle = bpy.types.SpaceSequenceEditor.draw_handler_add(
            draw_crop_handles, (), 'PREVIEW', 'POST_PIXEL')
        
        # Add a timer to force redraws
        wm = context.window_manager
        self.timer = wm.event_timer_add(0.01, window=context.window)
        
        # Add modal handler
        wm.modal_handler_add(self)
        
        # If activated from tool button, just show handles
        # If activated from direct interaction, check for handle click
        if self.from_tool:
            # Tool button clicked - just show handles, don't wait for click
            self.first_click = False
        elif event.type == 'LEFTMOUSE':
            # Direct click - check for handle interaction
            self.first_click = True
            self.first_mouse_x = event.mouse_region_x
            self.first_mouse_y = event.mouse_region_y
        else:
            # Keyboard shortcut - just show handles
            self.first_click = False
        
        return {'RUNNING_MODAL'}
    
    def modal(self, context, event):
        global _draw_data
        
        # Handle first click if from direct interaction
        if hasattr(self, 'first_click') and self.first_click:
            self.first_click = False
            # Create a fake mouse event at the stored position
            fake_event = type('obj', (object,), {
                'mouse_region_x': self.first_mouse_x,
                'mouse_region_y': self.first_mouse_y
            })
            corner = self.get_corner_at_mouse(context, fake_event)
            if corner >= 0:
                self.active_corner = corner
                _draw_data['active_corner'] = corner
                self.mouse_start = (self.first_mouse_x, self.first_mouse_y)
                strip = context.scene.sequence_editor.active_strip
                self.crop_start = (
                    strip.crop.min_x,
                    strip.crop.max_x,
                    strip.crop.min_y,
                    strip.crop.max_y
                )
        
        # Handle timer events to force redraw
        if event.type == 'TIMER':
            # Force redraw on timer
            for area in context.screen.areas:
                if area.type == 'SEQUENCE_EDITOR':
                    area.tag_redraw()
        
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
                self.crop_start = (
                    strip.crop.min_x,
                    strip.crop.max_x,
                    strip.crop.min_y,
                    strip.crop.max_y
                )
            else:
                # Not clicking on a handle - exit crop mode
                return self.finish(context)
        
        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            self.active_corner = -1
            _draw_data['active_corner'] = -1
        
        elif event.type == 'MOUSEMOVE' and self.active_corner >= 0:
            self.update_crop(context, event)
        
        elif event.type in {'RET', 'NUMPAD_ENTER'}:
            # Exit crop mode on Enter
            return self.finish(context)
        
        elif event.type == 'ESC':
            # Restore original crop values
            strip.crop.min_x = int(self.crop_start[0])
            strip.crop.max_x = int(self.crop_start[1])
            strip.crop.min_y = int(self.crop_start[2])
            strip.crop.max_y = int(self.crop_start[3])
            return self.finish(context, cancelled=True)
        
        elif event.type in {'G', 'S', 'R'}:
            # Exit crop mode and activate the transform
            self.finish(context)
            # Trigger the transform operator
            if event.type == 'G':
                bpy.ops.transform.translate('INVOKE_DEFAULT')
            elif event.type == 'S':
                bpy.ops.transform.resize('INVOKE_DEFAULT')
            elif event.type == 'R':
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
        if not strip:
            return [], []
        
        # Use the exact same calculation as in draw_crop_handles
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
        
        # Get rotation angle
        angle = 0
        if hasattr(strip, 'rotation_start'):
            angle = math.radians(strip.rotation_start)
        elif hasattr(strip, 'rotation'):
            angle = strip.rotation
        elif hasattr(strip, 'transform') and hasattr(strip.transform, 'rotation'):
            angle = strip.transform.rotation
        
        # Apply transforms following Blender's actual behavior
        # Step 1 & 2: Apply crop to get the actual displayed size
        crop_left = 0
        crop_right = 0  
        crop_bottom = 0
        crop_top = 0
        
        if hasattr(strip, 'crop'):
            crop_left = float(strip.crop.min_x)
            crop_right = float(strip.crop.max_x)
            crop_bottom = float(strip.crop.min_y)
            crop_top = float(strip.crop.max_y)
        
        # Size after crop
        cropped_width = strip_width - crop_left - crop_right
        cropped_height = strip_height - crop_bottom - crop_top
        
        # Step 3: Apply scale
        scaled_width = cropped_width * scale_x
        scaled_height = cropped_height * scale_y
        
        # Step 4: Calculate position
        # Center of the full scaled strip (rotation pivot)
        full_scaled_width = strip_width * scale_x
        full_scaled_height = strip_height * scale_y
        
        pivot_x = res_x / 2 + offset_x
        pivot_y = res_y / 2 + offset_y
        
        # Top-left of the full strip
        full_left = pivot_x - full_scaled_width / 2
        full_bottom = pivot_y - full_scaled_height / 2
        
        # The cropped rectangle within that space
        left = full_left + crop_left * scale_x
        right = full_left + (strip_width - crop_right) * scale_x
        bottom = full_bottom + crop_bottom * scale_y
        top = full_bottom + (strip_height - crop_top) * scale_y
        
        # Calculate center for rotation (the pivot point)
        center = Vector((pivot_x, pivot_y))
        
        # Create corner vectors
        corners = [
            Vector((left, bottom)),  # Bottom-left
            Vector((left, top)),     # Top-left
            Vector((right, top)),    # Top-right
            Vector((right, bottom))  # Bottom-right
        ]
        
        # Apply rotation if needed
        if angle != 0:
            rotated_corners = []
            for corner in corners:
                rotated = rotate_point(corner, angle, center)
                rotated_corners.append(rotated)
            corners = rotated_corners
        
        # Calculate edge midpoints (after rotation)
        edge_midpoints = []
        for i in range(4):
            next_i = (i + 1) % 4
            midpoint = (corners[i] + corners[next_i]) / 2
            edge_midpoints.append(midpoint)
        
        # Use Blender's view2d system for accurate transformation
        view2d = context.region.view2d
        
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
        """Update crop values based on mouse drag"""
        strip = context.scene.sequence_editor.active_strip
        scene = context.scene
        
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
        
        # Get the strip's scale
        strip_scale_x = strip.transform.scale_x if hasattr(strip, 'transform') and hasattr(strip.transform, 'scale_x') else 1.0
        strip_scale_y = strip.transform.scale_y if hasattr(strip, 'transform') and hasattr(strip.transform, 'scale_y') else 1.0
        
        # Handle rotation if present
        angle = 0
        if hasattr(strip, 'rotation_start'):
            angle = -math.radians(strip.rotation_start)  # Negative to reverse rotation, convert from degrees
        elif hasattr(strip, 'transform') and hasattr(strip.transform, 'rotation'):
            angle = -strip.transform.rotation  # Already in radians, just negate
        
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
        
        # Get the original strip dimensions (before crop/scale)
        strip_width = strip.elements[0].orig_width if hasattr(strip, 'elements') and strip.elements else scene.render.resolution_x
        strip_height = strip.elements[0].orig_height if hasattr(strip, 'elements') and strip.elements else scene.render.resolution_y
        
        # Update based on which handle is active
        if self.active_corner < 4:
            # Corner handles (0-3)
            if self.active_corner == 0:  # Bottom-left
                new_min_x = int(max(0, self.crop_start[0] + dx_res))
                new_min_y = int(max(0, self.crop_start[2] + dy_res))
                if new_min_x + strip.crop.max_x < strip_width:
                    strip.crop.min_x = new_min_x
                if new_min_y + strip.crop.max_y < strip_height:
                    strip.crop.min_y = new_min_y
                    
            elif self.active_corner == 1:  # Top-left
                new_min_x = int(max(0, self.crop_start[0] + dx_res))
                new_max_y = int(max(0, self.crop_start[3] - dy_res))
                if new_min_x + strip.crop.max_x < strip_width:
                    strip.crop.min_x = new_min_x
                if strip.crop.min_y + new_max_y < strip_height:
                    strip.crop.max_y = new_max_y
                    
            elif self.active_corner == 2:  # Top-right
                new_max_x = int(max(0, self.crop_start[1] - dx_res))
                new_max_y = int(max(0, self.crop_start[3] - dy_res))
                if strip.crop.min_x + new_max_x < strip_width:
                    strip.crop.max_x = new_max_x
                if strip.crop.min_y + new_max_y < strip_height:
                    strip.crop.max_y = new_max_y
                    
            elif self.active_corner == 3:  # Bottom-right
                new_max_x = int(max(0, self.crop_start[1] - dx_res))
                new_min_y = int(max(0, self.crop_start[2] + dy_res))
                if strip.crop.min_x + new_max_x < strip_width:
                    strip.crop.max_x = new_max_x
                if new_min_y + strip.crop.max_y < strip_height:
                    strip.crop.min_y = new_min_y
        else:
            # Edge handles (4-7)
            edge_index = self.active_corner - 4
            
            if edge_index == 0:  # Left edge (between corners 0 and 1)
                new_min_x = int(max(0, self.crop_start[0] + dx_res))
                if new_min_x + strip.crop.max_x < strip_width:
                    strip.crop.min_x = new_min_x
                    
            elif edge_index == 1:  # Top edge (between corners 1 and 2)
                new_max_y = int(max(0, self.crop_start[3] - dy_res))
                if strip.crop.min_y + new_max_y < strip_height:
                    strip.crop.max_y = new_max_y
                    
            elif edge_index == 2:  # Right edge (between corners 2 and 3)
                new_max_x = int(max(0, self.crop_start[1] - dx_res))
                if strip.crop.min_x + new_max_x < strip_width:
                    strip.crop.max_x = new_max_x
                    
            elif edge_index == 3:  # Bottom edge (between corners 3 and 0)
                new_min_y = int(max(0, self.crop_start[2] + dy_res))
                if new_min_y + strip.crop.max_y < strip_height:
                    strip.crop.min_y = new_min_y