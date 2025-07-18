"""
BL Easy Crop - Operators with improved keybinding detection

This module contains the updated operators with better keybinding detection
that checks multiple keymap sources to find user's custom transform bindings.
"""

import bpy
import math
from mathutils import Vector

# Import from crop modules
from .crop_core import (
    get_crop_state, set_crop_active, get_draw_data, set_draw_data,
    get_draw_handle, set_draw_handle, clear_crop_state,
    get_strip_geometry_with_flip_support, is_strip_visible_at_frame, point_in_polygon
)
from .crop_drawing import draw_crop_handles


class EASYCROP_OT_crop(bpy.types.Operator):
    """Crop strips in the preview window"""
    bl_idname = "easycrop.crop"
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
            # Type hint for Pylance
            space_seq: 'SpaceSequenceEditor' = space  # type: ignore
            if space_seq.view_type not in {'PREVIEW', 'SEQUENCER_PREVIEW'}:
                return False
        
        # Just need any selected strip with crop capability
        if scene.sequence_editor.active_strip and hasattr(scene.sequence_editor.active_strip, 'crop'):
            return True
        
        # Also check if any selected strip has crop
        for strip in context.selected_sequences:
            if hasattr(strip, 'crop'):
                return True
                
        return False
    
    def invoke(self, context, event):
        crop_state = get_crop_state()
        
        # If crop is already active, handle the click within the existing modal
        if crop_state['active']:
            # Don't start a new crop operation - let the existing modal handle it
            self.report({'WARNING'}, "Crop mode already active")
            return {'CANCELLED'}
        
        # Get the active strip - if no active strip or not croppable, check if clicking on a strip
        strip = context.scene.sequence_editor.active_strip if context.scene.sequence_editor else None
        current_frame = context.scene.frame_current
        
        # Check if we have a suitable active strip that's visible
        has_suitable_active = (strip and 
                              hasattr(strip, 'crop') and 
                              is_strip_visible_at_frame(strip, current_frame))
        
        # If no suitable active strip, try to find one under the mouse
        if not has_suitable_active:
            mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))
            strips = self.get_visible_strips(context)
            clicked_strip = None
            
            # Check from top to bottom for a croppable strip
            for s in reversed(strips):
                if hasattr(s, 'crop') and self.is_mouse_over_strip(context, s, mouse_pos):
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
                # No suitable strip found - report and exit
                self.report({'INFO'}, "No croppable strip found - select an image/movie strip")
                return {'CANCELLED'}
        
        # Now we should have a suitable strip - proceed with crop initialization
        if not has_suitable_active:
            self.report({'INFO'}, "No suitable strip for cropping")
            return {'CANCELLED'}
        
        # Initialize instance variables
        self.active_corner = -1
        self.mouse_start = (0.0, 0.0)
        self.crop_start = (0.0, 0.0, 0.0, 0.0)
        self.timer = None
        self.first_click = False
        self.first_mouse_x = 0
        self.first_mouse_y = 0
        
        # Store the current transform overlay state so we can restore it later
        self.prev_show_gizmo = None
        if hasattr(context.space_data, 'show_gizmo'):
            space_seq: 'SpaceSequenceEditor' = context.space_data  # type: ignore
            self.prev_show_gizmo = space_seq.show_gizmo
            # Hide transform gizmos while cropping to avoid conflicts
            space_seq.show_gizmo = False
        
        # Clean up any existing handler first (safety check for lingering state)
        if get_draw_handle() is not None:
            try:
                bpy.types.SpaceSequenceEditor.draw_handler_remove(
                    get_draw_handle(), 'PREVIEW')
            except:
                pass
            set_draw_handle(None)
        
        # Mark crop as active FIRST
        set_crop_active(True)
        
        # Initialize draw data immediately - this ensures handles will be visible
        set_draw_data({
            'active_corner': -1,
            'frame_count': 0
        })
        
        # Store the initial crop values
        if strip and hasattr(strip, 'crop') and strip.crop:
            crop_data = getattr(strip, 'crop', None)  # type: ignore
            if crop_data:
                self.crop_start = (
                    crop_data.min_x,
                    crop_data.max_x,
                    crop_data.min_y,
                    crop_data.max_y
                )
            else:
                self.crop_start = (0, 0, 0, 0)
        else:
            self.crop_start = (0, 0, 0, 0)
        
        # Set up drawing handler (handles will draw immediately)
        handler = bpy.types.SpaceSequenceEditor.draw_handler_add(
            draw_crop_handles, (), 'PREVIEW', 'POST_PIXEL')
        set_draw_handle(handler)
        
        # Force an immediate redraw
        context.area.tag_redraw()
        
        # Add a timer to force redraws
        wm = context.window_manager
        self.timer = wm.event_timer_add(0.01, window=context.window)
        
        # Add modal handler
        wm.modal_handler_add(self)
        
        return {'RUNNING_MODAL'}
    
    def modal(self, context, event):
        draw_data = get_draw_data()
        
        # Handle timer events to force redraw
        if event.type == 'TIMER':
            # Force redraw on timer
            for area in context.screen.areas:
                if area.type == 'SEQUENCE_EDITOR':
                    area.tag_redraw()
            return {'RUNNING_MODAL'}
        
        strip = context.scene.sequence_editor.active_strip
        if not strip:
            return self.finish(context)
        
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            # Check if clicking on a handle
            corner = self.get_corner_at_mouse(context, event)
            
            if corner >= 0:
                self.active_corner = corner
                draw_data['active_corner'] = corner
                set_draw_data(draw_data)
                self.mouse_start = (event.mouse_region_x, event.mouse_region_y)
                # Store current crop values for this drag
                if strip and hasattr(strip, 'crop'):
                    crop_data = getattr(strip, 'crop', None)  # type: ignore
                    if crop_data:
                        self.crop_start = (
                            crop_data.min_x,
                            crop_data.max_x,
                            crop_data.min_y,
                            crop_data.max_y
                        )
                    else:
                        self.crop_start = (0, 0, 0, 0)
                else:
                    self.crop_start = (0, 0, 0, 0)
            else:
                # Not clicking on a handle - check if clicking on another strip
                mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))
                strips = self.get_visible_strips(context)
                clicked_strip = None
                
                # Check from top to bottom
                for s in reversed(strips):
                    if self.is_mouse_over_strip(context, s, mouse_pos):
                        clicked_strip = s
                        break
                
                if clicked_strip and clicked_strip != strip:
                    # Clicking on a different strip - exit crop and select it
                    self.finish(context)
                    if not event.shift:
                        bpy.ops.sequencer.select_all(action='DESELECT')
                    clicked_strip.select = True
                    context.scene.sequence_editor.active_strip = clicked_strip
                    # Re-activate crop on the new strip
                    if hasattr(clicked_strip, 'crop'):
                        bpy.ops.easycrop.crop('INVOKE_DEFAULT')  # type: ignore
                    return {'FINISHED'}
                else:
                    # Clicking outside any strip or on same strip - just exit crop mode
                    return self.finish(context)
        
        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            if self.active_corner >= 0:
                pass  # Handle release silently
            self.active_corner = -1
            draw_data['active_corner'] = -1
            set_draw_data(draw_data)
        
        elif event.type == 'MOUSEMOVE' and self.active_corner >= 0:
            self.update_crop(context, event)
            # Force immediate redraw to show the changes
            for area in context.screen.areas:
                if area.type == 'SEQUENCE_EDITOR':
                    area.tag_redraw()
            return {'RUNNING_MODAL'}
        
        elif event.type in {'RET', 'NUMPAD_ENTER'}:
            # Exit crop mode on Enter
            return self.finish(context)
        
        elif event.type == 'ESC':
            # Restore original crop values
            if strip and hasattr(strip, 'crop'):
                crop_data = getattr(strip, 'crop', None)  # type: ignore
                if crop_data:
                    crop_data.min_x = int(self.crop_start[0])
                    crop_data.max_x = int(self.crop_start[1])
                    crop_data.min_y = int(self.crop_start[2])
                    crop_data.max_y = int(self.crop_start[3])
            return self.finish(context, cancelled=True)
        
        elif self.is_transform_key(context, event):
            # Exit crop mode and activate the transform
            transform_op = self.get_transform_operator(context, event)
            if transform_op:
                self.finish(context)
                # Invoke the actual operator the user has bound to this key
                operator_parts = transform_op.split('.')
                if len(operator_parts) == 2:
                    category, name = operator_parts
                    try:
                        op = getattr(getattr(bpy.ops, category), name)
                        # Use INVOKE_DEFAULT to let Blender handle the transform properly
                        op('INVOKE_DEFAULT')
                    except AttributeError:
                        # Fallback if operator doesn't exist
                        pass
            return {'FINISHED'}
        
        elif event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        
        return {'RUNNING_MODAL'}
    
    def finish(self, context, cancelled=False):
        """Clean up and exit"""
        # Clear the active flag FIRST
        set_crop_active(False)
        
        # Restore transform gizmo visibility
        if hasattr(self, 'prev_show_gizmo') and self.prev_show_gizmo is not None and hasattr(context.space_data, 'show_gizmo'):
            space_seq: 'SpaceSequenceEditor' = context.space_data  # type: ignore
            space_seq.show_gizmo = self.prev_show_gizmo
        
        # Remove timer
        if hasattr(self, 'timer') and self.timer:
            try:
                context.window_manager.event_timer_remove(self.timer)
            except:
                pass
            self.timer = None
        
        # Remove draw handler - be extra thorough
        if get_draw_handle() is not None:
            try:
                bpy.types.SpaceSequenceEditor.draw_handler_remove(
                    get_draw_handle(), 'PREVIEW')
            except:
                pass
            set_draw_handle(None)
        
        # Clear all state
        clear_crop_state()
        
        # Reset operator state
        self.active_corner = -1
        self.first_click = False
        
        # Force redraw all sequence editor areas
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'SEQUENCE_EDITOR':
                    for region in area.regions:
                        region.tag_redraw()
        
        return {'CANCELLED'} if cancelled else {'FINISHED'}
    
    def get_corner_at_mouse(self, context, event):
        """Check if mouse is over a corner or edge handle"""
        mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))
        corners, midpoints = self.get_crop_corners(context)
        
        # Check corner handles first (0-3)
        for i, corner in enumerate(corners):
            if (corner - mouse_pos).length < 10:
                return i
        
        # Check edge handles (4-7)
        for i, midpoint in enumerate(midpoints):
            if (midpoint - mouse_pos).length < 10:
                return i + 4
        
        return -1
    
    def get_crop_corners(self, context):
        """Get the corner and edge midpoint positions in screen space"""
        strip = context.scene.sequence_editor.active_strip
        scene = context.scene
        if not strip or not context.region:
            return [], []
        
        # Use the new flip-aware geometry calculation
        corners, (pivot_x, pivot_y), (scale_x, scale_y, flip_x, flip_y) = get_strip_geometry_with_flip_support(strip, scene)
        
        # Calculate edge midpoints (after rotation)
        edge_midpoints = []
        for i in range(4):
            next_i = (i + 1) % 4
            midpoint = (corners[i] + corners[next_i]) / 2
            edge_midpoints.append(midpoint)
        
        # Use Blender's view2d system for accurate transformation
        view2d = context.region.view2d
        res_x = scene.render.resolution_x
        res_y = scene.render.resolution_y
        
        screen_corners = []
        for corner in corners:
            # Transform from resolution space to view space
            view_x = corner.x - res_x / 2
            view_y = corner.y - res_y / 2
            
            # Use view2d to get screen coordinates
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
    
    def update_crop(self, context, event):
        """Update crop values based on mouse drag with flip support"""
        strip = context.scene.sequence_editor.active_strip
        scene = context.scene
        
        # Ensure we have a valid strip with crop capability
        if not strip or not hasattr(strip, 'crop') or not strip.crop:
            return
        
        # Calculate mouse delta
        dx = event.mouse_region_x - self.mouse_start[0]
        dy = event.mouse_region_y - self.mouse_start[1]
        
        # Use view2d to convert screen delta to resolution space
        view2d = context.region.view2d
        
        # Get two points to calculate the scale
        p1 = view2d.region_to_view(0, 0)
        p2 = view2d.region_to_view(1, 1)
        
        # Calculate pixels per unit in view space
        scale_x = abs(p2[0] - p1[0])
        scale_y = abs(p2[1] - p1[1])
        
        # Convert mouse delta to view space units
        dx_view = dx * scale_x
        dy_view = dy * scale_y
        
        # Get the strip's scale and flip state
        strip_scale_x = strip.transform.scale_x if hasattr(strip, 'transform') and hasattr(strip.transform, 'scale_x') else 1.0
        strip_scale_y = strip.transform.scale_y if hasattr(strip, 'transform') and hasattr(strip.transform, 'scale_y') else 1.0
        
        # Check for Mirror X/Y checkboxes (flip transforms)
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
        
        # Handle rotation if present
        angle = 0
        if hasattr(strip, 'rotation_start'):
            angle = -math.radians(strip.rotation_start)  # Negative to reverse rotation, convert from degrees
        elif hasattr(strip, 'transform') and hasattr(strip.transform, 'rotation'):
            angle = -strip.transform.rotation  # Already in radians, just negate
        
        # When flipped, rotation direction is reversed
        if flip_x != flip_y:  # XOR - if only one axis is flipped
            angle = -angle
        
        # Rotate the delta if strip is rotated
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
        
        # IMPORTANT: When strips are flipped, we need to invert the mouse deltas
        # because dragging "right" on a flipped strip should increase the "left" crop value
        if flip_x:
            dx_res = -dx_res
        if flip_y:
            dy_res = -dy_res
        
        # Get the original strip dimensions (before crop/scale)
        strip_width = strip.elements[0].orig_width if hasattr(strip, 'elements') and strip.elements else scene.render.resolution_x
        strip_height = strip.elements[0].orig_height if hasattr(strip, 'elements') and strip.elements else scene.render.resolution_y
        
        # Apply crop changes based on which handle is being dragged
        self._apply_crop_changes(strip, dx_res, dy_res, strip_width, strip_height, flip_x, flip_y)
    
    def _apply_crop_changes(self, strip, dx_res, dy_res, strip_width, strip_height, flip_x, flip_y):
        """Apply crop changes based on the active corner and flip state"""
        if self.active_corner < 4:
            # Corner handles - need to remap based on both X and Y flips
            corner_map = self.active_corner
            
            # Remap corner based on flips
            if flip_x and flip_y:
                # Both flipped: BL<->TR, TL<->BR
                corner_remap = {0: 2, 1: 3, 2: 0, 3: 1}
                corner_map = corner_remap[self.active_corner]
            elif flip_x:
                # X flipped: BL<->BR, TL<->TR  
                corner_remap = {0: 3, 1: 2, 2: 1, 3: 0}
                corner_map = corner_remap[self.active_corner]
            elif flip_y:
                # Y flipped: BL<->TL, BR<->TR
                corner_remap = {0: 1, 1: 0, 2: 3, 3: 2}
                corner_map = corner_remap[self.active_corner]
            
            # Apply crop changes based on remapped corner
            if corner_map == 0:  # Bottom-left (in original image space)
                # X direction: moving right increases left crop
                new_min_x = int(max(0, self.crop_start[0] + dx_res))
                if new_min_x + strip.crop.max_x < strip_width:
                    strip.crop.min_x = new_min_x
                
                # Y direction: moving up increases bottom crop
                new_min_y = int(max(0, self.crop_start[2] + dy_res))
                if new_min_y + strip.crop.max_y < strip_height:
                    strip.crop.min_y = new_min_y
                        
            elif corner_map == 1:  # Top-left (in original image space)
                # X direction: moving right increases left crop
                new_min_x = int(max(0, self.crop_start[0] + dx_res))
                if new_min_x + strip.crop.max_x < strip_width:
                    strip.crop.min_x = new_min_x
                
                # Y direction: moving up decreases top crop
                new_max_y = int(max(0, self.crop_start[3] - dy_res))
                if strip.crop.min_y + new_max_y < strip_height:
                    strip.crop.max_y = new_max_y
                        
            elif corner_map == 2:  # Top-right (in original image space)
                # X direction: moving right decreases right crop
                new_max_x = int(max(0, self.crop_start[1] - dx_res))
                if strip.crop.min_x + new_max_x < strip_width:
                    strip.crop.max_x = new_max_x
                
                # Y direction: moving up decreases top crop
                new_max_y = int(max(0, self.crop_start[3] - dy_res))
                if strip.crop.min_y + new_max_y < strip_height:
                    strip.crop.max_y = new_max_y
                        
            elif corner_map == 3:  # Bottom-right (in original image space)
                # X direction: moving right decreases right crop
                new_max_x = int(max(0, self.crop_start[1] - dx_res))
                if strip.crop.min_x + new_max_x < strip_width:
                    strip.crop.max_x = new_max_x
                
                # Y direction: moving up increases bottom crop
                new_min_y = int(max(0, self.crop_start[2] + dy_res))
                if new_min_y + strip.crop.max_y < strip_height:
                    strip.crop.min_y = new_min_y
        else:
            # Edge handles - need to remap based on flips
            edge_index = self.active_corner - 4
            edge_map = edge_index
            
            # Remap edges based on flips
            if flip_x and flip_y:
                # Both flipped: Left<->Right, Top<->Bottom
                edge_remap = {0: 2, 1: 3, 2: 0, 3: 1}
                edge_map = edge_remap[edge_index]
            elif flip_x:
                # X flipped: Left<->Right
                edge_remap = {0: 2, 1: 1, 2: 0, 3: 3}
                edge_map = edge_remap[edge_index]
            elif flip_y:
                # Y flipped: Top<->Bottom
                edge_remap = {0: 0, 1: 3, 2: 2, 3: 1}
                edge_map = edge_remap[edge_index]
            
            # Apply crop changes based on remapped edge
            if edge_map == 0:  # Left edge (in original image space)
                new_min_x = int(max(0, self.crop_start[0] + dx_res))
                if new_min_x + strip.crop.max_x < strip_width:
                    strip.crop.min_x = new_min_x
                        
            elif edge_map == 1:  # Top edge (in original image space)
                new_max_y = int(max(0, self.crop_start[3] - dy_res))
                if strip.crop.min_y + new_max_y < strip_height:
                    strip.crop.max_y = new_max_y
                        
            elif edge_map == 2:  # Right edge (in original image space)
                new_max_x = int(max(0, self.crop_start[1] - dx_res))
                if strip.crop.min_x + new_max_x < strip_width:
                    strip.crop.max_x = new_max_x
                        
            elif edge_map == 3:  # Bottom edge (in original image space)
                new_min_y = int(max(0, self.crop_start[2] + dy_res))
                if new_min_y + strip.crop.max_y < strip_height:
                    strip.crop.min_y = new_min_y
    
    def is_transform_key(self, context, event):
        """Check if the pressed key is bound to a transform operator - NOW CHECKING USER KEYCONFIG!"""
        if event.value != 'PRESS':
            return False
        
        print(f"\n=== CHECKING USER KEYCONFIG ===")
        print(f"Looking for key: {event.type}, shift={event.shift}, ctrl={event.ctrl}, alt={event.alt}")
        
        # Get the window manager and keyconfigs
        wm = context.window_manager
        
        # KEY INSIGHT: Check keyconfigs.user instead of keyconfigs.active!
        # User customizations are stored in the user keyconfig
        kc_user = wm.keyconfigs.user
        kc_active = wm.keyconfigs.active
        
        print(f"Active keyconfig: {kc_active.name}")
        print(f"User keyconfig: {kc_user.name}")
        
        transform_ops = ['transform.translate', 'transform.resize', 'transform.rotate']
        
        # Check USER keyconfig first (where customizations live)
        print(f"\n=== CHECKING USER KEYCONFIG KEYMAPS ===")
        keymaps_to_check = []
        
        # 1. SequencerPreview in user keyconfig
        preview_km = kc_user.keymaps.find('SequencerPreview', space_type='SEQUENCE_EDITOR', region_type='WINDOW')
        if preview_km:
            print(f"Found USER SequencerPreview: {preview_km.name}")
            keymaps_to_check.append(('USER SequencerPreview', preview_km))
        
        # 2. Sequencer in user keyconfig
        sequencer_km = kc_user.keymaps.find('Sequencer', space_type='SEQUENCE_EDITOR', region_type='WINDOW')
        if sequencer_km:
            print(f"Found USER Sequencer: {sequencer_km.name}")
            keymaps_to_check.append(('USER Sequencer', sequencer_km))
        
        # 3. Window in user keyconfig
        window_km = kc_user.keymaps.find('Window', space_type='EMPTY', region_type='WINDOW')
        if window_km:
            print(f"Found USER Window: {window_km.name}")
            keymaps_to_check.append(('USER Window', window_km))
        
        # Also check active keyconfig as fallback
        print(f"\n=== CHECKING ACTIVE KEYCONFIG KEYMAPS ===")
        
        # 4. SequencerPreview in active keyconfig
        preview_km_active = kc_active.keymaps.find('SequencerPreview', space_type='SEQUENCE_EDITOR', region_type='WINDOW')
        if preview_km_active:
            print(f"Found ACTIVE SequencerPreview: {preview_km_active.name}")
            keymaps_to_check.append(('ACTIVE SequencerPreview', preview_km_active))
        
        # Show detailed transform analysis
        print(f"\n=== DETAILED TRANSFORM ANALYSIS ===")
        for km_name, km in keymaps_to_check:
            print(f"\n--- {km_name} ---")
            transform_count = 0
            for kmi in km.keymap_items:
                if kmi.idname in transform_ops:
                    print(f"  {kmi.idname} -> {kmi.type} (shift={kmi.shift}, ctrl={kmi.ctrl}, alt={kmi.alt}, active={kmi.active})")
                    transform_count += 1
            print(f"  Total transform ops: {transform_count}")
        
        # Check for exact matches
        print(f"\n--- Looking for exact matches ---")
        for km_name, km in keymaps_to_check:
            for kmi in km.keymap_items:
                if (kmi.active and 
                    kmi.idname in transform_ops and
                    kmi.type == event.type and 
                    kmi.shift == event.shift and
                    kmi.ctrl == event.ctrl and
                    kmi.alt == event.alt and
                    kmi.oskey == event.oskey):
                    print(f"MATCH FOUND in {km_name}: {kmi.idname}")
                    return True
        
        print(f"No matches found")
        print(f"=== END USER KEYCONFIG CHECK ===\n")
        return False
    
    def get_transform_operator(self, context, event):
        """Get which transform operator is bound to the pressed key - NOW CHECKING USER KEYCONFIG!"""
        # Get the window manager and keyconfigs
        wm = context.window_manager
        
        # Check BOTH user and active keyconfigs
        kc_user = wm.keyconfigs.user
        kc_active = wm.keyconfigs.active
        
        transform_ops = ['transform.translate', 'transform.resize', 'transform.rotate']
        
        # Priority order: user keyconfig first (customizations), then active (defaults)
        keyconfigs_to_check = [
            ('USER', kc_user),
            ('ACTIVE', kc_active)
        ]
        
        for kc_name, kc in keyconfigs_to_check:
            keymaps_to_check = []
            
            # Find keymaps in this keyconfig
            preview_km = kc.keymaps.find('SequencerPreview', space_type='SEQUENCE_EDITOR', region_type='WINDOW')
            if preview_km:
                keymaps_to_check.append(preview_km)
            
            sequencer_km = kc.keymaps.find('Sequencer', space_type='SEQUENCE_EDITOR', region_type='WINDOW')
            if sequencer_km:
                keymaps_to_check.append(sequencer_km)
            
            window_km = kc.keymaps.find('Window', space_type='EMPTY', region_type='WINDOW')
            if window_km:
                keymaps_to_check.append(window_km)
            
            # Check for exact matches in this keyconfig
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
    
    def get_visible_strips(self, context):
        """Get all strips visible at the current frame"""
        scene = context.scene
        if not scene.sequence_editor:
            return []
        
        current_frame = scene.frame_current
        strips = []
        
        for strip in scene.sequence_editor.sequences:
            # Check if strip is visible at current frame
            if is_strip_visible_at_frame(strip, current_frame):
                strips.append(strip)
        
        # Sort by channel (higher channels on top)
        strips.sort(key=lambda s: s.channel)
        
        return strips
    
    def is_mouse_over_strip(self, context, strip, mouse_pos):
        """Check if mouse is over the given strip with flip support"""
        # Use the new flip-aware geometry
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
    bl_idname = "easycrop.activate_tool"
    bl_label = "Activate Crop Tool"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}
    
    @classmethod
    def poll(cls, context):
        return (context.scene.sequence_editor is not None and
                context.space_data and 
                context.space_data.type == 'SEQUENCE_EDITOR' and
                context.space_data.view_type in {'PREVIEW', 'SEQUENCER_PREVIEW'})
    
    def invoke(self, context, event):
        # Just like Blender's built-in transforms: immediately activate the crop operator
        # The crop operator will handle all the logic about what to crop
        return bpy.ops.easycrop.crop('INVOKE_DEFAULT')


class EASYCROP_OT_select_and_crop(bpy.types.Operator):
    """Select strip and activate crop mode"""
    bl_idname = "easycrop.select_and_crop"
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
        # First, check if we're clicking on a strip
        mouse_pos = Vector((event.mouse_region_x, event.mouse_region_y))
        
        # Get all visible strips at current frame
        strips = self.get_visible_strips(context)
        clicked_strip = None
        
        # Check from top to bottom (reversed order)
        for strip in reversed(strips):
            if hasattr(strip, 'crop') and self.is_mouse_over_strip(context, strip, mouse_pos):
                clicked_strip = strip
                break
        
        if clicked_strip:
            # Select the strip
            if not event.shift:
                bpy.ops.sequencer.select_all(action='DESELECT')
            
            clicked_strip.select = True
            context.scene.sequence_editor.active_strip = clicked_strip
            
            # Give a tiny delay to ensure selection is processed
            context.area.tag_redraw()
            
            # Now activate crop mode
            return bpy.ops.easycrop.crop('INVOKE_DEFAULT')
        else:
            # No strip clicked - if we have an active strip with crop that's visible, activate immediately
            seq_editor = context.scene.sequence_editor
            active_strip = seq_editor.active_strip if seq_editor else None
            current_frame = context.scene.frame_current
            
            if (active_strip and 
                hasattr(active_strip, 'crop') and 
                is_strip_visible_at_frame(active_strip, current_frame)):
                
                # Check if crop is already active
                crop_state = get_crop_state()
                if not crop_state['active']:
                    return bpy.ops.easycrop.crop('INVOKE_DEFAULT')
        
        return {'FINISHED'}
    
    def get_visible_strips(self, context):
        """Get all strips visible at the current frame"""
        scene = context.scene
        if not scene.sequence_editor:
            return []
        
        current_frame = scene.frame_current
        strips = []
        
        for strip in scene.sequence_editor.sequences:
            # Check if strip is visible at current frame
            if is_strip_visible_at_frame(strip, current_frame):
                strips.append(strip)
        
        # Sort by channel (higher channels on top)
        strips.sort(key=lambda s: s.channel)
        
        return strips
    
    def is_mouse_over_strip(self, context, strip, mouse_pos):
        """Check if mouse is over the given strip with flip support"""
        # Use the new flip-aware geometry
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