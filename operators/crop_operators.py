"""
BL Easy Crop - Operators

This module contains the main operators for the crop functionality,
including the primary crop operator and helper operators for tool activation.
"""

import bpy
import math
from mathutils import Vector

from .crop_core import (
    get_crop_state, set_crop_active, get_draw_data, set_draw_data,
    get_draw_handle, set_draw_handle, clear_crop_state,
    get_strip_geometry_with_flip_support, is_strip_visible_at_frame, point_in_polygon
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
        
        # Check if we're in preview mode
        space = context.space_data
        if space and space.type == 'SEQUENCE_EDITOR':
            if space.view_type not in {'PREVIEW', 'SEQUENCER_PREVIEW'}:
                return False
        
        # Check for croppable strips
        if scene.sequence_editor.active_strip and hasattr(scene.sequence_editor.active_strip, 'crop'):
            return True
        
        for strip in context.selected_sequences:
            if hasattr(strip, 'crop'):
                return True
                
        return False
    
    def invoke(self, context, event):
        crop_state = get_crop_state()
        
        # If crop is already active, don't start a new operation
        if crop_state['active']:
            self.report({'WARNING'}, "Crop mode already active")
            return {'CANCELLED'}
        
        strip = context.scene.sequence_editor.active_strip
        current_frame = context.scene.frame_current
        
        # Check if we have a suitable active strip that's visible
        has_suitable_active = (strip and 
                              hasattr(strip, 'crop') and 
                              is_strip_visible_at_frame(strip, current_frame))
        
        # If we have a suitable active strip, use it directly (no mouse click needed)
        if has_suitable_active:
            # This is the key change - we proceed directly without requiring a click
            pass
        else:
            # If no suitable active strip, try to find one under the mouse
            mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))
            strips = self._get_visible_strips(context)
            clicked_strip = None
            
            # Check from top to bottom for a croppable strip
            for s in strips:
                if hasattr(s, 'crop') and self._is_mouse_over_strip(context, s, mouse_pos):
                    clicked_strip = s
                    break
            
            if clicked_strip:
                # Select the clicked strip and make it active
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
        self.mouse_start = (0.0, 0.0)
        self.crop_start = (0.0, 0.0, 0.0, 0.0)
        self.timer = None
        
        # Store the current transform overlay state
        self.prev_show_gizmo = None
        if hasattr(context.space_data, 'show_gizmo'):
            self.prev_show_gizmo = context.space_data.show_gizmo
            context.space_data.show_gizmo = False
        
        # Clean up any existing handler
        if get_draw_handle() is not None:
            try:
                bpy.types.SpaceSequenceEditor.draw_handler_remove(get_draw_handle(), 'PREVIEW')
            except:
                pass
            set_draw_handle(None)
        
        # Mark crop as active
        set_crop_active(True)
        
        # Initialize draw data
        set_draw_data({'active_corner': -1, 'frame_count': 0})
        
        # Store initial crop values
        if strip and hasattr(strip, 'crop') and strip.crop:
            crop_data = strip.crop
            self.crop_start = (crop_data.min_x, crop_data.max_x, crop_data.min_y, crop_data.max_y)
        else:
            self.crop_start = (0, 0, 0, 0)
        
        # Set up drawing handler
        handler = bpy.types.SpaceSequenceEditor.draw_handler_add(
            draw_crop_handles, (), 'PREVIEW', 'POST_PIXEL')
        set_draw_handle(handler)
        
        # Force redraw
        context.area.tag_redraw()
        
        # Add timer for redraws
        wm = context.window_manager
        self.timer = wm.event_timer_add(0.01, window=context.window)
        
        # Add modal handler
        wm.modal_handler_add(self)
        
        return {'RUNNING_MODAL'}
    
    def modal(self, context, event):
        draw_data = get_draw_data()
        
        # Store current mouse position for hover detection
        if hasattr(event, 'mouse_region_x') and hasattr(event, 'mouse_region_y'):
            draw_data['mouse_x'] = event.mouse_region_x
            draw_data['mouse_y'] = event.mouse_region_y
            set_draw_data(draw_data)
        
        # Handle timer events
        if event.type == 'TIMER':
            for area in context.screen.areas:
                if area.type == 'SEQUENCE_EDITOR':
                    area.tag_redraw()
            return {'RUNNING_MODAL'}
        
        strip = context.scene.sequence_editor.active_strip
        if not strip:
            return self.finish(context)
        
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            # Check if clicking on a handle
            corner = self._get_corner_at_mouse(context, event)
            
            if corner >= 0:
                self.active_corner = corner
                draw_data['active_corner'] = corner
                set_draw_data(draw_data)
                self.mouse_start = (event.mouse_region_x, event.mouse_region_y)
                
                # Store current crop values for this drag
                if strip and hasattr(strip, 'crop'):
                    crop_data = strip.crop
                    if crop_data:
                        self.crop_start = (crop_data.min_x, crop_data.max_x, crop_data.min_y, crop_data.max_y)
                    else:
                        self.crop_start = (0, 0, 0, 0)
            else:
                # Check if clicking on another strip
                mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))
                strips = self._get_visible_strips(context)
                clicked_strip = None
                
                # Check from top to bottom
                for s in strips:
                    if self._is_mouse_over_strip(context, s, mouse_pos):
                        clicked_strip = s
                        break
                
                if clicked_strip and clicked_strip != strip:
                    # Switch to different strip
                    self.finish(context)
                    if not event.shift:
                        bpy.ops.sequencer.select_all(action='DESELECT')
                    clicked_strip.select = True
                    context.scene.sequence_editor.active_strip = clicked_strip
                    if hasattr(clicked_strip, 'crop'):
                        bpy.ops.sequencer.crop('INVOKE_DEFAULT')
                    return {'FINISHED'}
                else:
                    # Exit crop mode
                    return self.finish(context)
        
        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if self.active_corner >= 0:
                pass  # Handle release silently
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
            # Restore original crop values
            if strip and hasattr(strip, 'crop'):
                crop_data = strip.crop
                if crop_data:
                    crop_data.min_x = int(self.crop_start[0])
                    crop_data.max_x = int(self.crop_start[1])
                    crop_data.min_y = int(self.crop_start[2])
                    crop_data.max_y = int(self.crop_start[3])
            return self.finish(context, cancelled=True)
        
        elif event.type == 'C' and event.alt and event.value == 'PRESS':
            # Clear crop with Alt+C while in crop mode
            if strip and hasattr(strip, 'crop'):
                crop_data = strip.crop
                if crop_data:
                    crop_data.min_x = 0
                    crop_data.max_x = 0
                    crop_data.min_y = 0
                    crop_data.max_y = 0
                    # Update the stored start values so ESC won't restore the old crop
                    self.crop_start = (0, 0, 0, 0)
                    # Force redraw to show the change immediately
                    for area in context.screen.areas:
                        if area.type == 'SEQUENCE_EDITOR':
                            area.tag_redraw()
            return {'RUNNING_MODAL'}
        
        elif self._is_transform_key(context, event):
            # Exit crop mode and activate the transform
            transform_op = self._get_transform_operator(context, event)
            if transform_op:
                self.finish(context)
                operator_parts = transform_op.split('.')
                if len(operator_parts) == 2:
                    category, name = operator_parts
                    try:
                        op = getattr(getattr(bpy.ops, category), name)
                        op('INVOKE_DEFAULT')
                    except AttributeError:
                        pass
            return {'FINISHED'}
        
        elif event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        
        return {'RUNNING_MODAL'}
    
    def finish(self, context, cancelled=False):
        """Clean up and exit"""
        # Clear the active flag
        set_crop_active(False)
        
        # Restore transform gizmo visibility
        if hasattr(self, 'prev_show_gizmo') and self.prev_show_gizmo is not None and hasattr(context.space_data, 'show_gizmo'):
            context.space_data.show_gizmo = self.prev_show_gizmo
        
        # Remove timer
        if hasattr(self, 'timer') and self.timer:
            try:
                context.window_manager.event_timer_remove(self.timer)
            except:
                pass
            self.timer = None
        
        # Remove draw handler
        if get_draw_handle() is not None:
            try:
                bpy.types.SpaceSequenceEditor.draw_handler_remove(get_draw_handle(), 'PREVIEW')
            except:
                pass
            set_draw_handle(None)
        
        # Clear all state
        clear_crop_state()
        
        # Reset operator state
        self.active_corner = -1
        
        # Force redraw
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'SEQUENCE_EDITOR':
                    for region in area.regions:
                        region.tag_redraw()
        
        return {'CANCELLED'} if cancelled else {'FINISHED'}
    
    def _get_corner_at_mouse(self, context, event):
        """Check if mouse is over a corner or edge handle"""
        mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))
        corners, midpoints = self._get_crop_corners(context)
        
        # Check corner handles first (0-3)
        for i, corner in enumerate(corners):
            if (corner - mouse_pos).length < 10:
                return i
        
        # Check edge handles (4-7)
        for i, midpoint in enumerate(midpoints):
            if (midpoint - mouse_pos).length < 10:
                return i + 4
        
        return -1
    
    def _get_crop_corners(self, context):
        """Get the corner and edge midpoint positions in screen space"""
        strip = context.scene.sequence_editor.active_strip
        scene = context.scene
        if not strip or not context.region:
            return [], []
        
        corners, (pivot_x, pivot_y), (scale_x, scale_y, flip_x, flip_y) = get_strip_geometry_with_flip_support(strip, scene)
        
        # Calculate edge midpoints
        edge_midpoints = []
        for i in range(4):
            next_i = (i + 1) % 4
            midpoint = (corners[i] + corners[next_i]) / 2
            edge_midpoints.append(midpoint)
        
        # Transform to screen coordinates
        view2d = context.region.view2d
        res_x = scene.render.resolution_x
        res_y = scene.render.resolution_y
        
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
        
        return screen_corners, screen_midpoints
    
    def cancel(self, context):
        """Called when operator is cancelled by Blender"""
        return self.finish(context, cancelled=True)
    
    def _update_crop(self, context, event):
        """Update crop values based on mouse drag with flip support"""
        strip = context.scene.sequence_editor.active_strip
        scene = context.scene
        
        if not strip or not hasattr(strip, 'crop') or not strip.crop:
            return
        
        # Calculate mouse delta
        dx = event.mouse_region_x - self.mouse_start[0]
        dy = event.mouse_region_y - self.mouse_start[1]
        
        # Convert screen delta to view space
        view2d = context.region.view2d
        p1 = view2d.region_to_view(0, 0)
        p2 = view2d.region_to_view(1, 1)
        
        scale_x = abs(p2[0] - p1[0])
        scale_y = abs(p2[1] - p1[1])
        
        dx_view = dx * scale_x
        dy_view = dy * scale_y
        
        # Get strip properties
        strip_scale_x = strip.transform.scale_x if hasattr(strip, 'transform') and hasattr(strip.transform, 'scale_x') else 1.0
        strip_scale_y = strip.transform.scale_y if hasattr(strip, 'transform') and hasattr(strip.transform, 'scale_y') else 1.0
        
        # Check for flip states
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
        
        # Handle rotation
        angle = 0
        if hasattr(strip, 'rotation_start'):
            angle = -math.radians(strip.rotation_start)
        elif hasattr(strip, 'transform') and hasattr(strip.transform, 'rotation'):
            angle = -strip.transform.rotation
        
        # Adjust rotation for flip
        if flip_x != flip_y:
            angle = -angle
        
        # Apply rotation to delta
        if angle != 0:
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)
            rotated_dx = dx_view * cos_a - dy_view * sin_a
            rotated_dy = dx_view * sin_a + dy_view * cos_a
            dx_view = rotated_dx
            dy_view = rotated_dy
        
        # Convert to strip's original image space
        dx_res = dx_view / strip_scale_x
        dy_res = dy_view / strip_scale_y
        
        # Invert deltas for flipped strips
        if flip_x:
            dx_res = -dx_res
        if flip_y:
            dy_res = -dy_res
        
        # Get strip dimensions
        strip_width = scene.render.resolution_x
        strip_height = scene.render.resolution_y
        
        if hasattr(strip, 'elements') and strip.elements and len(strip.elements) > 0:
            elem = strip.elements[0]
            if hasattr(elem, 'orig_width') and hasattr(elem, 'orig_height'):
                strip_width = elem.orig_width
                strip_height = elem.orig_height
        
        # Apply crop changes
        self._apply_crop_changes(strip, dx_res, dy_res, strip_width, strip_height, flip_x, flip_y)
    
    def _apply_crop_changes(self, strip, dx_res, dy_res, strip_width, strip_height, flip_x, flip_y):
        """Apply crop changes based on the active corner and flip state"""
        if self.active_corner < 4:
            # Corner handles - remap based on flips
            corner_map = self.active_corner
            
            if flip_x and flip_y:
                corner_remap = {0: 2, 1: 3, 2: 0, 3: 1}
                corner_map = corner_remap[self.active_corner]
            elif flip_x:
                corner_remap = {0: 3, 1: 2, 2: 1, 3: 0}
                corner_map = corner_remap[self.active_corner]
            elif flip_y:
                corner_remap = {0: 1, 1: 0, 2: 3, 3: 2}
                corner_map = corner_remap[self.active_corner]
            
            # Apply crop changes based on remapped corner
            if corner_map == 0:  # Bottom-left
                new_min_x = int(max(0, self.crop_start[0] + dx_res))
                if new_min_x + strip.crop.max_x < strip_width:
                    strip.crop.min_x = new_min_x
                
                new_min_y = int(max(0, self.crop_start[2] + dy_res))
                if new_min_y + strip.crop.max_y < strip_height:
                    strip.crop.min_y = new_min_y
                        
            elif corner_map == 1:  # Top-left
                new_min_x = int(max(0, self.crop_start[0] + dx_res))
                if new_min_x + strip.crop.max_x < strip_width:
                    strip.crop.min_x = new_min_x
                
                new_max_y = int(max(0, self.crop_start[3] - dy_res))
                if strip.crop.min_y + new_max_y < strip_height:
                    strip.crop.max_y = new_max_y
                        
            elif corner_map == 2:  # Top-right
                new_max_x = int(max(0, self.crop_start[1] - dx_res))
                if strip.crop.min_x + new_max_x < strip_width:
                    strip.crop.max_x = new_max_x
                
                new_max_y = int(max(0, self.crop_start[3] - dy_res))
                if strip.crop.min_y + new_max_y < strip_height:
                    strip.crop.max_y = new_max_y
                        
            elif corner_map == 3:  # Bottom-right
                new_max_x = int(max(0, self.crop_start[1] - dx_res))
                if strip.crop.min_x + new_max_x < strip_width:
                    strip.crop.max_x = new_max_x
                
                new_min_y = int(max(0, self.crop_start[2] + dy_res))
                if new_min_y + strip.crop.max_y < strip_height:
                    strip.crop.min_y = new_min_y
        else:
            # Edge handles - remap based on flips
            edge_index = self.active_corner - 4
            edge_map = edge_index
            
            if flip_x and flip_y:
                edge_remap = {0: 2, 1: 3, 2: 0, 3: 1}
                edge_map = edge_remap[edge_index]
            elif flip_x:
                edge_remap = {0: 2, 1: 1, 2: 0, 3: 3}
                edge_map = edge_remap[edge_index]
            elif flip_y:
                edge_remap = {0: 0, 1: 3, 2: 2, 3: 1}
                edge_map = edge_remap[edge_index]
            
            # Apply crop changes based on remapped edge
            if edge_map == 0:  # Left edge
                new_min_x = int(max(0, self.crop_start[0] + dx_res))
                if new_min_x + strip.crop.max_x < strip_width:
                    strip.crop.min_x = new_min_x
                        
            elif edge_map == 1:  # Top edge
                new_max_y = int(max(0, self.crop_start[3] - dy_res))
                if strip.crop.min_y + new_max_y < strip_height:
                    strip.crop.max_y = new_max_y
                        
            elif edge_map == 2:  # Right edge
                new_max_x = int(max(0, self.crop_start[1] - dx_res))
                if strip.crop.min_x + new_max_x < strip_width:
                    strip.crop.max_x = new_max_x
                        
            elif edge_map == 3:  # Bottom edge
                new_min_y = int(max(0, self.crop_start[2] + dy_res))
                if new_min_y + strip.crop.max_y < strip_height:
                    strip.crop.min_y = new_min_y
    
    def _is_transform_key(self, context, event):
        """Check if the pressed key is bound to a transform operator"""
        if event.value != 'PRESS':
            return False
        
        wm = context.window_manager
        kc_user = wm.keyconfigs.user
        kc_active = wm.keyconfigs.active
        
        transform_ops = ['transform.translate', 'transform.resize', 'transform.rotate']
        
        keyconfigs_to_check = [kc_user, kc_active]
        
        for kc in keyconfigs_to_check:
            keymaps_to_check = []
            
            preview_km = kc.keymaps.find(get_preview_keymap_name(), space_type='SEQUENCE_EDITOR', region_type='WINDOW')
            if preview_km:
                keymaps_to_check.append(preview_km)
            
            sequencer_km = kc.keymaps.find(get_sequencer_keymap_name(), space_type='SEQUENCE_EDITOR', region_type='WINDOW')
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
                        return True
        
        return False
    
    def _get_transform_operator(self, context, event):
        """Get which transform operator is bound to the pressed key"""
        wm = context.window_manager
        kc_user = wm.keyconfigs.user
        kc_active = wm.keyconfigs.active
        
        transform_ops = ['transform.translate', 'transform.resize', 'transform.rotate']
        
        keyconfigs_to_check = [kc_user, kc_active]
        
        for kc in keyconfigs_to_check:
            keymaps_to_check = []
            
            preview_km = kc.keymaps.find(get_preview_keymap_name(), space_type='SEQUENCE_EDITOR', region_type='WINDOW')
            if preview_km:
                keymaps_to_check.append(preview_km)
            
            sequencer_km = kc.keymaps.find(get_sequencer_keymap_name(), space_type='SEQUENCE_EDITOR', region_type='WINDOW')
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
        """Get all strips visible at the current frame, sorted top to bottom"""
        scene = context.scene
        if not scene.sequence_editor:
            return []
        
        current_frame = scene.frame_current
        strips = []
        
        for strip in scene.sequence_editor.sequences:
            if is_strip_visible_at_frame(strip, current_frame):
                strips.append(strip)
        
        # Sort by channel (higher channels on top), then reverse for top-to-bottom checking
        strips.sort(key=lambda s: s.channel, reverse=True)
        return strips
    
    def _is_mouse_over_strip(self, context, strip, mouse_pos):
        """Check if mouse is over the given strip with flip support"""
        scene = context.scene
        corners, (pivot_x, pivot_y), (scale_x, scale_y, flip_x, flip_y) = get_strip_geometry_with_flip_support(strip, scene)
        
        # Convert to screen space
        view2d = context.region.view2d
        res_x = scene.render.resolution_x
        res_y = scene.render.resolution_y
        
        screen_corners = []
        for corner in corners:
            view_x = corner.x - res_x / 2
            view_y = corner.y - res_y / 2
            screen_co = view2d.view_to_region(view_x, view_y, clip=False)
            screen_corners.append(Vector(screen_co))
        
        return point_in_polygon(mouse_pos, screen_corners)


class EASYCROP_OT_activate_tool(bpy.types.Operator):
    """Activate crop tool - direct activation like built-in transforms"""
    bl_idname = "sequencer.activate_tool"
    bl_label = "Activate Crop Tool"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}
    
    @classmethod
    def poll(cls, context):
        return (context.scene.sequence_editor is not None and
                context.space_data and 
                context.space_data.type == 'SEQUENCE_EDITOR' and
                context.space_data.view_type in {'PREVIEW', 'SEQUENCER_PREVIEW'})
    
    def invoke(self, context, event):
        # Immediately activate the crop operator - let it handle strip selection
        return bpy.ops.sequencer.crop('INVOKE_DEFAULT')


class EASYCROP_OT_select_and_crop(bpy.types.Operator):
    """Select strip and activate crop mode"""
    bl_idname = "sequencer.select_and_crop"
    bl_label = "Select and Crop"
    bl_description = "Select a strip in the preview and activate crop mode"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}
    
    @classmethod
    def poll(cls, context):
        return (context.scene.sequence_editor is not None and
                context.space_data and 
                context.space_data.type == 'SEQUENCE_EDITOR' and
                context.space_data.view_type in {'PREVIEW', 'SEQUENCER_PREVIEW'})
    
    def invoke(self, context, event):
        # Check if clicking on a strip
        mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))
        strips = self._get_visible_strips_for_selection(context)
        clicked_strip = None
        
        # Check from top to bottom
        for strip in strips:
            if hasattr(strip, 'crop') and self._is_mouse_over_strip_for_selection(context, strip, mouse_pos):
                clicked_strip = strip
                break
        
        if clicked_strip:
            # Select the strip
            if not event.shift:
                bpy.ops.sequencer.select_all(action='DESELECT')
            
            clicked_strip.select = True
            context.scene.sequence_editor.active_strip = clicked_strip
            
            context.area.tag_redraw()
            
            # Activate crop mode
            return bpy.ops.sequencer.crop('INVOKE_DEFAULT')
        else:
            # Check if we have an active strip ready
            seq_editor = context.scene.sequence_editor
            active_strip = seq_editor.active_strip if seq_editor else None
            current_frame = context.scene.frame_current
            
            if (active_strip and 
                hasattr(active_strip, 'crop') and 
                is_strip_visible_at_frame(active_strip, current_frame)):
                
                crop_state = get_crop_state()
                if not crop_state['active']:
                    return bpy.ops.sequencer.crop('INVOKE_DEFAULT')
        
        return {'FINISHED'}
    
    def _get_visible_strips_for_selection(self, context):
        """Get all strips visible at the current frame for selection, sorted top to bottom"""
        scene = context.scene
        if not scene.sequence_editor:
            return []
        
        current_frame = scene.frame_current
        strips = []
        
        for strip in scene.sequence_editor.sequences:
            if is_strip_visible_at_frame(strip, current_frame):
                strips.append(strip)
        
        # Sort by channel (higher channels on top), then reverse for top-to-bottom checking
        strips.sort(key=lambda s: s.channel, reverse=True)
        return strips
    
    def _is_mouse_over_strip_for_selection(self, context, strip, mouse_pos):
        """Check if mouse is over the given strip for selection"""
        scene = context.scene
        corners, (pivot_x, pivot_y), (scale_x, scale_y, flip_x, flip_y) = get_strip_geometry_with_flip_support(strip, scene)
        
        # Convert to screen space
        view2d = context.region.view2d
        res_x = scene.render.resolution_x
        res_y = scene.render.resolution_y
        
        screen_corners = []
        for corner in corners:
            view_x = corner.x - res_x / 2
            view_y = corner.y - res_y / 2
            screen_co = view2d.view_to_region(view_x, view_y, clip=False)
            screen_corners.append(Vector(screen_co))
        
        return point_in_polygon(mouse_pos, screen_corners)