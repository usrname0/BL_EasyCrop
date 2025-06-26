import bpy
import math
from mathutils import Vector


def get_preview_offset():
    """Get the offset and scale of the preview region"""
    context = bpy.context
    scene = context.scene
    region = context.region
    
    render = scene.render
    res_x = render.resolution_x
    res_y = render.resolution_y
    
    # Get region dimensions
    region_width = region.width
    region_height = region.height
    
    # Calculate aspect ratios
    render_aspect = res_x / res_y
    region_aspect = region_width / region_height
    
    # Calculate scale and offset
    if render_aspect > region_aspect:
        # Fit to width
        preview_zoom = region_width / res_x
        offset_x = 0
        offset_y = (region_height - (res_y * preview_zoom)) / 2
    else:
        # Fit to height
        preview_zoom = region_height / res_y
        offset_x = (region_width - (res_x * preview_zoom)) / 2
        offset_y = 0
    
    # Factor for proxy/preview render size
    proxy_fac = 1.0
    if hasattr(context.space_data, 'proxy_render_size'):
        proxy_sizes = {
            'NONE': 1.0,
            'SCENE': 1.0,
            'FULL': 1.0,
            'PROXY_100': 1.0,
            'PROXY_75': 0.75,
            'PROXY_50': 0.5,
            'PROXY_25': 0.25
        }
        proxy_key = context.space_data.proxy_render_size
        proxy_fac = proxy_sizes.get(proxy_key, 1.0)
    
    return offset_x, offset_y, proxy_fac, preview_zoom


def mouse_to_res(mouse_vec):
    """Convert mouse coordinates to resolution coordinates"""
    offset_x, offset_y, fac, preview_zoom = get_preview_offset()
    
    x = (mouse_vec.x - offset_x) / (preview_zoom * fac)
    y = (mouse_vec.y - offset_y) / (preview_zoom * fac)
    
    return Vector([x, y])


def get_strip_corners(strip):
    """Get the four corners of a strip in resolution space"""
    scene = bpy.context.scene
    res_x = scene.render.resolution_x
    res_y = scene.render.resolution_y
    
    # Handle different strip types
    if strip.type == 'TRANSFORM':
        left, right, bottom, top = get_transform_box(strip)
    else:
        left, right, bottom, top = get_strip_box(strip)
    
    # Apply rotation if applicable
    angle = 0
    if hasattr(strip, 'rotation_start'):
        angle = math.radians(strip.rotation_start)
    elif strip.type == 'TRANSFORM':
        angle = math.radians(strip.rotation_start)
    
    # Calculate corners
    bl = Vector([left, bottom])
    tl = Vector([left, top])
    tr = Vector([right, top])
    br = Vector([right, bottom])
    
    # Rotate if needed
    if angle != 0:
        origin = Vector([(left + right) / 2, (bottom + top) / 2])
        bl = rotate_point(bl, angle, origin)
        tl = rotate_point(tl, angle, origin)
        tr = rotate_point(tr, angle, origin)
        br = rotate_point(br, angle, origin)
    
    return [bl, tl, tr, br]


def get_strip_box(strip):
    """Get the bounding box of a strip (without transform modifier)"""
    scene = bpy.context.scene
    res_x = scene.render.resolution_x
    res_y = scene.render.resolution_y
    
    # Get actual strip dimensions
    if hasattr(strip, 'elements') and strip.elements:
        # Image/movie strip
        elem = strip.elements[0]
        strip_width = elem.orig_width
        strip_height = elem.orig_height
    else:
        # Default to render resolution
        strip_width = res_x
        strip_height = res_y
    
    # Apply scale and offset
    scale_x = 1.0
    scale_y = 1.0
    offset_x = 0
    offset_y = 0
    
    # Check for transforms (handles both old and new transform systems)
    if hasattr(strip, 'transform'):
        # Direct transform properties (Blender 4.0+)
        offset_x = strip.transform.offset_x
        offset_y = strip.transform.offset_y
        
        # Some strips might have scale in transform
        if hasattr(strip.transform, 'scale_x'):
            scale_x = strip.transform.scale_x
            scale_y = strip.transform.scale_y
    
    # Also check use_translation for compatibility
    if hasattr(strip, 'use_translation') and strip.use_translation:
        if hasattr(strip, 'transform'):
            offset_x = strip.transform.offset_x
            offset_y = strip.transform.offset_y
            if hasattr(strip.transform, 'scale_x'):
                scale_x = strip.transform.scale_x
                scale_y = strip.transform.scale_y
    
    # Calculate scaled dimensions
    scaled_width = strip_width * scale_x
    scaled_height = strip_height * scale_y
    
    # Calculate position (centered by default, then offset)
    left = (res_x - scaled_width) / 2 + offset_x
    right = (res_x + scaled_width) / 2 + offset_x
    bottom = (res_y - scaled_height) / 2 + offset_y
    top = (res_y + scaled_height) / 2 + offset_y
    
    # Apply crop if enabled
    if hasattr(strip, 'use_crop') and strip.use_crop and hasattr(strip, 'crop'):
        # Crop values are in original image space, so we need to scale them
        left += strip.crop.min_x * scale_x
        right -= strip.crop.max_x * scale_x
        bottom += strip.crop.min_y * scale_y
        top -= strip.crop.max_y * scale_y
    
    return left, right, bottom, top


def get_transform_box(strip):
    """Get the bounding box of a transform strip"""
    if strip.type != 'TRANSFORM':
        return get_strip_box(strip)
    
    scene = bpy.context.scene
    res_x = scene.render.resolution_x
    res_y = scene.render.resolution_y
    
    # Get position
    pos_x = get_pos_x(strip)
    pos_y = get_pos_y(strip)
    
    # Get scale
    scale_x = strip.scale_start_x
    scale_y = strip.scale_start_y
    
    # Calculate dimensions
    strip_in = strip.input_1
    if strip_in:
        # Get input dimensions
        if hasattr(strip_in, 'elements') and strip_in.elements:
            orig_width = strip_in.elements[0].orig_width
            orig_height = strip_in.elements[0].orig_height
        else:
            orig_width = res_x
            orig_height = res_y
        
        # Apply input crop
        if hasattr(strip_in, 'use_crop') and strip_in.use_crop and hasattr(strip_in, 'crop'):
            crop_width = orig_width - strip_in.crop.min_x - strip_in.crop.max_x
            crop_height = orig_height - strip_in.crop.min_y - strip_in.crop.max_y
        else:
            crop_width = orig_width
            crop_height = orig_height
        
        # Calculate final dimensions
        width = (crop_width * scale_x * res_x) / orig_width
        height = (crop_height * scale_y * res_y) / orig_height
    else:
        width = res_x * scale_x
        height = res_y * scale_y
    
    # Calculate bounds
    left = pos_x - width / 2
    right = pos_x + width / 2
    bottom = pos_y - height / 2
    top = pos_y + height / 2
    
    return left, right, bottom, top


def get_pos_x(strip):
    """Get X position of a transform strip"""
    if strip.type != 'TRANSFORM':
        return 0
    
    scene = bpy.context.scene
    res_x = scene.render.resolution_x
    
    if strip.translation_unit == 'PERCENT':
        return res_x * (strip.translate_start_x / 100.0) + res_x / 2
    else:
        return strip.translate_start_x + res_x / 2


def get_pos_y(strip):
    """Get Y position of a transform strip"""
    if strip.type != 'TRANSFORM':
        return 0
    
    scene = bpy.context.scene
    res_y = scene.render.resolution_y
    
    if strip.translation_unit == 'PERCENT':
        return res_y * (strip.translate_start_y / 100.0) + res_y / 2
    else:
        return strip.translate_start_y + res_y / 2


def set_pos_x(strip, value):
    """Set X position of a transform strip"""
    if strip.type != 'TRANSFORM':
        return 0
    
    scene = bpy.context.scene
    res_x = scene.render.resolution_x
    
    if strip.translation_unit == 'PERCENT':
        return ((value - res_x / 2) * 100.0) / res_x
    else:
        return value - res_x / 2


def set_pos_y(strip, value):
    """Set Y position of a transform strip"""
    if strip.type != 'TRANSFORM':
        return 0
    
    scene = bpy.context.scene
    res_y = scene.render.resolution_y
    
    if strip.translation_unit == 'PERCENT':
        return ((value - res_y / 2) * 100.0) / res_y
    else:
        return value - res_y / 2


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


def get_group_box(strips):
    """Get the bounding box that encompasses all strips"""
    if not strips:
        return 0, 0, 0, 0
    
    scene = bpy.context.scene
    res_x = scene.render.resolution_x
    res_y = scene.render.resolution_y
    
    # Initialize with first strip
    first_strip = strips[0]
    if first_strip.type == 'TRANSFORM':
        left, right, bottom, top = get_transform_box(first_strip)
    else:
        left, right, bottom, top = get_strip_box(first_strip)
    
    # Expand to include all strips
    for strip in strips[1:]:
        if strip.type == 'TRANSFORM':
            s_left, s_right, s_bottom, s_top = get_transform_box(strip)
        else:
            s_left, s_right, s_bottom, s_top = get_strip_box(strip)
        
        left = min(left, s_left)
        right = max(right, s_right)
        bottom = min(bottom, s_bottom)
        top = max(top, s_top)
    
    return left, right, bottom, top