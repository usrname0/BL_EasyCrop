"""
BL Easy Crop - Crop Handles Gizmo System

A complete gizmo-based cropping system with individual handles for corners and edges.
Based on the modal operator but using gizmos for better integration.
"""

import bpy
import math
import gpu
from gpu_extras.batch import batch_for_shader
from bpy.types import Gizmo, GizmoGroup
from mathutils import Vector, Matrix

from ..operators.crop_core import (
    get_crop_state, is_strip_visible_at_frame,
    get_strip_geometry_with_flip_support, get_strip_flip_state,
    get_strip_rotation, get_strip_dimensions, get_edge_midpoints,
    res_to_screen, compute_crop_delta, apply_crop_changes
)
from ..operators.crop_drawing import draw_crop_symbol_at, draw_rotated_square


class EASYCROP_GT_crop_handle(Gizmo):
    """Individual crop handle gizmo."""
    bl_idname = "EASYCROP_GT_crop_handle"
    bl_target_properties = ()

    def setup(self):
        """Setup the handle gizmo."""
        self.handle_type = "corner"  # or "edge" or "center"
        self.handle_index = 0

        # Essential properties for always-visible gizmos
        self.use_draw_modal = True
        self.use_draw_select = True
        self.use_event_handle_all = True

        self.use_select_background = False
        self.use_grab_cursor = True

        self.hide = False
        self.alpha = 0.8
        self.alpha_highlight = 1.0

        self.color = (1.0, 1.0, 1.0)
        self.color_highlight = (1.0, 0.5, 0.0)

        self.scale_basis = 6.0
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

        try:
            if self.handle_type == "center":
                draw_crop_symbol_at(center_pos.x, center_pos.y, color)
            else:
                rotation_angle = self.matrix_basis.to_3x3().to_euler().z
                draw_rotated_square(center_pos.x, center_pos.y, 6,
                                    rotation_angle, color)
        except Exception:
            pass

    def draw_select(self, context, select_id):
        """Draw during selection/modal operations - keeps handles visible."""
        self._draw_handle_common(context, during_modal=True)

    def _draw_handle_common(self, context, during_modal=False):
        """Common drawing logic for both normal and modal states."""
        center_pos = self.matrix_basis.translation

        if self.handle_type == "center":
            color = (1.0, 1.0, 1.0, 0.6 if during_modal else 0.8)
            try:
                draw_crop_symbol_at(center_pos.x, center_pos.y, color)
            except Exception:
                pass
        else:
            if self.is_highlight or during_modal:
                color = (1.0, 0.5, 0.0, 1.0)
            else:
                color = (1.0, 1.0, 1.0, 0.7)

            try:
                rotation_angle = self.matrix_basis.to_3x3().to_euler().z
                draw_rotated_square(center_pos.x, center_pos.y, 6,
                                    rotation_angle, color)
            except Exception:
                pass

    def test_select(self, context, event):
        """Test if point is over this gizmo."""
        gizmo_pos = self.matrix_basis.translation
        mouse_pos = event  # event is (x, y) tuple

        distance = ((gizmo_pos.x - mouse_pos[0])**2 + (gizmo_pos.y - mouse_pos[1])**2)**0.5
        threshold = 25

        if distance <= threshold:
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
            except Exception:
                return {'CANCELLED'}
        else:
            # Store initial mouse position for delta calculation
            self.init_mouse_pos = (event.mouse_region_x, event.mouse_region_y)

            # Mark drag as active to prevent gizmo repositioning
            EASYCROP_GGT_crop_handles._drag_active = True

            # Disable transform gizmos during crop drag
            try:
                if hasattr(context.space_data, 'show_gizmo'):
                    self._saved_gizmo_state = context.space_data.show_gizmo
                    context.space_data.show_gizmo = False
            except Exception:
                pass

            # Enable modal drawing handler to keep handles visible during drag
            try:
                self._modal_draw_handler = bpy.types.SpaceSequenceEditor.draw_handler_add(
                    self._draw_handles_during_modal, (), 'PREVIEW', 'POST_PIXEL')
            except Exception:
                pass

            # Store initial crop values for this drag operation
            strip = context.scene.sequence_editor.active_strip
            if strip and hasattr(strip, 'crop') and strip.crop:
                self.crop_start = (strip.crop.min_x, strip.crop.max_x,
                                   strip.crop.min_y, strip.crop.max_y)
            else:
                self.crop_start = (0, 0, 0, 0)

            return {'RUNNING_MODAL'}

    def modal(self, context, event, tweak):
        """Handle dragging modal operation."""
        if self.handle_type == "center":
            return {'FINISHED'}

        # Calculate delta from initial position
        if hasattr(self, 'init_mouse_pos'):
            current_mouse = (event.mouse_region_x, event.mouse_region_y)
            delta = (current_mouse[0] - self.init_mouse_pos[0],
                     current_mouse[1] - self.init_mouse_pos[1])
        else:
            delta = (0, 0)

        try:
            strip = context.scene.sequence_editor.active_strip
            if strip and hasattr(strip, 'crop'):
                self._update_crop_from_gizmo_drag(context, delta, strip)

                for area in context.screen.areas:
                    if area.type == 'SEQUENCE_EDITOR':
                        area.tag_redraw()
        except Exception:
            pass

        return {'RUNNING_MODAL'}

    def _draw_handles_during_modal(self):
        """Custom drawing function to keep handles visible during modal."""
        try:
            context = bpy.context
            scene = context.scene
            if not scene.sequence_editor or not scene.sequence_editor.active_strip:
                return

            active_strip = scene.sequence_editor.active_strip
            if not hasattr(active_strip, 'crop'):
                return

            self._draw_handles_with_gpu(context, active_strip, scene)
        except Exception:
            pass

    def _draw_handles_with_gpu(self, context, strip, scene):
        """Draw handles directly with GPU during modal operations."""
        try:
            corners, (pivot_x, pivot_y), (scale_x, scale_y, flip_x, flip_y) = \
                get_strip_geometry_with_flip_support(strip, scene)
            edge_midpoints = get_edge_midpoints(corners)

            region = context.region
            if not region or not region.view2d:
                return

            view2d = region.view2d
            res_x = scene.render.resolution_x
            res_y = scene.render.resolution_y

            gpu.state.blend_set('ALPHA')

            # Get rotation with flip compensation for handle drawing
            angle = get_strip_rotation(strip)
            if flip_x != flip_y:
                angle = -angle

            # Draw corner handles
            for i, corner in enumerate(corners):
                screen_co = res_to_screen(corner.x, corner.y, res_x, res_y, view2d)
                if screen_co:
                    if self.handle_type == "corner" and self.handle_index == i:
                        color = (1.0, 0.5, 0.0, 1.0)
                    else:
                        color = (1.0, 1.0, 1.0, 0.8)
                    draw_rotated_square(screen_co[0], screen_co[1], 6, angle, color)

            # Draw edge handles
            for i, midpoint in enumerate(edge_midpoints):
                screen_co = res_to_screen(midpoint.x, midpoint.y, res_x, res_y, view2d)
                if screen_co:
                    if self.handle_type == "edge" and self.handle_index == i:
                        color = (1.0, 0.5, 0.0, 1.0)
                    else:
                        color = (1.0, 1.0, 1.0, 0.8)
                    draw_rotated_square(screen_co[0], screen_co[1], 6, angle, color)

            # Draw center handle
            center_screen = res_to_screen(pivot_x, pivot_y, res_x, res_y, view2d)
            if center_screen:
                draw_crop_symbol_at(center_screen[0], center_screen[1],
                                    (1.0, 1.0, 1.0, 0.8))

        except Exception:
            pass

    def exit(self, context, cancel):
        """Handle gizmo exit."""
        if self.handle_type != "center":

            # Clear drag state to allow gizmo repositioning again
            EASYCROP_GGT_crop_handles._drag_active = False

            # Deferred cursor warp to final handle position (unless cancelled)
            if not cancel:
                try:
                    strip = context.scene.sequence_editor.active_strip
                    if strip and hasattr(strip, 'crop'):
                        corners, (pivot_x, pivot_y), _ = \
                            get_strip_geometry_with_flip_support(strip, context.scene)

                        final_handle_pos = None

                        if self.handle_type == "corner" and self.handle_index < len(corners):
                            final_handle_pos = corners[self.handle_index]
                        elif self.handle_type == "edge" and self.handle_index < 4:
                            next_i = (self.handle_index + 1) % 4
                            final_handle_pos = (corners[self.handle_index] + corners[next_i]) / 2

                        if final_handle_pos:
                            region = context.region
                            if region and region.view2d:
                                res_x = context.scene.render.resolution_x
                                res_y = context.scene.render.resolution_y

                                screen_co = res_to_screen(
                                    final_handle_pos.x, final_handle_pos.y,
                                    res_x, res_y, region.view2d)

                                # Convert region coords to window coords for cursor_warp
                                final_x = region.x + int(screen_co[0])
                                final_y = region.y + int(screen_co[1])

                                def deferred_cursor_warp():
                                    try:
                                        bpy.context.window.cursor_warp(final_x, final_y)
                                        bpy.context.window.cursor_modal_restore()
                                    except Exception:
                                        pass
                                    return None  # Don't repeat the timer

                                # Hide cursor during restoration, then warp and restore
                                bpy.context.window.cursor_modal_set('NONE')
                                bpy.app.timers.register(deferred_cursor_warp, first_interval=0.05)

                except Exception:
                    pass

            # Remove modal drawing handler
            try:
                if hasattr(self, '_modal_draw_handler') and self._modal_draw_handler:
                    bpy.types.SpaceSequenceEditor.draw_handler_remove(
                        self._modal_draw_handler, 'PREVIEW')
                    self._modal_draw_handler = None
            except Exception:
                pass

            # Restore transform gizmos
            try:
                if hasattr(self, '_saved_gizmo_state') and hasattr(context.space_data, 'show_gizmo'):
                    context.space_data.show_gizmo = self._saved_gizmo_state
            except Exception:
                pass

            # If cancelled, restore original crop values
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

        apply_crop_changes(handle_index, strip, dx_res, dy_res,
                           self.crop_start, strip_width, strip_height, flip_x, flip_y)


class EASYCROP_GGT_crop_handles(GizmoGroup):
    """Crop handles gizmo group - full handle system."""
    bl_idname = "EASYCROP_GGT_crop_handles"
    bl_label = "Crop Handles"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'PREVIEW'
    bl_options = {'SHOW_MODAL_ALL', 'SCALE'}

    # Class variable to track if any gizmo is being dragged
    _drag_active = False

    @classmethod
    def poll(cls, context):
        """Check if gizmo group should be active."""
        if not context.space_data or context.space_data.type != 'SEQUENCE_EDITOR':
            return False

        if hasattr(context.space_data, 'display_mode'):
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

        # Check if crop handles tool is active
        try:
            if hasattr(bpy.context, 'workspace') and bpy.context.workspace:
                workspace = bpy.context.workspace
                if hasattr(workspace, 'tools') and workspace.tools:
                    for tool in workspace.tools:
                        if hasattr(tool, 'idname') and tool.idname == "sequencer.crop_handles_tool":
                            return True
        except Exception:
            pass

        return False

    def setup(self, context):
        """Setup the gizmo group with all handles."""
        # Create corner handles (4)
        for i in range(4):
            gizmo = self.gizmos.new(EASYCROP_GT_crop_handle.bl_idname)
            gizmo.handle_type = "corner"
            gizmo.handle_index = i
            gizmo.select_id = i

            gizmo.use_event_handle_all = True
            gizmo.use_draw_modal = True
            gizmo.use_grab_cursor = True
            gizmo.use_draw_select = True

        # Create edge handles (4)
        for i in range(4):
            gizmo = self.gizmos.new(EASYCROP_GT_crop_handle.bl_idname)
            gizmo.handle_type = "edge"
            gizmo.handle_index = i
            gizmo.select_id = i + 4

            gizmo.use_event_handle_all = True
            gizmo.use_draw_modal = True
            gizmo.use_grab_cursor = True
            gizmo.use_draw_select = True

        # Create center handle (1)
        gizmo = self.gizmos.new(EASYCROP_GT_crop_handle.bl_idname)
        gizmo.handle_type = "center"
        gizmo.handle_index = 0
        gizmo.select_id = 8

        gizmo.use_event_handle_all = True
        gizmo.use_draw_select = True

    def refresh(self, context):
        """Refresh gizmo positions."""
        # Don't reposition gizmos during active drag
        if self._drag_active:
            return

        scene = context.scene
        if not scene.sequence_editor or not scene.sequence_editor.active_strip:
            return

        active_strip = scene.sequence_editor.active_strip
        if not hasattr(active_strip, 'crop'):
            return

        try:
            corners, (pivot_x, pivot_y), (scale_x, scale_y, flip_x, flip_y) = \
                get_strip_geometry_with_flip_support(active_strip, scene)
            edge_midpoints = get_edge_midpoints(corners)

            res_x = scene.render.resolution_x
            res_y = scene.render.resolution_y
            region = context.region

            if region and region.view2d:
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
                    if i < len(self.gizmos):
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
                    gizmo_idx = i + 4
                    if gizmo_idx < len(self.gizmos):
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

                        self.gizmos[gizmo_idx].matrix_basis = transform_matrix
                        self.gizmos[gizmo_idx].hide = False
                        self.gizmos[gizmo_idx].alpha = 0.8

                # Position center handle (8)
                if len(self.gizmos) > 8:
                    screen_co = res_to_screen(pivot_x, pivot_y, res_x, res_y, view2d)
                    self.gizmos[8].matrix_basis = Matrix.Translation((screen_co[0], screen_co[1], 0))
                    self.gizmos[8].hide = False
                    self.gizmos[8].alpha = 0.8

        except Exception:
            pass

    def draw_prepare(self, context):
        """Prepare for drawing."""
        self.refresh(context)

    def draw_select(self, context):
        """Draw during modal operations - ensure handles stay visible."""
        try:
            scene = context.scene
            if scene.sequence_editor and scene.sequence_editor.active_strip:
                active_strip = scene.sequence_editor.active_strip
                if hasattr(active_strip, 'crop'):
                    for gizmo in self.gizmos:
                        if hasattr(gizmo, '_draw_handle_common'):
                            gizmo._draw_handle_common(context, during_modal=True)
        except Exception:
            pass


def register_crop_handles_gizmo():
    """Register the crop handles gizmo classes."""
    try:
        bpy.utils.register_class(EASYCROP_GT_crop_handle)
        bpy.utils.register_class(EASYCROP_GGT_crop_handles)

        try:
            wm = bpy.context.window_manager
            if hasattr(wm, 'gizmo_group_type_ensure'):
                wm.gizmo_group_type_ensure(EASYCROP_GGT_crop_handles.bl_idname)
        except Exception:
            pass  # Expected for PERSISTENT gizmo groups

        return True

    except Exception:
        return False


def unregister_crop_handles_gizmo():
    """Unregister the crop handles gizmo classes."""
    try:
        bpy.utils.unregister_class(EASYCROP_GGT_crop_handles)
        bpy.utils.unregister_class(EASYCROP_GT_crop_handle)
    except Exception:
        pass
