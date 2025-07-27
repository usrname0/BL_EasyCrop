"""
BL Easy Crop - Tool Monitor

This module monitors when the crop tool is selected and auto-triggers crop mode.
"""

import bpy
from .crop_core import get_crop_state, is_strip_visible_at_frame


class EASYCROP_OT_tool_monitor(bpy.types.Operator):
    """Monitor tool selection and auto-trigger crop mode"""
    bl_idname = "sequencer.crop_tool_monitor"
    bl_label = "Crop Tool Monitor"
    bl_options = {'INTERNAL'}
    
    _timer = None
    _last_tool = None
    _crop_triggered = False
    
    def modal(self, context, event):
        if event.type == 'TIMER':
            # Check current tool
            try:
                current_tool = None
                if context.workspace and hasattr(context.workspace, 'tools'):
                    # Look for active crop tool
                    for tool in context.workspace.tools:
                        if hasattr(tool, 'mode') and tool.mode == 'PREVIEW':
                            current_tool = tool.idname
                            break
                
                # Detect tool change to crop tool
                if (current_tool == "sequencer.crop_tool" and 
                    self._last_tool != "sequencer.crop_tool"):
                    
                    # Tool just became active - check if we should auto-trigger
                    if not self._crop_triggered and self._should_auto_trigger(context):
                        self._crop_triggered = True
                        try:
                            bpy.ops.sequencer.crop('INVOKE_DEFAULT')
                        except:
                            pass
                
                # Reset trigger flag when tool changes away from crop
                elif current_tool != "sequencer.crop_tool":
                    self._crop_triggered = False
                
                self._last_tool = current_tool
                
            except Exception:
                pass
        
        return {'PASS_THROUGH'}
    
    def _should_auto_trigger(self, context):
        """Check if we should auto-trigger crop mode"""
        # Don't trigger if crop is already active
        crop_state = get_crop_state()
        if crop_state['active']:
            return False
        
        # Only trigger if there's a suitable active strip
        if not context.scene.sequence_editor:
            return False
            
        active_strip = context.scene.sequence_editor.active_strip
        if not active_strip or not hasattr(active_strip, 'crop'):
            return False
            
        current_frame = context.scene.frame_current
        if not is_strip_visible_at_frame(active_strip, current_frame):
            return False
        
        return True
    
    def invoke(self, context, event):
        # Start the timer
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def cancel(self, context):
        if self._timer:
            try:
                context.window_manager.event_timer_remove(self._timer)
            except:
                pass
            self._timer = None


# Global monitor instance
_monitor_running = False


def start_tool_monitor():
    """Start the tool monitor if not already running"""
    global _monitor_running
    if not _monitor_running and bpy.context:
        try:
            bpy.ops.sequencer.crop_tool_monitor('INVOKE_DEFAULT')
            _monitor_running = True
            print("✓ Crop tool monitor started")
        except Exception as e:
            print(f"Failed to start crop tool monitor: {e}")


def stop_tool_monitor():
    """Stop the tool monitor"""
    global _monitor_running
    _monitor_running = False
    print("✓ Crop tool monitor stopped")