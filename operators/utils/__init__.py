# Make utils a proper Python package
from . import draw
from . import geometry
from . import selection

# Export specific functions for easier access
from .geometry import get_preview_offset, get_strip_corners, get_strip_box, rotate_point
from .draw import draw_line
from .selection import get_visible_strips

__all__ = [
    'draw',
    'geometry', 
    'selection',
    'get_preview_offset',
    'get_strip_corners',
    'get_strip_box',
    'rotate_point',
    'draw_line',
    'get_visible_strips',
]