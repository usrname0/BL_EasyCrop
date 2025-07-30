"""
BL Easy Crop - Drawing and visual rendering

This module handles all the visual aspects of the crop interface,
including drawing handles, crop outlines, and the crop symbol.
"""

import bpy
import gpu
import math
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from .crop_core import (
    get_crop_state, get_draw_data, 
    get_strip_geometry_with_flip_support, is_strip_visible_at_frame
)


def draw_line(v1, v2, width, color):
    """Draw a line between two points"""
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.line_width_set(width)
    vertices = [v1, v2]
    batch = batch_for_shader(shader, 'LINES', {"pos": vertices})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)
    gpu.state.line_width_set(1.0)


def draw_crop_handles():
    """Main draw function for crop handles"""
    crop_state = get_crop_state()
    
    # Exit immediately if crop mode isn't active
    if not crop_state['active']:
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
    
    # Get stored data
    draw_data = get_draw_data()
    if not draw_data:
        from .crop_core import set_draw_data
        set_draw_data({'active_corner': -1, 'frame_count': 0})
        draw_data = get_draw_data()
    
    active_corner = draw_data.get('active_corner', -1)
    
    # Get mouse position for hover detection (stored by modal operator)
    mouse_x = draw_data.get('mouse_x', 0)  
    mouse_y = draw_data.get('mouse_y', 0)
    
    # Get theme colors - match gizmo version
    active_color = (1.0, 0.5, 0.0, 1.0)  # Orange for active/dragging (like gizmo)
    hover_color = (1.0, 0.5, 0.0, 1.0)   # Orange for hover (like gizmo)
    handle_color = (1.0, 1.0, 1.0, 0.7)  # White for normal
    line_color = (1.0, 1.0, 1.0, 0.5)
    
    # Get current geometry
    corners, (pivot_x, pivot_y), (scale_x, scale_y, flip_x, flip_y) = get_strip_geometry_with_flip_support(strip, scene)
    
    # Calculate edge midpoints
    edge_midpoints = []
    for i in range(4):
        next_i = (i + 1) % 4
        midpoint = (corners[i] + corners[next_i]) / 2
        edge_midpoints.append(midpoint)
    
    # Get preview transform
    region = context.region
    if not region:
        return
    
    view2d = context.region.view2d
    res_x = scene.render.resolution_x
    res_y = scene.render.resolution_y
    
    # Transform to screen coordinates
    screen_corners = []
    for corner in corners:
        view_x = corner.x - res_x / 2
        view_y = corner.y - res_y / 2
        screen_co = view2d.view_to_region(view_x, view_y, clip=False)
        screen_corners.append(Vector(screen_co))
    
    screen_midpoints = []
    for midpoint in edge_midpoints:
        view_x = midpoint.x - res_x / 2
        view_y = midpoint.y - res_y / 2
        screen_co = view2d.view_to_region(view_x, view_y, clip=False)
        screen_midpoints.append(Vector(screen_co))
    
    
    # Draw crop symbol at center
    _draw_crop_symbol(view2d, pivot_x, pivot_y, res_x, res_y)
    
    # Detect hover for feedback
    hover_corner = _get_hovered_corner(screen_corners, screen_midpoints, mouse_x, mouse_y)
    
    # Draw corner and edge handles
    _draw_crop_handles(screen_corners, screen_midpoints, active_corner, hover_corner, strip, flip_x, flip_y, active_color, hover_color, handle_color)


def _draw_crop_symbol(view2d, pivot_x, pivot_y, res_x, res_y):
    """Draw the crop symbol at the strip center"""
    # Transform to screen coordinates
    screen_center = view2d.view_to_region(
        pivot_x - res_x / 2,
        pivot_y - res_y / 2,
        clip=False
    )
    center_x = screen_center[0]
    center_y = screen_center[1]
    
    # Draw clean white crop symbol
    white_color = (1.0, 1.0, 1.0, 0.8)
    line_shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    
    # Symbol dimensions
    outer_size = 8
    inner_size = 5
    
    gpu.state.line_width_set(1.5)
    line_shader.bind()
    line_shader.uniform_float("color", white_color)
    
    # Corner brackets
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


def _get_hovered_corner(screen_corners, screen_midpoints, mouse_x, mouse_y):
    """Detect which handle is being hovered over"""
    all_handle_positions = screen_corners + screen_midpoints
    threshold = 15  # Same threshold as modal operator
    
    for i, pos in enumerate(all_handle_positions):
        distance = ((pos.x - mouse_x)**2 + (pos.y - mouse_y)**2)**0.5
        if distance <= threshold:
            return i
    return -1


def _draw_crop_handles(screen_corners, screen_midpoints, active_corner, hover_corner, strip, flip_x, flip_y, active_color, hover_color, handle_color):
    """Draw the corner and edge handles"""
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    
    all_handle_positions = screen_corners + screen_midpoints
    
    # Get rotation angle for handle orientation with flip compensation
    angle = 0
    if hasattr(strip, 'rotation_start'):
        angle = math.radians(strip.rotation_start)
    elif hasattr(strip, 'rotation'):
        angle = strip.rotation
    elif hasattr(strip, 'transform') and hasattr(strip.transform, 'rotation'):
        angle = strip.transform.rotation
    
    # Apply flip compensation - match crop_core.py logic
    if flip_x != flip_y:  # XOR - if only one axis is flipped
        angle = -angle
    
    for i, pos in enumerate(all_handle_positions):
        # Determine color based on state - consistent size like gizmo version
        size = 6  # Consistent size for all states
        
        if i == active_corner:
            # Active/dragging - white
            color = active_color
        elif i == hover_corner:
            # Hovered - orange like gizmo version
            color = hover_color
        else:
            # Normal - white but dimmer
            color = handle_color
        
        # Create handle vertices - rotated to match strip
        if abs(angle) > 0.01:  # If strip is rotated
            # Calculate handle rotation - use edge-based calculation for consistency
            if i < 4:  # Corner handle - calculate from adjacent edges like edge handles do
                # For corner handles, use the same edge-based approach as edge handles
                # This ensures consistent rotation between corners and edges
                corner_idx = i
                # Get the two edges adjacent to this corner
                prev_edge_idx = (corner_idx - 1) % 4
                next_edge_idx = corner_idx
                
                # Calculate average angle of the two adjacent edges
                prev_corner1 = prev_edge_idx
                prev_corner2 = (prev_edge_idx + 1) % 4
                next_corner1 = next_edge_idx  
                next_corner2 = (next_edge_idx + 1) % 4
                
                prev_edge_vec = screen_corners[prev_corner2] - screen_corners[prev_corner1]
                next_edge_vec = screen_corners[next_corner2] - screen_corners[next_corner1]
                
                prev_edge_angle = math.atan2(prev_edge_vec.y, prev_edge_vec.x)
                next_edge_angle = math.atan2(next_edge_vec.y, next_edge_vec.x)
                
                # Use the average angle, or just use one of them for simplicity
                handle_angle = next_edge_angle - math.pi / 2  # Perpendicular to edge like edge handles
            else:  # Edge handle - align with edge direction (unchanged)
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
            
            vertices = [vertices[0], vertices[1], vertices[3], vertices[2]]
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