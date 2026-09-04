"""
BL Easy Crop - Drawing and visual rendering

This module handles all the visual aspects of the crop interface,
including drawing handles, crop outlines, and the crop symbol.

Shared drawing functions (draw_crop_symbol_at, draw_rotated_square) are
used by both the modal operator drawing and the gizmo system.
"""

import bpy
import gpu
import math
from gpu_extras.batch import batch_for_shader

from .crop_core import (
    get_crop_state, get_draw_data,
    get_strip_geometry_with_flip_support, get_strip_rotation,
    get_edge_midpoints, is_strip_visible_at_frame,
    res_to_screen
)


# --- Shared drawing primitives ---

def draw_crop_symbol_at(center_x, center_y, color=(1.0, 1.0, 1.0, 0.8)):
    """Draw the crop symbol (L-brackets + inner rectangle) at a screen position.

    Used by both modal operator drawing and gizmo drawing.
    """
    outer_size = 8
    inner_size = 5

    line_shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.line_width_set(1.5)
    line_shader.bind()
    line_shader.uniform_float("color", color)

    # L-bracket lines: top-left and bottom-right
    bracket_lines = [
        # Top-left L-shape
        [(center_x - outer_size, center_y + 1),
         (center_x - outer_size, center_y + outer_size)],
        [(center_x - outer_size, center_y + outer_size),
         (center_x - 1, center_y + outer_size)],
        # Bottom-right L-shape
        [(center_x + 1, center_y - outer_size),
         (center_x + outer_size, center_y - outer_size)],
        [(center_x + outer_size, center_y - outer_size),
         (center_x + outer_size, center_y - 1)],
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

    # Combine all line segments into a single batch for efficiency
    all_line_verts = []
    for line_verts in bracket_lines + inner_rect_lines:
        all_line_verts.extend(line_verts)

    batch = batch_for_shader(line_shader, 'LINES', {"pos": all_line_verts})
    batch.draw(line_shader)

    gpu.state.line_width_set(1.0)


def draw_rotated_square(center_x, center_y, half_size, angle, color):
    """Draw a filled square at a screen position, optionally rotated.

    Used by both modal operator drawing and gizmo drawing.

    Args:
        center_x, center_y: Screen position
        half_size: Half the side length in pixels (6 = 12px square)
        angle: Rotation angle in radians (already flip-compensated)
        color: RGBA tuple
    """
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')

    if abs(angle) > 0.01:
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)

        corners_rel = [
            (-half_size, -half_size), (half_size, -half_size),
            (half_size, half_size), (-half_size, half_size)
        ]

        vertices = []
        for x_rel, y_rel in corners_rel:
            x = x_rel * cos_a - y_rel * sin_a + center_x
            y = x_rel * sin_a + y_rel * cos_a + center_y
            vertices.append((x, y))

        # Reorder for proper triangle winding
        vertices = [vertices[0], vertices[1], vertices[3], vertices[2]]
    else:
        vertices = [
            (center_x - half_size, center_y - half_size),
            (center_x + half_size, center_y - half_size),
            (center_x - half_size, center_y + half_size),
            (center_x + half_size, center_y + half_size)
        ]

    indices = ((0, 1, 2), (2, 1, 3))

    batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)


# --- Modal operator draw callback ---

def draw_crop_handles():
    """Main draw function for crop handles (called by modal operator's draw handler)."""
    crop_state = get_crop_state()

    if not crop_state['active']:
        return

    context = bpy.context
    if not context.area or context.area.type != 'SEQUENCE_EDITOR':
        return

    scene = context.scene
    if not scene.sequence_editor:
        return

    strip = scene.sequence_editor.active_strip
    if not strip or not hasattr(strip, 'crop'):
        return

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
    mouse_x = draw_data.get('mouse_x', 0)
    mouse_y = draw_data.get('mouse_y', 0)

    # Colors
    active_color = (1.0, 0.5, 0.0, 1.0)  # Orange for active/dragging
    hover_color = (1.0, 0.5, 0.0, 1.0)   # Orange for hover
    handle_color = (1.0, 1.0, 1.0, 0.7)  # White for normal

    # Get current geometry
    corners, (pivot_x, pivot_y), (scale_x, scale_y, flip_x, flip_y) = \
        get_strip_geometry_with_flip_support(strip, scene)
    edge_midpoints = get_edge_midpoints(corners)

    region = context.region
    if not region:
        return

    view2d = region.view2d
    res_x = scene.render.resolution_x
    res_y = scene.render.resolution_y

    # Transform to screen coordinates
    screen_corners = [
        res_to_screen(c.x, c.y, res_x, res_y, view2d) for c in corners
    ]
    screen_midpoints = [
        res_to_screen(m.x, m.y, res_x, res_y, view2d) for m in edge_midpoints
    ]

    # Draw crop symbol at center
    screen_center = res_to_screen(pivot_x, pivot_y, res_x, res_y, view2d)
    draw_crop_symbol_at(screen_center[0], screen_center[1])

    # Detect hover for feedback
    hover_corner = _get_hovered_corner(screen_corners, screen_midpoints,
                                       mouse_x, mouse_y)

    # Get rotation angle with flip compensation for handle drawing
    angle = get_strip_rotation(strip)
    if flip_x != flip_y:
        angle = -angle

    # Draw corner and edge handles
    all_handle_positions = screen_corners + screen_midpoints
    for i, pos in enumerate(all_handle_positions):
        if i == active_corner:
            color = active_color
        elif i == hover_corner:
            color = hover_color
        else:
            color = handle_color

        draw_rotated_square(pos[0], pos[1], 6, angle, color)


def _get_hovered_corner(screen_corners, screen_midpoints, mouse_x, mouse_y):
    """Detect which handle is being hovered over."""
    all_handle_positions = screen_corners + screen_midpoints
    threshold = 15

    for i, pos in enumerate(all_handle_positions):
        distance = math.hypot(pos[0] - mouse_x, pos[1] - mouse_y)
        if distance <= threshold:
            return i
    return -1
