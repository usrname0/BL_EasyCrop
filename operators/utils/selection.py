import bpy


def get_visible_strips():
    """Get all strips visible at the current frame"""
    context = bpy.context
    scene = context.scene
    
    if not scene.sequence_editor:
        return []
    
    current_frame = scene.frame_current
    strips = []
    
    for strip in scene.sequence_editor.sequences:
        # Check if strip is visible at current frame
        if (strip.frame_final_start <= current_frame <= strip.frame_final_end and
            not strip.mute):
            strips.append(strip)
    
    # Sort by channel (higher channels on top)
    strips.sort(key=lambda s: s.channel, reverse=True)
    
    return strips