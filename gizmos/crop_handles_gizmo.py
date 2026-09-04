"""
BL Easy Crop - Crop Handles Gizmo System

The primary crop interface: nine gizmos - four corners, four edge midpoints and
a center symbol that hands over to the modal operator. Handles stay on screen
for as long as the tool is selected.

Geometry and crop maths come from operators.crop_core, which the modal operator
also uses. Keeping one source is what stops the two interfaces disagreeing about
where a handle belongs on a flipped or rotated strip.
"""

import bpy
import math
import gpu
from bpy.types import Gizmo, GizmoGroup
from mathutils import Vector, Matrix

from ..operators.crop_core import (
    get_crop_state, is_strip_visible_at_frame,
    get_strip_geometry_with_flip_support, get_strip_flip_state,
    get_strip_rotation, get_strip_dimensions, get_edge_midpoints,
    res_to_screen, compute_crop_delta, apply_crop_changes, autokey_crop,
    HANDLE_RADIUS, SELECT_RADIUS
)
from ..operators.crop_drawing import draw_crop_symbol_at, draw_rotated_square


class EASYCROP_GT_crop_handle(Gizmo):
    """One crop handle: a corner, an edge midpoint, or the center symbol.

    The group sets handle_type and handle_index after creating each one; the
    pair maps to the 0-7 numbering crop_core uses, center excepted.
    """
    bl_idname = "EASYCROP_GT_crop_handle"
    bl_target_properties = ()

    def setup(self):
        """Setup the handle gizmo."""
        self.handle_type = "corner"  # or "edge" or "center"
        self.handle_index = 0

        # Keeps the handles drawn and taking events while a drag is running,
        # rather than only while the group is idle.
        self.use_draw_modal = True
        self.use_draw_select = True
        self.use_event_handle_all = True

        self.use_select_background = False
        # Hides the pointer and keeps mouse_region_x continuous past the region
        # edge, so a drag is not capped by the window. exit() puts it back.
        self.use_grab_cursor = True

        self.hide = False
        self.alpha = 0.8
        self.alpha_highlight = 1.0

        self.color = (1.0, 1.0, 1.0)
        self.color_highlight = (1.0, 0.5, 0.0)

        self.scale_basis = HANDLE_RADIUS
        self.select_id = 0

    def draw_prepare(self, context):
        """Prepare for drawing - ensure gizmo is visible."""
        self.hide = False
        self.alpha = 0.8 if not self.is_highlight else 1.0

    def draw(self, context):
        """Draw the handle gizmo."""
        self.hide = False
        center_pos = self.matrix_basis.translation

        if self.is_highlight:
            color = (*self.color_highlight, self.alpha_highlight)
        else:
            color = (1.0, 1.0, 1.0, 0.8)

        if self.handle_type == "center":
            draw_crop_symbol_at(center_pos.x, center_pos.y, color)
        else:
            rotation_angle = self.matrix_basis.to_3x3().to_euler().z
            draw_rotated_square(center_pos.x, center_pos.y, HANDLE_RADIUS,
                                rotation_angle, color)

    def draw_select(self, context, select_id):
        """Draw during selection/modal operations - keeps handles visible."""
        self._draw_handle_common(context, during_modal=True)

    def _draw_handle_common(self, context, during_modal=False):
        """Common drawing logic for both normal and modal states."""
        center_pos = self.matrix_basis.translation

        if self.handle_type == "center":
            color = (1.0, 1.0, 1.0, 0.6 if during_modal else 0.8)
            draw_crop_symbol_at(center_pos.x, center_pos.y, color)
        else:
            if self.is_highlight or during_modal:
                color = (1.0, 0.5, 0.0, 1.0)
            else:
                color = (1.0, 1.0, 1.0, 0.7)

            rotation_angle = self.matrix_basis.to_3x3().to_euler().z
            draw_rotated_square(center_pos.x, center_pos.y, HANDLE_RADIUS,
                                rotation_angle, color)

    def test_select(self, context, event):
        """Test if point is over this gizmo.

        WARNING: event is an (x, y) tuple here, not an Event. Blender passes
        region coordinates to a gizmo's test_select.
        """
        gizmo_pos = self.matrix_basis.translation
        mouse_pos = event

        distance = ((gizmo_pos.x - mouse_pos[0])**2 + (gizmo_pos.y - mouse_pos[1])**2)**0.5

        if distance <= SELECT_RADIUS:
            return self.select_id
        else:
            return -1

    def select(self, context, event):
        """Handle gizmo selection/click."""
        return True

    def invoke(self, context, event):
        """Start handle dragging."""
        if self.handle_type == "center":
            try:
                bpy.ops.sequencer.crop('INVOKE_DEFAULT')
                return {'FINISHED'}
            except RuntimeError:
                # Blender raises when the operator's poll() fails, which a click
                # on the center symbol can legitimately hit.
                return {'CANCELLED'}
        else:
            # The cursor position the next delta is measured from. The drag
            # moves the crop by how far the cursor traveled since the last
            # event, not by where it now points - see _update_crop_from_gizmo_drag.
            self.last_mouse_pos = (event.mouse_region_x, event.mouse_region_y)

            EASYCROP_GGT_crop_handles._drag_active = True

            # Disable transform gizmos during crop drag. Never swallow a failure
            # here: exit() undoes this, and a save that silently did not happen
            # leaves the user's gizmos switched off for the rest of the session.
            self._saved_gizmo_state = context.space_data.show_gizmo
            context.space_data.show_gizmo = False

            # Blender stops drawing the group once a drag owns the input, so
            # the handles are drawn by hand for the duration.
            self._modal_draw_handler = bpy.types.SpaceSequenceEditor.draw_handler_add(
                self._draw_handles_during_modal, (), 'PREVIEW', 'POST_PIXEL')

            # Store initial crop values for this drag operation
            strip = context.scene.sequence_editor.active_strip
            if strip and hasattr(strip, 'crop') and strip.crop:
                self.crop_start = (float(strip.crop.min_x), float(strip.crop.max_x),
                                   float(strip.crop.min_y), float(strip.crop.max_y))
            else:
                self.crop_start = (0.0, 0.0, 0.0, 0.0)
            # The crop this drag has accepted so far. Each event accumulates
            # onto this rather than onto crop_start, so a crop held against a
            # limit moves again the moment the cursor heads back off it.
            self.crop_current = self.crop_start

            return {'RUNNING_MODAL'}

    def modal(self, context, event, tweak):
        """Handle dragging modal operation."""
        if self.handle_type == "center":
            return {'FINISHED'}

        # Movement since the previous event, not since the drag began.
        # event.mouse_region_x stays continuous under use_grab_cursor, so
        # differencing consecutive events is safe.
        if hasattr(self, 'last_mouse_pos'):
            current_mouse = (event.mouse_region_x, event.mouse_region_y)
            delta = (current_mouse[0] - self.last_mouse_pos[0],
                     current_mouse[1] - self.last_mouse_pos[1])
            self.last_mouse_pos = current_mouse
        else:
            delta = (0, 0)

        # WARNING: do not wrap this in a blanket except. last_mouse_pos has
        # already advanced, so a swallowed failure consumes the event's delta
        # and the drag carries on with the crop no longer tracking the cursor,
        # stranding the user with nothing on screen to explain it.
        strip = context.scene.sequence_editor.active_strip
        if strip and hasattr(strip, 'crop'):
            self._update_crop_from_gizmo_drag(context, delta, strip)

            for area in context.screen.areas:
                if area.type == 'SEQUENCE_EDITOR':
                    area.tag_redraw()

        return {'RUNNING_MODAL'}

    def _draw_handles_during_modal(self):
        """Custom drawing function to keep handles visible during modal."""
        context = bpy.context
        scene = context.scene
        if not scene.sequence_editor or not scene.sequence_editor.active_strip:
            return

        active_strip = scene.sequence_editor.active_strip
        if not hasattr(active_strip, 'crop'):
            return

        self._draw_handles_with_gpu(context, active_strip, scene)

    def _draw_handles_with_gpu(self, context, strip, scene):
        """Draw handles directly with GPU during modal operations."""
        region = context.region
        if not region or not region.view2d:
            return

        corners, (pivot_x, pivot_y), (scale_x, scale_y, flip_x, flip_y) = \
            get_strip_geometry_with_flip_support(strip, scene)
        edge_midpoints = get_edge_midpoints(corners)

        view2d = region.view2d
        res_x = scene.render.resolution_x
        res_y = scene.render.resolution_y

        # Restore whatever the caller had. A draw handler that leaves blending
        # switched on changes how everything drawn after it in the region looks.
        prev_blend = gpu.state.blend_get()
        gpu.state.blend_set('ALPHA')

        # Get rotation with flip compensation for handle drawing
        angle = get_strip_rotation(strip)
        if flip_x != flip_y:
            angle = -angle

        # Draw corner handles
        for i, corner in enumerate(corners):
            screen_co = res_to_screen(corner.x, corner.y, res_x, res_y, view2d)
            if self.handle_type == "corner" and self.handle_index == i:
                color = (1.0, 0.5, 0.0, 1.0)
            else:
                color = (1.0, 1.0, 1.0, 0.8)
            draw_rotated_square(screen_co[0], screen_co[1], HANDLE_RADIUS, angle, color)

        # Draw edge handles
        for i, midpoint in enumerate(edge_midpoints):
            screen_co = res_to_screen(midpoint.x, midpoint.y, res_x, res_y, view2d)
            if self.handle_type == "edge" and self.handle_index == i:
                color = (1.0, 0.5, 0.0, 1.0)
            else:
                color = (1.0, 1.0, 1.0, 0.8)
            draw_rotated_square(screen_co[0], screen_co[1], HANDLE_RADIUS, angle, color)

        # Draw center handle
        center_screen = res_to_screen(pivot_x, pivot_y, res_x, res_y, view2d)
        draw_crop_symbol_at(center_screen[0], center_screen[1],
                            (1.0, 1.0, 1.0, 0.8))

        gpu.state.blend_set(prev_blend)

    def _commit(self, context):
        """Auto-key and push undo for a drag that changed something.

        WARNING: call this from exit(), never from a LEFTMOUSE/RELEASE branch
        in modal(). Blender's gizmo tweak operator matches the confirming
        release against its own modal keymap and finishes the modal itself, so
        modal() is not reliably given the release. The drag still works
        perfectly and only the commit goes missing, so the mistake is invisible
        until someone tries to undo.

        Gizmos get no undo step of their own - unlike the modal operator, which
        has bl_options {'REGISTER', 'UNDO'} - so without the push here a crop
        dragged with the tool cannot be undone at all.
        """
        strip = context.scene.sequence_editor.active_strip
        if not strip or not hasattr(strip, 'crop') or not strip.crop:
            return

        # A bare click on a handle changes nothing; keying and pushing undo for
        # it would leave a stray keyframe and a no-op undo step.
        started_at = tuple(int(v) for v in self.crop_start)
        ended_at = (strip.crop.min_x, strip.crop.max_x,
                    strip.crop.min_y, strip.crop.max_y)
        if ended_at == started_at:
            return

        handle_index = (self.handle_index if self.handle_type == "corner"
                        else self.handle_index + 4)
        flip_x, flip_y = get_strip_flip_state(strip)
        # Keys first, so they land inside the undo step the push opens.
        autokey_crop(context, strip, handle_index, flip_x, flip_y)
        bpy.ops.ed.undo_push(message="Crop")

    def _warp_cursor_to_handle(self, context):
        """Put the cursor back on the handle the drag finished on.

        use_grab_cursor returns the pointer to where the drag started, which
        after a constrained drag need not be where the handle ended up. The warp
        is deferred on a short timer because Blender restores the cursor after
        exit() returns, so warping inline is overwritten.

        WARNING: cursor_modal_set('NONE') hides the pointer and only the timer
        callback restores it. Nothing may be added between those two calls, and
        neither may be wrapped in a handler that could swallow a failure of the
        other - the cursor would stay invisible for the rest of the session.
        """
        strip = context.scene.sequence_editor.active_strip
        region = context.region
        if not strip or not hasattr(strip, 'crop') or not region or not region.view2d:
            return

        corners, _, _ = get_strip_geometry_with_flip_support(strip, context.scene)
        if self.handle_type == "corner":
            final_handle_pos = corners[self.handle_index]
        else:
            next_i = (self.handle_index + 1) % 4
            final_handle_pos = (corners[self.handle_index] + corners[next_i]) / 2

        screen_co = res_to_screen(
            final_handle_pos.x, final_handle_pos.y,
            context.scene.render.resolution_x,
            context.scene.render.resolution_y, region.view2d)

        # Convert region coords to window coords for cursor_warp
        final_x = region.x + int(screen_co[0])
        final_y = region.y + int(screen_co[1])

        def deferred_cursor_warp():
            try:
                bpy.context.window.cursor_warp(final_x, final_y)
                bpy.context.window.cursor_modal_restore()
            except Exception:
                # A timer callback fires after the gizmo is gone, against a
                # context nobody can act on. Failing to move the cursor is
                # cosmetic; raising here only spams the console.
                pass
            return None  # Don't repeat the timer

        bpy.context.window.cursor_modal_set('NONE')
        bpy.app.timers.register(deferred_cursor_warp, first_interval=0.05)

    def exit(self, context, cancel):
        """End a drag: commit it or undo it, then put back what invoke() changed.

        WARNING: this is where the end of a drag has to be handled. Blender's
        gizmo tweak operator finishes the modal itself on the confirming
        release, so modal() cannot be relied on to see it - see _commit.
        """
        if self.handle_type == "center":
            return

        EASYCROP_GGT_crop_handles._drag_active = False

        if not cancel:
            self._commit(context)
            self._warp_cursor_to_handle(context)

        if getattr(self, '_modal_draw_handler', None):
            bpy.types.SpaceSequenceEditor.draw_handler_remove(
                self._modal_draw_handler, 'PREVIEW')
            self._modal_draw_handler = None

        # Never swallow a failure here - the user is left with their transform
        # gizmos switched off and no way to guess why.
        if hasattr(self, '_saved_gizmo_state'):
            context.space_data.show_gizmo = self._saved_gizmo_state

        if cancel and hasattr(self, 'crop_start'):
            strip = context.scene.sequence_editor.active_strip
            if strip and hasattr(strip, 'crop') and strip.crop:
                strip.crop.min_x = int(self.crop_start[0])
                strip.crop.max_x = int(self.crop_start[1])
                strip.crop.min_y = int(self.crop_start[2])
                strip.crop.max_y = int(self.crop_start[3])

                for area in context.screen.areas:
                    if area.type == 'SEQUENCE_EDITOR':
                        area.tag_redraw()

    def _update_crop_from_gizmo_drag(self, context, delta, strip):
        """Update crop values from gizmo drag."""
        region = context.region
        if not region or not region.view2d:
            return

        dx_res, dy_res, flip_x, flip_y = compute_crop_delta(
            delta[0], delta[1], region.view2d, strip)
        strip_width, strip_height = get_strip_dimensions(strip, context.scene)

        # Convert gizmo handle type/index to unified handle index (0-7)
        handle_index = self.handle_index if self.handle_type == "corner" else self.handle_index + 4

        self.crop_current = apply_crop_changes(
            handle_index, strip, dx_res, dy_res,
            self.crop_current, strip_width, strip_height, flip_x, flip_y)


class EASYCROP_GGT_crop_handles(GizmoGroup):
    """The nine handles: four corners, four edge midpoints, one center symbol.

    Linked from the toolbar tool's bl_widget, and poll() gates on that tool
    being the active one.
    """
    bl_idname = "EASYCROP_GGT_crop_handles"
    bl_label = "Crop Handles"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'PREVIEW'
    bl_options = {'SHOW_MODAL_ALL', 'SCALE'}

    # Set for the duration of a drag. refresh() runs on every redraw and would
    # otherwise pull the dragged handle back to where the crop says it belongs,
    # fighting the drag that is still moving it.
    _drag_active = False

    @classmethod
    def poll(cls, context):
        """Check if gizmo group should be active."""
        if not context.space_data or context.space_data.type != 'SEQUENCE_EDITOR':
            return False

        if context.space_data.display_mode != 'IMAGE':
            return False

        if not context.scene.sequence_editor:
            return False

        active_strip = context.scene.sequence_editor.active_strip
        if not active_strip or not hasattr(active_strip, 'crop'):
            return False

        if not active_strip.select:
            return False

        current_frame = context.scene.frame_current
        if not is_strip_visible_at_frame(active_strip, current_frame):
            return False

        # Don't show if modal crop mode is already active
        crop_state = get_crop_state()
        if crop_state['active']:
            return False

        # Check if crop handles tool is active. A swallowed failure here would
        # hide the whole tool - handles that never appear, from a toolbar button
        # that looks like it worked - so this deliberately has no catch.
        workspace = getattr(bpy.context, 'workspace', None)
        if workspace is not None:
            for tool in workspace.tools:
                if tool.idname == "sequencer.crop_handles_tool":
                    return True

        return False

    def setup(self, context):
        """Create the nine handles.

        WARNING: creation order is load-bearing. refresh() addresses them as
        self.gizmos[0..3] corners, [4..7] edges, [8] center, so nothing may be
        inserted or reordered here without changing it there too.

        The four use_* flags repeat what EASYCROP_GT_crop_handle.setup() already
        set on each gizmo. Which of the two Blender consults has not been
        established, so both are left in place.
        """
        for i in range(4):
            gizmo = self.gizmos.new(EASYCROP_GT_crop_handle.bl_idname)
            gizmo.handle_type = "corner"
            gizmo.handle_index = i
            gizmo.select_id = i

            gizmo.use_event_handle_all = True
            gizmo.use_draw_modal = True
            gizmo.use_grab_cursor = True
            gizmo.use_draw_select = True

        for i in range(4):
            gizmo = self.gizmos.new(EASYCROP_GT_crop_handle.bl_idname)
            gizmo.handle_type = "edge"
            gizmo.handle_index = i
            gizmo.select_id = i + 4

            gizmo.use_event_handle_all = True
            gizmo.use_draw_modal = True
            gizmo.use_grab_cursor = True
            gizmo.use_draw_select = True

        gizmo = self.gizmos.new(EASYCROP_GT_crop_handle.bl_idname)
        gizmo.handle_type = "center"
        gizmo.handle_index = 0
        gizmo.select_id = 8

        gizmo.use_event_handle_all = True
        gizmo.use_draw_select = True

    def refresh(self, context):
        """Put each handle where the strip's current crop says it belongs."""
        if self._drag_active:
            return

        scene = context.scene
        if not scene.sequence_editor or not scene.sequence_editor.active_strip:
            return

        active_strip = scene.sequence_editor.active_strip
        if not hasattr(active_strip, 'crop'):
            return

        region = context.region
        if not region or not region.view2d:
            return

        # WARNING: no blanket except around this. A swallowed failure leaves
        # every handle on the matrix_basis it was last given - positions that
        # still look right, on a strip whose geometry has moved - and dragging
        # one then edits a crop field that no longer matches where it is drawn.
        corners, (pivot_x, pivot_y), (scale_x, scale_y, flip_x, flip_y) = \
            get_strip_geometry_with_flip_support(active_strip, scene)
        edge_midpoints = get_edge_midpoints(corners)

        res_x = scene.render.resolution_x
        res_y = scene.render.resolution_y
        view2d = region.view2d

        # Convert corners to screen coordinates for rotation calculation
        screen_corners = [
            Vector(res_to_screen(c.x, c.y, res_x, res_y, view2d))
            for c in corners
        ]

        # Get raw rotation angle once for both loops
        raw_angle = get_strip_rotation(active_strip)

        # Position corner handles (0-3)
        for i in range(4):
            screen_co = screen_corners[i]
            rotation_angle = 0

            if abs(raw_angle) > 0.01:
                next_corner1 = i
                next_corner2 = (i + 1) % 4
                next_edge_vec = screen_corners[next_corner2] - screen_corners[next_corner1]
                next_edge_angle = math.atan2(next_edge_vec.y, next_edge_vec.x)
                rotation_angle = next_edge_angle - math.pi / 2

            transform_matrix = Matrix.Translation((screen_co[0], screen_co[1], 0))
            if abs(rotation_angle) > 0.01:
                rotation_matrix = Matrix.Rotation(rotation_angle, 4, 'Z')
                transform_matrix = transform_matrix @ rotation_matrix

            self.gizmos[i].matrix_basis = transform_matrix
            self.gizmos[i].hide = False
            self.gizmos[i].alpha = 0.8

        # Position edge handles (4-7)
        for i in range(4):
            midpoint = edge_midpoints[i]
            screen_co = res_to_screen(midpoint.x, midpoint.y, res_x, res_y, view2d)
            rotation_angle = 0

            if abs(raw_angle) > 0.01:
                corner1_idx = i
                corner2_idx = (i + 1) % 4
                edge_vec = screen_corners[corner2_idx] - screen_corners[corner1_idx]
                edge_angle = math.atan2(edge_vec.y, edge_vec.x)
                rotation_angle = edge_angle - math.pi / 2

            transform_matrix = Matrix.Translation((screen_co[0], screen_co[1], 0))
            if abs(rotation_angle) > 0.01:
                rotation_matrix = Matrix.Rotation(rotation_angle, 4, 'Z')
                transform_matrix = transform_matrix @ rotation_matrix

            self.gizmos[i + 4].matrix_basis = transform_matrix
            self.gizmos[i + 4].hide = False
            self.gizmos[i + 4].alpha = 0.8

        # Position center handle (8)
        screen_co = res_to_screen(pivot_x, pivot_y, res_x, res_y, view2d)
        self.gizmos[8].matrix_basis = Matrix.Translation((screen_co[0], screen_co[1], 0))
        self.gizmos[8].hide = False
        self.gizmos[8].alpha = 0.8

    def draw_prepare(self, context):
        """Prepare for drawing."""
        self.refresh(context)

    def draw_select(self, context):
        """Draw during modal operations - ensure handles stay visible."""
        scene = context.scene
        if not scene.sequence_editor or not scene.sequence_editor.active_strip:
            return

        active_strip = scene.sequence_editor.active_strip
        if not hasattr(active_strip, 'crop'):
            return

        for gizmo in self.gizmos:
            gizmo._draw_handle_common(context, during_modal=True)


def register_crop_handles_gizmo():
    """Register the crop handles gizmo classes."""
    bpy.utils.register_class(EASYCROP_GT_crop_handle)
    bpy.utils.register_class(EASYCROP_GGT_crop_handles)

    # The group is also linked by the tool's bl_widget, and its poll() gates on
    # the tool being active, so this is belt and braces rather than what makes
    # the handles appear. There is no window manager in background mode.
    wm = getattr(bpy.context, "window_manager", None)
    if wm is not None:
        wm.gizmo_group_type_ensure(EASYCROP_GGT_crop_handles.bl_idname)


def unregister_crop_handles_gizmo():
    """Unregister the crop handles gizmo classes."""
    bpy.utils.unregister_class(EASYCROP_GGT_crop_handles)
    bpy.utils.unregister_class(EASYCROP_GT_crop_handle)
