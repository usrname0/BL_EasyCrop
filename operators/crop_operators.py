"""
BL Easy Crop - Operators

The secondary crop interface: a modal operator on Shift+C and in the Strip >
Transform menu, which draws handles for the duration of the operation and then
gets out of the way. The gizmo tool's center symbol hands over to it.

Unlike the gizmo, this carries bl_options {'REGISTER', 'UNDO'}, so Blender
pushes the undo step and only the auto-keying is done by hand.
"""

import bpy
from mathutils import Vector

from .crop_core import (
    get_crop_state, set_crop_active, get_draw_data, set_draw_data,
    get_draw_handle, set_draw_handle, clear_crop_state,
    get_strip_geometry_with_flip_support, is_strip_visible_at_frame, point_in_polygon,
    get_strips, get_selected_strips,
    get_strip_dimensions, get_edge_midpoints, get_strip_flip_state,
    res_to_screen, compute_crop_delta, apply_crop_changes, autokey_crop,
    SELECT_RADIUS
)
from .crop_drawing import draw_crop_handles


def get_preview_keymap_name():
    """Get the correct preview keymap name for the current Blender version."""
    return "Preview" if bpy.app.version >= (4, 5, 0) else "SequencerPreview"


def get_sequencer_keymap_name():
    """Get the correct sequencer keymap name for the current Blender version."""
    return "Video Sequence Editor" if bpy.app.version >= (4, 5, 0) else "Sequencer"


class EASYCROP_OT_crop(bpy.types.Operator):
    """Crop strips in the preview window"""
    bl_idname = "sequencer.crop"
    bl_label = "Crop"
    bl_description = "Crop a strip in the Image Preview"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        scene = context.scene
        if not scene.sequence_editor:
            return False

        space = context.space_data
        if space and space.type == 'SEQUENCE_EDITOR':
            if space.view_type not in {'PREVIEW', 'SEQUENCER_PREVIEW'}:
                return False

        if scene.sequence_editor.active_strip and hasattr(scene.sequence_editor.active_strip, 'crop'):
            return True

        for strip in get_selected_strips(context):
            if hasattr(strip, 'crop'):
                return True

        return False

    def invoke(self, context, event):
        crop_state = get_crop_state()

        if crop_state['active']:
            self.report({'WARNING'}, "Crop mode already active")
            return {'CANCELLED'}

        strip = context.scene.sequence_editor.active_strip
        current_frame = context.scene.frame_current

        has_suitable_active = (strip and
                              hasattr(strip, 'crop') and
                              is_strip_visible_at_frame(strip, current_frame))

        if not has_suitable_active:
            # Try to find a strip under the mouse
            mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))
            strips = self._get_visible_strips(context)

            clicked_strip = None
            for s in strips:
                if self._is_mouse_over_strip(context, s, mouse_pos):
                    clicked_strip = s
                    break

            if clicked_strip:
                if not event.shift:
                    bpy.ops.sequencer.select_all(action='DESELECT')
                clicked_strip.select = True
                context.scene.sequence_editor.active_strip = clicked_strip
                strip = clicked_strip
                has_suitable_active = True
            else:
                self.report({'INFO'}, "No croppable strip found - select an image/movie strip")
                return {'CANCELLED'}

        if not has_suitable_active:
            self.report({'INFO'}, "No suitable strip for cropping")
            return {'CANCELLED'}

        # Initialize operator state
        self.active_corner = -1
        # The cursor the next delta is measured from, and the crop this drag
        # has accepted so far. crop_start is kept separate because ESC restores
        # to it - see _update_crop for why the drag cannot accumulate onto it.
        self.mouse_last = (0.0, 0.0)
        self.crop_start = (0.0, 0.0, 0.0, 0.0)
        self.crop_current = (0.0, 0.0, 0.0, 0.0)
        self.timer = None

        # Store the current transform overlay state
        self.prev_show_gizmo = None
        if context.space_data:
            self.prev_show_gizmo = context.space_data.show_gizmo
            context.space_data.show_gizmo = False

        # Clean up any existing handler. ValueError means it was already
        # removed by whichever path tore the last crop session down.
        if get_draw_handle() is not None:
            try:
                bpy.types.SpaceSequenceEditor.draw_handler_remove(get_draw_handle(), 'PREVIEW')
            except ValueError:
                pass
            set_draw_handle(None)

        set_crop_active(True)
        set_draw_data({'active_corner': -1})

        # Store initial crop values
        if strip and hasattr(strip, 'crop') and strip.crop:
            crop_data = strip.crop
            self.crop_start = (float(crop_data.min_x), float(crop_data.max_x),
                               float(crop_data.min_y), float(crop_data.max_y))
        else:
            self.crop_start = (0.0, 0.0, 0.0, 0.0)
        self.crop_current = self.crop_start

        # Set up drawing handler
        handler = bpy.types.SpaceSequenceEditor.draw_handler_add(
            draw_crop_handles, (), 'PREVIEW', 'POST_PIXEL')
        set_draw_handle(handler)

        context.area.tag_redraw()

        wm = context.window_manager
        self.timer = wm.event_timer_add(0.01, window=context.window)
        wm.modal_handler_add(self)

        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        draw_data = get_draw_data()

        if hasattr(event, 'mouse_region_x') and hasattr(event, 'mouse_region_y'):
            draw_data['mouse_x'] = event.mouse_region_x
            draw_data['mouse_y'] = event.mouse_region_y
            set_draw_data(draw_data)

        if event.type == 'TIMER':
            for area in context.screen.areas:
                if area.type == 'SEQUENCE_EDITOR':
                    area.tag_redraw()
            return {'RUNNING_MODAL'}

        strip = context.scene.sequence_editor.active_strip
        if not strip:
            return self.finish(context)

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            corner = self._get_corner_at_mouse(context, event)

            if corner >= 0:
                self.active_corner = corner
                draw_data['active_corner'] = corner
                set_draw_data(draw_data)
                self.mouse_last = (event.mouse_region_x, event.mouse_region_y)

                if strip and hasattr(strip, 'crop') and strip.crop:
                    crop_data = strip.crop
                    self.crop_start = (float(crop_data.min_x), float(crop_data.max_x),
                                       float(crop_data.min_y), float(crop_data.max_y))
                else:
                    self.crop_start = (0.0, 0.0, 0.0, 0.0)
                self.crop_current = self.crop_start
            else:
                mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))
                strips = self._get_visible_strips(context)
                clicked_strip = None

                for s in strips:
                    if self._is_mouse_over_strip(context, s, mouse_pos):
                        clicked_strip = s
                        break

                if clicked_strip and clicked_strip != strip:
                    self.finish(context)
                    if not event.shift:
                        bpy.ops.sequencer.select_all(action='DESELECT')
                    clicked_strip.select = True
                    context.scene.sequence_editor.active_strip = clicked_strip
                    bpy.ops.sequencer.crop('INVOKE_DEFAULT')
                    return {'FINISHED'}
                else:
                    return self.finish(context)

        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            self._autokey_if_changed(context, strip)
            self.active_corner = -1
            draw_data['active_corner'] = -1
            set_draw_data(draw_data)

        elif event.type == 'MOUSEMOVE' and self.active_corner >= 0:
            self._update_crop(context, event)
            for area in context.screen.areas:
                if area.type == 'SEQUENCE_EDITOR':
                    area.tag_redraw()
            return {'RUNNING_MODAL'}

        elif event.type in {'RET', 'NUMPAD_ENTER'}:
            return self.finish(context)

        elif event.type == 'ESC':
            if strip and hasattr(strip, 'crop') and strip.crop:
                crop_data = strip.crop
                crop_data.min_x = int(self.crop_start[0])
                crop_data.max_x = int(self.crop_start[1])
                crop_data.min_y = int(self.crop_start[2])
                crop_data.max_y = int(self.crop_start[3])
            return self.finish(context, cancelled=True)

        elif event.type == 'C' and event.alt and event.value == 'PRESS':
            if strip and hasattr(strip, 'crop') and strip.crop:
                crop_data = strip.crop
                crop_data.min_x = 0
                crop_data.max_x = 0
                crop_data.min_y = 0
                crop_data.max_y = 0
                self.crop_start = (0.0, 0.0, 0.0, 0.0)
                self.crop_current = self.crop_start
                for area in context.screen.areas:
                    if area.type == 'SEQUENCE_EDITOR':
                        area.tag_redraw()
            return {'RUNNING_MODAL'}

        elif event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}

        elif event.value == 'PRESS':
            # Check if this key is bound to a transform operator
            transform_op = self._find_transform_operator(context, event)
            if transform_op:
                self.finish(context)
                category, name = transform_op.split('.')
                try:
                    op = getattr(getattr(bpy.ops, category), name)
                    op('INVOKE_DEFAULT')
                except AttributeError:
                    pass
                return {'FINISHED'}

        return {'RUNNING_MODAL'}

    def finish(self, context, cancelled=False):
        """Take down the draw handler, the timer and the overlay state.

        Reachable from modal(), from cancel(), and from the branch that hands
        over to a click on another strip, so everything it removes is checked
        for having gone already.
        """
        set_crop_active(False)

        # None means invoke() found no show_gizmo to save, which is not the same
        # as having saved False.
        if self.prev_show_gizmo is not None and context.space_data:
            context.space_data.show_gizmo = self.prev_show_gizmo

        if self.timer:
            try:
                context.window_manager.event_timer_remove(self.timer)
            except ValueError:
                pass
            self.timer = None

        if get_draw_handle() is not None:
            try:
                bpy.types.SpaceSequenceEditor.draw_handler_remove(get_draw_handle(), 'PREVIEW')
            except ValueError:
                pass
            set_draw_handle(None)

        clear_crop_state()
        self.active_corner = -1

        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'SEQUENCE_EDITOR':
                    for region in area.regions:
                        region.tag_redraw()

        return {'CANCELLED'} if cancelled else {'FINISHED'}

    def _get_corner_at_mouse(self, context, event):
        """The handle nearest the cursor within SELECT_RADIUS, or -1.

        Nearest rather than first: at a grab radius of 25px the corners and the
        edge midpoints of a crop rect narrower than 100px on screen sit inside
        each other's radius, and taking the first match would hand every such
        click to a corner whatever the user aimed at.
        """
        mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))
        corners, midpoints = self._get_crop_corners(context)

        best, best_distance = -1, SELECT_RADIUS
        for i, pos in enumerate(list(corners) + list(midpoints)):
            distance = (pos - mouse_pos).length
            if distance <= best_distance:
                best, best_distance = i, distance

        return best

    def _get_crop_corners(self, context):
        """Get the corner and edge midpoint positions in screen space."""
        strip = context.scene.sequence_editor.active_strip
        scene = context.scene
        if not strip or not context.region:
            return [], []

        corners, _, _ = get_strip_geometry_with_flip_support(strip, scene)
        edge_midpoints = get_edge_midpoints(corners)

        view2d = context.region.view2d
        res_x = scene.render.resolution_x
        res_y = scene.render.resolution_y

        screen_corners = [
            Vector(res_to_screen(c.x, c.y, res_x, res_y, view2d))
            for c in corners
        ]
        screen_midpoints = [
            Vector(res_to_screen(m.x, m.y, res_x, res_y, view2d))
            for m in edge_midpoints
        ]

        return screen_corners, screen_midpoints

    def cancel(self, context):
        """Called when operator is canceled by Blender."""
        return self.finish(context, cancelled=True)

    def _autokey_if_changed(self, context, strip):
        """Key the channels this drag moved, if auto-key is on.

        Fires per handle release rather than once at the end, because a single
        modal session can drag several handles and each is its own edit. The
        undo step is not this method's problem: unlike the gizmo, this operator
        carries bl_options {'REGISTER', 'UNDO'} and Blender pushes one when the
        modal finishes, so the keys inserted here land inside it.

        Why it is needed at all: writing strip.crop through RNA never triggers
        auto-keying, whatever the toggle says.
        """
        if self.active_corner < 0:
            return
        if not strip or not hasattr(strip, 'crop') or not strip.crop:
            return

        # A click that moved nothing must not leave a keyframe behind.
        started_at = tuple(int(v) for v in self.crop_start)
        ended_at = (strip.crop.min_x, strip.crop.max_x,
                    strip.crop.min_y, strip.crop.max_y)
        if ended_at == started_at:
            return

        flip_x, flip_y = get_strip_flip_state(strip)
        autokey_crop(context, strip, self.active_corner, flip_x, flip_y)

    def _update_crop(self, context, event):
        """Update crop values based on mouse drag with flip support."""
        strip = context.scene.sequence_editor.active_strip
        if not strip or not hasattr(strip, 'crop') or not strip.crop:
            return

        # Movement since the previous event, not since the grab. Accumulating
        # onto the last accepted crop is what stops a crop held against a limit
        # from stranding the cursor out in the disallowed region, with every
        # pixel of that invisible travel to be dragged back before the edge
        # moves again. apply_crop_changes has the rest of the contract.
        dx = event.mouse_region_x - self.mouse_last[0]
        dy = event.mouse_region_y - self.mouse_last[1]
        self.mouse_last = (event.mouse_region_x, event.mouse_region_y)

        dx_res, dy_res, flip_x, flip_y = compute_crop_delta(
            dx, dy, context.region.view2d, strip)
        strip_width, strip_height = get_strip_dimensions(strip, context.scene)
        self.crop_current = apply_crop_changes(
            self.active_corner, strip, dx_res, dy_res,
            self.crop_current, strip_width, strip_height, flip_x, flip_y)

    def _find_transform_operator(self, context, event):
        """Find if the pressed key is bound to a transform operator.

        Returns the operator idname (e.g. 'transform.translate') or None.
        """
        wm = context.window_manager
        transform_ops = ['transform.translate', 'transform.resize', 'transform.rotate']

        for kc in [wm.keyconfigs.user, wm.keyconfigs.active]:
            keymaps_to_check = []

            preview_km = kc.keymaps.find(get_preview_keymap_name(),
                                         space_type='SEQUENCE_EDITOR', region_type='WINDOW')
            if preview_km:
                keymaps_to_check.append(preview_km)

            sequencer_km = kc.keymaps.find(get_sequencer_keymap_name(),
                                           space_type='SEQUENCE_EDITOR', region_type='WINDOW')
            if sequencer_km:
                keymaps_to_check.append(sequencer_km)

            window_km = kc.keymaps.find('Window', space_type='EMPTY', region_type='WINDOW')
            if window_km:
                keymaps_to_check.append(window_km)

            for km in keymaps_to_check:
                for kmi in km.keymap_items:
                    if (kmi.active and
                        kmi.idname in transform_ops and
                        kmi.type == event.type and
                        kmi.shift == event.shift and
                        kmi.ctrl == event.ctrl and
                        kmi.alt == event.alt and
                        kmi.oskey == event.oskey):
                        return kmi.idname

        return None

    def _get_visible_strips(self, context):
        """Croppable strips visible at the current frame, sorted top to bottom.

        WARNING: the crop filter is load-bearing, not tidiness. A strip with no
        crop also has no transform, and get_strip_geometry_with_flip_support
        then falls back to offset 0 and scale 1 - the whole render rectangle -
        so an unfiltered strip matches a click anywhere in the preview. A sound
        strip on a higher channel than the one being cropped would swallow every
        click-through test and end the crop, with nothing to report.
        """
        scene = context.scene
        if not scene.sequence_editor:
            return []

        current_frame = scene.frame_current
        strips = []

        for strip in get_strips(scene.sequence_editor):
            if hasattr(strip, 'crop') and is_strip_visible_at_frame(strip, current_frame):
                strips.append(strip)

        strips.sort(key=lambda s: s.channel, reverse=True)
        return strips

    def _is_mouse_over_strip(self, context, strip, mouse_pos):
        """Check if mouse is over the given strip with flip support."""
        scene = context.scene
        corners, _, _ = get_strip_geometry_with_flip_support(strip, scene)

        view2d = context.region.view2d
        res_x = scene.render.resolution_x
        res_y = scene.render.resolution_y

        screen_corners = [
            Vector(res_to_screen(c.x, c.y, res_x, res_y, view2d))
            for c in corners
        ]

        return point_in_polygon(mouse_pos, screen_corners)
