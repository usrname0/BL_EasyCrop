"""
BL Easy Crop - Drawing and visual rendering

Two primitives - a handle square and the center crop symbol - plus the modal
operator's draw handler. The gizmo tool draws the same two primitives from
gizmos.crop_handles_gizmo, so a handle looks the same under either interface.
"""

import bpy
import gpu
import math
from gpu_extras.batch import batch_for_shader

from .crop_core import (
    get_crop_state, get_draw_data, set_draw_data,
    get_strip_geometry_with_flip_support, handle_screen_angle,
    HANDLE_COLOR, ACCENT_COLOR,
    get_edge_midpoints, is_strip_visible_at_frame,
    res_to_screen, HANDLE_RADIUS, SELECT_RADIUS
)


# --- Shared drawing primitives ---

def draw_crop_symbol_at(center_x, center_y, color=HANDLE_COLOR):
    """Draw the crop symbol (L-brackets + inner rectangle) at a screen position.

    Used by both modal operator drawing and gizmo drawing.

    WARNING: sets its own blend state and puts back what it found. See
    draw_rotated_square for why that belongs here and not in the callers.
    """
    outer_size = 8
    inner_size = 5

    prev_blend = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')

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
    # blend_get() is typed str, blend_set() takes a Literal union - the stubs
    # cannot round-trip their own value.
    gpu.state.blend_set(prev_blend)  # pyright: ignore[reportArgumentType]


def draw_rotated_square(center_x, center_y, half_size, angle, color):
    """Draw a filled square at a screen position, optionally rotated.

    Used by both modal operator drawing and gizmo drawing.

    Args:
        center_x, center_y: Screen position
        half_size: Half the side length in pixels (HANDLE_RADIUS)
        angle: Rotation angle in radians (already flip-compensated)
        color: RGBA tuple

    WARNING: this sets blend state and restores what it found, and that belongs
    here rather than in the callers. The three paths that draw handles are each
    called from a different Blender pass - the gizmo tool's idle draw from the
    gizmo pass, its drag draw and the modal operator's from POST_PIXEL draw
    handlers - and a pass that does not happen to have alpha blending on renders
    this square's color opaque.
    """
    prev_blend = gpu.state.blend_get()
    gpu.state.blend_set('ALPHA')

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

    # blend_get() is typed str, blend_set() takes a Literal union - the stubs
    # cannot round-trip their own value.
    gpu.state.blend_set(prev_blend)  # pyright: ignore[reportArgumentType]


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

    draw_data = get_draw_data()
    if not draw_data:
        set_draw_data({'active_corner': -1})
        draw_data = get_draw_data()

    # mouse_x/mouse_y are absent until the first MOUSEMOVE, so the hover test
    # measures against the region origin for one frame.
    active_corner = draw_data.get('active_corner', -1)
    mouse_x = draw_data.get('mouse_x', 0)
    mouse_y = draw_data.get('mouse_y', 0)

    corners, (pivot_x, pivot_y), _ = \
        get_strip_geometry_with_flip_support(strip, scene)
    edge_midpoints = get_edge_midpoints(corners)

    region = context.region
    if not region:
        return

    view2d = region.view2d
    res_x = scene.render.resolution_x
    res_y = scene.render.resolution_y

    screen_corners = [
        res_to_screen(c.x, c.y, res_x, res_y, view2d) for c in corners
    ]
    screen_midpoints = [
        res_to_screen(m.x, m.y, res_x, res_y, view2d) for m in edge_midpoints
    ]

    screen_center = res_to_screen(pivot_x, pivot_y, res_x, res_y, view2d)
    draw_crop_symbol_at(screen_center[0], screen_center[1])

    hover_corner = _get_hovered_corner(screen_corners, screen_midpoints,
                                       mouse_x, mouse_y)

    # The same angle, from the same helper, that the gizmo tool's two draw
    # paths use. Measuring the on-screen quad needs no flip correction: the
    # quad has already had the mirroring applied to it.
    angle = handle_screen_angle(screen_corners)

    # Corners 0-3 then edge midpoints 4-7, the numbering apply_crop_changes uses.
    for i, pos in enumerate(screen_corners + screen_midpoints):
        highlighted = i == active_corner or i == hover_corner
        draw_rotated_square(pos[0], pos[1], HANDLE_RADIUS, angle,
                            ACCENT_COLOR if highlighted else HANDLE_COLOR)


def _get_hovered_corner(screen_corners, screen_midpoints, mouse_x, mouse_y):
    """The handle nearest the cursor within SELECT_RADIUS, or -1.

    WARNING: this must agree with _get_corner_at_mouse on both the radius and
    the nearest-wins rule. It decides which handle lights up; that one decides
    which handle a click grabs. Any difference between them lights one handle
    and moves another.
    """
    best, best_distance = -1, SELECT_RADIUS

    for i, pos in enumerate(screen_corners + screen_midpoints):
        distance = math.hypot(pos[0] - mouse_x, pos[1] - mouse_y)
        if distance <= best_distance:
            best, best_distance = i, distance

    return best
