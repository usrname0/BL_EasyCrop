"""
BL Easy Crop - Core functionality and state management

The one source of strip geometry and crop maths. Both interfaces - the gizmo
tool and the modal operator - go through here, which is what stops them
disagreeing about where a handle belongs on a flipped or rotated strip.
"""

import bpy
import math
from mathutils import Vector

# Blender 5.0 renamed sequences -> strips throughout the API
_USE_STRIPS_API = bpy.app.version >= (5, 0, 0)

# Region pixels. A handle is drawn small enough not to hide the corner it
# marks, and grabbed from a good deal further out than it is drawn.
#
# WARNING: one grab radius, shared. The gizmo tool gets its highlight from the
# same test_select that decides the grab, so the two cannot disagree there; the
# modal operator hit-tests and highlights in Python, so it has to be held to the
# same number by hand. A hover radius wider than the grab radius leaves a ring
# where a handle is lit and a click misses it.
HANDLE_RADIUS = 6.0
SELECT_RADIUS = 25.0

# One palette, shared. The gizmo tool drew its white handles at alpha 0.8 and
# the modal operator drew the same handles at 0.7, which is a visible step
# between the two interfaces for no reason anyone recorded. 0.8 is the gizmo's,
# and the gizmo is the primary interface.
HANDLE_COLOR = (1.0, 1.0, 1.0, 0.8)
ACCENT_COLOR = (1.0, 0.5, 0.0, 1.0)

# The modal operator's session state, at module level because its draw handler
# is a plain function that Blender calls with no reference to the operator.
_draw_handle = None    # the PREVIEW draw handler, or None when not drawing
_draw_data = {}        # what that handler needs: active_corner, mouse_x, mouse_y
_crop_active = False   # a modal crop is running, so the gizmo tool stands down


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
                    # xinters looks possibly-unbound and is not: the tests above
                    # require y > min(p1y, p2y) and y <= max(p1y, p2y), which no
                    # y satisfies when p1y == p2y, so a horizontal edge never
                    # reaches the read.
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
    """Get the Mirror X / Mirror Y state of a strip.

    Returns:
        tuple: (flip_x, flip_y) booleans
    """
    return strip.use_flip_x, strip.use_flip_y


def get_strip_rotation(strip):
    """Get the rotation angle of a strip in radians (raw, without flip compensation).

    WARNING: strip.transform.rotation is the only source, and it is already in
    radians. Do not add a fallback to a strip-level rotation attribute: the
    obvious names are degrees elsewhere in Blender, and a wrongly converted
    angle draws handles in confidently wrong places rather than raising.
    """
    return strip.transform.rotation


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
    # Resolution space has its origin at the bottom-left of the frame; the
    # preview's View2D has its origin at the frame center.
    return view2d.view_to_region(
        point_x - res_x / 2, point_y - res_y / 2, clip=False)


def handle_screen_angle(screen_corners):
    """The angle every crop handle is drawn at, from the quad's first edge.

    Args:
        screen_corners: the four corners in region pixels, BL TL TR BR.
            Indexed, not attribute-accessed, so tuples and Vectors both work -
            the three call sites do not agree on which they carry.

    Returns:
        float: radians, 0 for an unrotated strip

    One angle for all nine handles, and one derivation for both draw paths -
    the gizmo group's refresh() and the hand-drawn pass that replaces it during
    a drag. Both used to work it out for themselves and they disagreed twice
    over:

    - refresh() gave each handle the angle of the edge it sits on, 90 degrees
      further round for each successive handle. A square is symmetric under 90
      degrees so the shape was identical, but draw_rotated_square cuts its
      square into triangles by fixed vertex index, so the split diagonal turned
      with the angle. 6 of 8 handles ended up split the other way from the drag
      path, which is visible as the two sets of handles being anti-aliased
      differently at the instant a drag starts.
    - The drag path derived the angle from transform.rotation and negated it
      when the flips differed, which is a second way of computing the same
      number and a second thing to keep in step.

    Measuring the edge on screen needs neither the raw rotation nor the flip
    correction: the quad has already had both applied to it. It also needs no
    zero threshold, because an unrotated strip's first edge points exactly at
    +Y and this returns exactly 0.
    """
    edge_x = screen_corners[1][0] - screen_corners[0][0]
    edge_y = screen_corners[1][1] - screen_corners[0][1]
    return math.atan2(edge_y, edge_x) - math.pi / 2


def handle_window_position(strip, scene, region, handle_index):
    """Where a handle sits right now, in window pixels, for cursor_warp.

    handle_index is the flat numbering both interfaces hit-test with: 0-3 are
    the corners, 4-7 the edge midpoints. The geometry is read fresh rather than
    taken from the drag, so the answer is where the handle actually ended up
    after the limits had their say.

    Returns:
        tuple: (x, y) in window coordinates, or None if the geometry is not
        available.

    The result is clamped to the region. A handle can legitimately sit outside
    it - zoom the preview in far enough and the crop rect leaves the view - and
    putting the pointer down outside the editor is worse than putting it at the
    edge nearest the handle. cursor_warp takes window coordinates, not region
    ones, which is the easy half of this to get wrong.
    """
    if not strip or not hasattr(strip, 'crop') or not region or not region.view2d:
        return None

    corners, _, _ = get_strip_geometry_with_flip_support(strip, scene)
    if handle_index < 4:
        handle_pos = corners[handle_index]
    else:
        handle_pos = get_edge_midpoints(corners)[handle_index - 4]

    screen_x, screen_y = res_to_screen(
        handle_pos.x, handle_pos.y,
        scene.render.resolution_x, scene.render.resolution_y, region.view2d)

    x = min(max(int(screen_x), 0), max(region.width - 1, 0))
    y = min(max(int(screen_y), 0), max(region.height - 1, 0))
    return (region.x + x, region.y + y)


def compute_crop_delta(dx_pixels, dy_pixels, view2d, strip):
    """Convert a pixel-space drag delta into strip-image-space crop deltas.

    Args:
        dx_pixels: Mouse drag delta X in pixels (screen space)
        dy_pixels: Mouse drag delta Y in pixels (screen space)
        view2d: The region's View2D for coordinate conversion
        strip: The strip being cropped

    Returns:
        tuple: (dx_res, dy_res, flip_x, flip_y) where dx_res/dy_res are
               deltas in strip image space, ready for apply_crop_changes().
    """
    # Two points rather than one, so the view2d's zoom is measured rather than
    # assumed - region_to_view is affine, not linear.
    p1 = view2d.region_to_view(0, 0)
    p2 = view2d.region_to_view(dx_pixels, dy_pixels)
    dx_view = p2[0] - p1[0]
    dy_view = p2[1] - p1[1]

    flip_x, flip_y = get_strip_flip_state(strip)

    # Undo the strip's own transform to get back to image space: rotate the
    # delta the other way, then divide out the scale. Mirroring on one axis
    # reverses which way the strip turns, so the inverse turns back the other
    # way too.
    angle = -get_strip_rotation(strip)
    if flip_x != flip_y:
        angle = -angle

    if angle != 0:
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        dx_view, dy_view = (dx_view * cos_a - dy_view * sin_a,
                            dx_view * sin_a + dy_view * cos_a)

    dx_res = dx_view / strip.transform.scale_x
    dy_res = dy_view / strip.transform.scale_y

    # On a mirrored axis, dragging right moves the image left.
    if flip_x:
        dx_res = -dx_res
    if flip_y:
        dy_res = -dy_res

    return dx_res, dy_res, flip_x, flip_y


# strip.crop property names, in the order the (min_x, max_x, min_y, max_y)
# tuples used throughout this module are laid out.
CROP_PROPS = ("min_x", "max_x", "min_y", "max_y")


def map_handle(handle_index, flip_x, flip_y):
    """Resolve a handle index to the one it addresses on a flipped strip.

    Mirroring a strip swaps which crop field a given on-screen handle drives:
    the handle drawn on the left edge of a flipped strip is the one that moves
    max_x. Corners and edges remap differently, hence the two tables.

    WARNING: flip compensation happens exactly once, and this is where. Callers
    pass the raw handle index and the strip's flip state and get back an index
    into the unflipped layout; compensating again in the drawing or gizmo layer
    double-applies it, which lands the handles correctly when both axes are
    flipped and wrongly when only one is.

    Args:
        handle_index: 0-3 for corners (BL, TL, TR, BR), 4-7 for edges
            (left, top, right, bottom)
        flip_x: Whether strip is flipped on X axis
        flip_y: Whether strip is flipped on Y axis

    Returns:
        int: the equivalent handle index with flips resolved
    """
    if handle_index < 4:
        if flip_x and flip_y:
            return {0: 2, 1: 3, 2: 0, 3: 1}[handle_index]
        if flip_x:
            return {0: 3, 1: 2, 2: 1, 3: 0}[handle_index]
        if flip_y:
            return {0: 1, 1: 0, 2: 3, 3: 2}[handle_index]
        return handle_index

    edge_index = handle_index - 4
    if flip_x and flip_y:
        edge_index = {0: 2, 1: 3, 2: 0, 3: 1}[edge_index]
    elif flip_x:
        edge_index = {0: 2, 1: 1, 2: 0, 3: 3}[edge_index]
    elif flip_y:
        edge_index = {0: 0, 1: 3, 2: 2, 3: 1}[edge_index]
    return edge_index + 4


def crop_props_for_handle(handle_index, flip_x, flip_y):
    """The strip.crop property names a handle actually moves.

    A corner moves two, an edge moves one. Used to key only what the drag
    touched - see autokey_crop.
    """
    x_move, y_move = _HANDLE_FIELDS[map_handle(handle_index, flip_x, flip_y)]
    return tuple(CROP_PROPS[move[0]] for move in (x_move, y_move)
                 if move is not None)


def autokey_crop(context, strip, handle_index, flip_x, flip_y):
    """Insert keyframes for the crop channels this drag moved, if auto-key is on.

    Auto-keying is not a property-level hook - it is something operators
    invoke - so writing strip.crop through RNA inserts nothing on its own, no
    matter what the toggle says. Any drag that wants to honor the setting has
    to key for itself.

    WARNING: read the flag from context.tool_settings, never from a scene
    looked up by hand. tool_settings is per-scene, the UI toggle writes the
    *window* scene's copy, and since 5.0 that need not be the scene the
    sequencer is showing. Reading the wrong one fails silently.

    WARNING: key only the channels the handle moved. Keying all four is the
    tempting simplification and it silently commits channels the user never
    touched, which they then have to find and delete.

    Call this before ed.undo_push, so the keys land in the same undo step as
    the edit.
    """
    tool_settings = getattr(context, "tool_settings", None)
    if tool_settings is None or not tool_settings.use_keyframe_insert_auto:
        return ()

    frame = context.scene.frame_current
    keyed = crop_props_for_handle(handle_index, flip_x, flip_y)
    for prop in keyed:
        strip.crop.keyframe_insert(prop, frame=frame, group="Crop")
    return keyed


# Which crop field each handle moves, and in which direction.
#
# Fields are indexed into the (min_x, max_x, min_y, max_y) tuple used
# throughout this module. A corner moves one field per axis; an edge moves one
# field and leaves the other axis alone. Dragging right (+dx) grows min_x but
# shrinks max_x, hence the signs.
#
#   index: (x_field, x_sign) or None, (y_field, y_sign) or None
_HANDLE_FIELDS = {
    0: ((0, 1.0), (2, 1.0)),    # corner bottom-left
    1: ((0, 1.0), (3, -1.0)),   # corner top-left
    2: ((1, -1.0), (3, -1.0)),  # corner top-right
    3: ((1, -1.0), (2, 1.0)),   # corner bottom-right
    4: ((0, 1.0), None),        # edge left
    5: (None, (3, -1.0)),       # edge top
    6: ((1, -1.0), None),       # edge right
    7: (None, (2, 1.0)),        # edge bottom
}

# The field on the same axis that the handle is not moving, whose value the
# opposite-edge collision test has to add in.
_OPPOSITE_FIELD = {0: 1, 1: 0, 2: 3, 3: 2}


def apply_crop_changes(handle_index, strip, dx_res, dy_res, crop_base,
                       strip_width, strip_height, flip_x, flip_y):
    """Accumulate one event's drag delta onto crop_base, write it, return it.

    WARNING: crop_base is the crop this drag last *accepted*, not the crop the
    drag started from, and dx_res/dy_res are the movement since the previous
    mouse event, not since the drag began. Feed the return value back in as
    crop_base on the next event.

    Two limits constrain the move: crop values cannot go negative, and the two
    crops on an axis cannot meet. Neither is enforced by RNA - the sidebar will
    happily set min_x + max_x past the strip width - so both live here.

    A blocked move is projected to the nearest allowed value, never refused.
    Refusing strands the user: the crop stops while the cursor travels on, and
    every pixel of that invisible travel has to be dragged back before the edge
    moves again. Accumulating onto the last accepted value, and projecting
    rather than dropping the move, means the crop settles against the limit and
    moves again on the first event heading back off it.

    A crop that is already past the limit when the drag starts is the one case
    projection alone gets wrong, because clamping would snap it a long way on
    the first nudge. There the move is taken only if it improves matters, which
    lets the handles walk out of a state the sidebar allows but dragging could
    never have produced.

    The two axes are accepted independently, so a drag running at a shallow
    angle into a limit still slides along it instead of stopping dead.

    crop_base carries floats even though strip.crop holds integers. Rounding
    the running value every event would swallow any motion smaller than a
    pixel, which stalls a slow drag completely; only the write is integral.

    Args:
        handle_index: 0-3 for corners (BL, TL, TR, BR), 4-7 for edges
            (left, top, right, bottom)
        strip: The strip being cropped
        dx_res: Delta X since the last event, in strip image space
        dy_res: Delta Y since the last event, in strip image space
        crop_base: Last accepted (min_x, max_x, min_y, max_y)
        strip_width: Original strip width in pixels
        strip_height: Original strip height in pixels
        flip_x: Whether strip is flipped on X axis
        flip_y: Whether strip is flipped on Y axis

    Returns:
        tuple: the accepted (min_x, max_x, min_y, max_y), as floats.
    """
    x_move, y_move = _HANDLE_FIELDS[map_handle(handle_index, flip_x, flip_y)]
    accepted = list(crop_base)

    for move, delta, extent in ((x_move, dx_res, strip_width),
                                (y_move, dy_res, strip_height)):
        if move is None:
            continue
        field, sign = move
        candidate = accepted[field] + sign * delta
        # Cannot crop past the edge it started from.
        if candidate < 0.0:
            candidate = 0.0

        # The largest value that still leaves a pixel between this crop and the
        # one coming from the other side. Negative when the opposite crop has
        # already eaten the whole strip on its own.
        limit = extent - accepted[_OPPOSITE_FIELD[field]] - 1.0

        if candidate <= limit:
            accepted[field] = candidate
        elif accepted[field] > limit:
            # Already past the limit - which the sidebar allows, since
            # StripCrop enforces nothing. Take the move only if it is an
            # improvement, so the handles can climb out of a state they could
            # not have reached by dragging. Never clamp to limit here: that
            # would snap the crop a long way on the first nudge.
            accepted[field] = min(candidate, accepted[field])
        else:
            # Inside the valid range and pushing out of it. Stop against the
            # limit rather than refusing the move, so the crop ends up where
            # the drag was actually heading.
            accepted[field] = limit

    strip.crop.min_x = int(accepted[0])
    strip.crop.max_x = int(accepted[1])
    strip.crop.min_y = int(accepted[2])
    strip.crop.max_y = int(accepted[3])

    return tuple(accepted)


# --- Strip geometry ---

def get_strip_geometry_with_flip_support(strip, scene):
    """Calculate strip geometry accounting for Mirror X/Y checkboxes.

    Returns corner positions in resolution space.

    WARNING: the strip must be croppable. Every strip type with a crop also has
    a transform, but a sound strip has neither, and guarding transform away
    rather than filtering the caller gives such a strip the whole render
    rectangle as its outline - a hit test that then matches every click in the
    preview. Filter with hasattr(strip, 'crop') before calling.
    """
    res_x = scene.render.resolution_x
    res_y = scene.render.resolution_y

    strip_width, strip_height = get_strip_dimensions(strip, scene)
    flip_x, flip_y = get_strip_flip_state(strip)
    angle = get_strip_rotation(strip)

    offset_x = strip.transform.offset_x
    offset_y = strip.transform.offset_y
    scale_x = strip.transform.scale_x
    scale_y = strip.transform.scale_y

    crop_left = float(strip.crop.min_x)
    crop_right = float(strip.crop.max_x)
    crop_bottom = float(strip.crop.min_y)
    crop_top = float(strip.crop.max_y)

    scaled_width = strip_width * scale_x
    scaled_height = strip_height * scale_y

    # A strip sits centered in the frame, then moves by its offset.
    left = (res_x - scaled_width) / 2 + offset_x
    right = (res_x + scaled_width) / 2 + offset_x
    bottom = (res_y - scaled_height) / 2 + offset_y
    top = (res_y + scaled_height) / 2 + offset_y

    # Crop is stored in original image pixels, so it scales with the strip.
    left += crop_left * scale_x
    right -= crop_right * scale_x
    bottom += crop_bottom * scale_y
    top -= crop_top * scale_y

    pivot_x = res_x / 2 + offset_x
    pivot_y = res_y / 2 + offset_y

    # Mirroring reflects the strip about the frame's center line, and takes the
    # rotation pivot with it.
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

    # BL, TL, TR, BR - the order every handle index in this module assumes.
    corners = [
        Vector((left, bottom)),  # Bottom-left
        Vector((left, top)),     # Top-left
        Vector((right, top)),    # Top-right
        Vector((right, bottom))  # Bottom-right
    ]

    if angle != 0:
        # Mirroring one axis reverses which way the strip turns.
        if flip_x != flip_y:
            angle = -angle

        center = Vector((pivot_x, pivot_y))
        corners = [rotate_point(c, angle, center) for c in corners]

    return corners, (pivot_x, pivot_y), (scale_x, scale_y, flip_x, flip_y)


# --- State management functions ---

def get_crop_state():
    """Whether a modal crop is running.

    The gizmo tool's poll() and its draw handler both stand down while one is,
    so this is read on every redraw - keep it cheap.
    """
    global _crop_active
    return {'active': _crop_active}


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
