"""
BL Easy Crop - Core functionality and state management

This module contains the core state variables, geometry calculations,
and utility functions that other crop modules depend on.
"""

import bpy
import math
from mathutils import Vector

# Blender 5.0 renamed sequences -> strips throughout the API
_USE_STRIPS_API = bpy.app.version >= (5, 0, 0)

# Global state variables
_draw_handle = None
_draw_data = {}
_crop_active = False


def get_strips(sequence_editor):
    """Get the strip collection from a SequenceEditor (compat for 4.4/5.0)."""
    if _USE_STRIPS_API:
        return sequence_editor.strips
    return sequence_editor.sequences


def get_selected_strips(context):
    """Get selected strips from context (compat for 4.4/5.0)."""
    if _USE_STRIPS_API:
        return context.selected_strips
    return context.selected_sequences


def is_strip_visible_at_frame(strip, frame):
    """Check if a strip is visible at the given frame."""
    return (strip.frame_final_start <= frame <= strip.frame_final_end and not strip.mute)


def point_in_polygon(point, polygon):
    """Check if a point is inside a polygon using ray casting algorithm."""
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
    """Rotate a 2D point around an origin."""
    if origin is None:
        origin = Vector([0, 0])

    cos_a = math.cos(angle)
    sin_a = math.sin(angle)

    x = point.x - origin.x
    y = point.y - origin.y

    new_x = x * cos_a - y * sin_a
    new_y = x * sin_a + y * cos_a

    return Vector([new_x + origin.x, new_y + origin.y])


# --- Shared helper functions ---

def get_strip_flip_state(strip):
    """Get the flip/mirror state of a strip.

    Returns:
        tuple: (flip_x, flip_y) booleans
    """
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

    return flip_x, flip_y


def get_strip_rotation(strip):
    """Get the rotation angle of a strip in radians (raw, without flip compensation)."""
    if hasattr(strip, 'rotation_start'):
        return math.radians(strip.rotation_start)
    elif hasattr(strip, 'rotation'):
        return strip.rotation
    elif hasattr(strip, 'transform') and hasattr(strip.transform, 'rotation'):
        return strip.transform.rotation
    return 0.0


def get_strip_dimensions(strip, scene):
    """Get the original pixel dimensions of a strip.

    Returns:
        tuple: (width, height) in pixels
    """
    strip_width = scene.render.resolution_x
    strip_height = scene.render.resolution_y

    if hasattr(strip, 'elements') and strip.elements and len(strip.elements) > 0:
        elem = strip.elements[0]
        if hasattr(elem, 'orig_width') and hasattr(elem, 'orig_height'):
            strip_width = elem.orig_width
            strip_height = elem.orig_height

    return strip_width, strip_height


def get_edge_midpoints(corners):
    """Calculate edge midpoints from four corner positions.

    Args:
        corners: List of 4 Vector corner positions (BL, TL, TR, BR)

    Returns:
        list: 4 Vector midpoint positions (left, top, right, bottom edges)
    """
    midpoints = []
    for i in range(4):
        next_i = (i + 1) % 4
        midpoints.append((corners[i] + corners[next_i]) / 2)
    return midpoints


def res_to_screen(point_x, point_y, res_x, res_y, view2d):
    """Convert resolution-space coordinates to screen-space via view2d.

    Args:
        point_x, point_y: Position in resolution space
        res_x, res_y: Scene render resolution
        view2d: The region's View2D

    Returns:
        tuple: (screen_x, screen_y) in region pixel coordinates
    """
    return view2d.view_to_region(
        point_x - res_x / 2, point_y - res_y / 2, clip=False)


def compute_crop_delta(dx_pixels, dy_pixels, view2d, strip):
    """Convert a pixel-space drag delta into strip-image-space crop deltas.

    Handles view2d scale conversion, inverse rotation compensation,
    strip scale division, and flip sign compensation.

    Args:
        dx_pixels: Mouse drag delta X in pixels (screen space)
        dy_pixels: Mouse drag delta Y in pixels (screen space)
        view2d: The region's View2D for coordinate conversion
        strip: The strip being cropped

    Returns:
        tuple: (dx_res, dy_res, flip_x, flip_y) where dx_res/dy_res are
               deltas in strip image space, ready for apply_crop_changes().
    """
    # Convert pixel delta to view-space via view2d scale
    p1 = view2d.region_to_view(0, 0)
    p2 = view2d.region_to_view(dx_pixels, dy_pixels)
    dx_view = p2[0] - p1[0]
    dy_view = p2[1] - p1[1]

    # Get strip transform state
    flip_x, flip_y = get_strip_flip_state(strip)

    # Inverse rotation compensation
    angle = -get_strip_rotation(strip)
    if flip_x != flip_y:
        angle = -angle

    if angle != 0:
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        dx_view, dy_view = (dx_view * cos_a - dy_view * sin_a,
                            dx_view * sin_a + dy_view * cos_a)

    # Divide by strip scale
    scale_x = strip.transform.scale_x if hasattr(strip, 'transform') and hasattr(strip.transform, 'scale_x') else 1.0
    scale_y = strip.transform.scale_y if hasattr(strip, 'transform') and hasattr(strip.transform, 'scale_y') else 1.0
    dx_res = dx_view / scale_x
    dy_res = dy_view / scale_y

    # Flip sign compensation
    if flip_x:
        dx_res = -dx_res
    if flip_y:
        dy_res = -dy_res

    return dx_res, dy_res, flip_x, flip_y


def apply_crop_changes(handle_index, strip, dx_res, dy_res, crop_start,
                       strip_width, strip_height, flip_x, flip_y):
    """Apply crop changes based on handle drag.

    Args:
        handle_index: 0-3 for corners (BL, TL, TR, BR), 4-7 for edges (left, top, right, bottom)
        strip: The strip being cropped
        dx_res: Delta X in strip image space
        dy_res: Delta Y in strip image space
        crop_start: Tuple of initial crop values (min_x, max_x, min_y, max_y)
        strip_width: Original strip width in pixels
        strip_height: Original strip height in pixels
        flip_x: Whether strip is flipped on X axis
        flip_y: Whether strip is flipped on Y axis
    """
    if handle_index < 4:
        # Corner handles - remap based on flips
        corner_map = handle_index

        if flip_x and flip_y:
            corner_map = {0: 2, 1: 3, 2: 0, 3: 1}[handle_index]
        elif flip_x:
            corner_map = {0: 3, 1: 2, 2: 1, 3: 0}[handle_index]
        elif flip_y:
            corner_map = {0: 1, 1: 0, 2: 3, 3: 2}[handle_index]

        if corner_map == 0:  # Bottom-left
            new_min_x = int(max(0, crop_start[0] + dx_res))
            if new_min_x + strip.crop.max_x < strip_width:
                strip.crop.min_x = new_min_x
            new_min_y = int(max(0, crop_start[2] + dy_res))
            if new_min_y + strip.crop.max_y < strip_height:
                strip.crop.min_y = new_min_y

        elif corner_map == 1:  # Top-left
            new_min_x = int(max(0, crop_start[0] + dx_res))
            if new_min_x + strip.crop.max_x < strip_width:
                strip.crop.min_x = new_min_x
            new_max_y = int(max(0, crop_start[3] - dy_res))
            if strip.crop.min_y + new_max_y < strip_height:
                strip.crop.max_y = new_max_y

        elif corner_map == 2:  # Top-right
            new_max_x = int(max(0, crop_start[1] - dx_res))
            if strip.crop.min_x + new_max_x < strip_width:
                strip.crop.max_x = new_max_x
            new_max_y = int(max(0, crop_start[3] - dy_res))
            if strip.crop.min_y + new_max_y < strip_height:
                strip.crop.max_y = new_max_y

        elif corner_map == 3:  # Bottom-right
            new_max_x = int(max(0, crop_start[1] - dx_res))
            if strip.crop.min_x + new_max_x < strip_width:
                strip.crop.max_x = new_max_x
            new_min_y = int(max(0, crop_start[2] + dy_res))
            if new_min_y + strip.crop.max_y < strip_height:
                strip.crop.min_y = new_min_y
    else:
        # Edge handles - remap based on flips
        edge_index = handle_index - 4
        edge_map = edge_index

        if flip_x and flip_y:
            edge_map = {0: 2, 1: 3, 2: 0, 3: 1}[edge_index]
        elif flip_x:
            edge_map = {0: 2, 1: 1, 2: 0, 3: 3}[edge_index]
        elif flip_y:
            edge_map = {0: 0, 1: 3, 2: 2, 3: 1}[edge_index]

        if edge_map == 0:  # Left edge
            new_min_x = int(max(0, crop_start[0] + dx_res))
            if new_min_x + strip.crop.max_x < strip_width:
                strip.crop.min_x = new_min_x

        elif edge_map == 1:  # Top edge
            new_max_y = int(max(0, crop_start[3] - dy_res))
            if strip.crop.min_y + new_max_y < strip_height:
                strip.crop.max_y = new_max_y

        elif edge_map == 2:  # Right edge
            new_max_x = int(max(0, crop_start[1] - dx_res))
            if strip.crop.min_x + new_max_x < strip_width:
                strip.crop.max_x = new_max_x

        elif edge_map == 3:  # Bottom edge
            new_min_y = int(max(0, crop_start[2] + dy_res))
            if new_min_y + strip.crop.max_y < strip_height:
                strip.crop.min_y = new_min_y


# --- Strip geometry ---

def get_strip_geometry_with_flip_support(strip, scene):
    """Calculate strip geometry accounting for Mirror X/Y checkboxes.

    Returns corner positions in resolution space.
    """
    res_x = scene.render.resolution_x
    res_y = scene.render.resolution_y

    strip_width, strip_height = get_strip_dimensions(strip, scene)
    flip_x, flip_y = get_strip_flip_state(strip)
    angle = get_strip_rotation(strip)

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

    # Handle flipped coordinates
    if flip_x:
        new_left = res_x - right
        new_right = res_x - left
        left = new_left
        right = new_right
        pivot_x = res_x - pivot_x

    if flip_y:
        new_bottom = res_y - top
        new_top = res_y - bottom
        bottom = new_bottom
        top = new_top
        pivot_y = res_y - pivot_y

    # Create corner vectors
    corners = [
        Vector((left, bottom)),  # Bottom-left
        Vector((left, top)),     # Top-left
        Vector((right, top)),    # Top-right
        Vector((right, bottom))  # Bottom-right
    ]

    # Apply rotation if needed
    if angle != 0:
        # When flipped, rotation direction is reversed
        if flip_x != flip_y:
            angle = -angle

        center = Vector((pivot_x, pivot_y))
        corners = [rotate_point(c, angle, center) for c in corners]

    return corners, (pivot_x, pivot_y), (scale_x, scale_y, flip_x, flip_y)


# --- State management functions ---

def get_crop_state():
    """Get the current crop state."""
    global _crop_active, _draw_data, _draw_handle
    return {
        'active': _crop_active,
        'draw_data': _draw_data.copy(),
        'has_handler': _draw_handle is not None
    }


def set_crop_active(active):
    """Set the crop active state."""
    global _crop_active
    _crop_active = active


def get_draw_data():
    """Get the current draw data."""
    global _draw_data
    return _draw_data


def set_draw_data(data):
    """Set the draw data."""
    global _draw_data
    _draw_data = data


def get_draw_handle():
    """Get the current draw handler."""
    global _draw_handle
    return _draw_handle


def set_draw_handle(handle):
    """Set the draw handler."""
    global _draw_handle
    _draw_handle = handle


def clear_crop_state():
    """Clear all crop state."""
    global _crop_active, _draw_data, _draw_handle
    _crop_active = False
    _draw_data.clear()
    _draw_handle = None
