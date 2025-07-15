"""
BL Easy Crop - Core functionality and state management

This module contains the core state variables, geometry calculations,
and utility functions that other crop modules depend on.
"""

import bpy
import math
from mathutils import Vector

# Global state variables
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


def rotate_point(point, angle, origin=None):
    """Rotate a 2D point around an origin"""
    if origin is None:
        origin = Vector([0, 0])
    
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    
    # Translate to origin
    x = point.x - origin.x
    y = point.y - origin.y
    
    # Rotate
    new_x = x * cos_a - y * sin_a
    new_y = x * sin_a + y * cos_a
    
    # Translate back
    return Vector([new_x + origin.x, new_y + origin.y])


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


def get_crop_state():
    """Get the current crop state"""
    global _crop_active, _draw_data, _draw_handle
    return {
        'active': _crop_active,
        'draw_data': _draw_data.copy(),
        'has_handler': _draw_handle is not None
    }


def set_crop_active(active):
    """Set the crop active state"""
    global _crop_active
    _crop_active = active


def get_draw_data():
    """Get the current draw data"""
    global _draw_data
    return _draw_data


def set_draw_data(data):
    """Set the draw data"""
    global _draw_data
    _draw_data = data


def get_draw_handle():
    """Get the current draw handler"""
    global _draw_handle
    return _draw_handle


def set_draw_handle(handle):
    """Set the draw handler"""
    global _draw_handle
    _draw_handle = handle


def clear_crop_state():
    """Clear all crop state"""
    global _crop_active, _draw_data, _draw_handle
    _crop_active = False
    _draw_data.clear()
    _draw_handle = None