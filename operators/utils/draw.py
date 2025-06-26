import gpu
from gpu_extras.batch import batch_for_shader


def draw_line(v1, v2, width, color):
    """Draw a line between two points"""
    # For Blender 4.x, we use the built-in shaders
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    
    # Set line width
    gpu.state.line_width_set(width)
    
    # Create batch
    vertices = [v1, v2]
    batch = batch_for_shader(shader, 'LINES', {"pos": vertices})
    
    # Draw
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)
    
    # Reset line width
    gpu.state.line_width_set(1.0)


def draw_quad(bl, tl, tr, br, color):
    """Draw a filled quad"""
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    
    vertices = [bl, br, tl, tr]
    indices = ((0, 1, 2), (2, 1, 3))
    
    batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
    
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)