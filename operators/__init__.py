# Make operators a proper Python package
from . import crop

# Import the operator classes for easier access
from .crop import (
    EASYCROP_OT_crop, 
    EASYCROP_OT_select_and_crop, 
    EASYCROP_OT_activate_tool,
    is_strip_visible_at_frame,
    get_crop_state,
    set_crop_active,
    clear_crop_state
)

__all__ = [
    'crop',
    'EASYCROP_OT_crop',
    'EASYCROP_OT_select_and_crop', 
    'EASYCROP_OT_activate_tool',
    'is_strip_visible_at_frame',
    'get_crop_state',
    'set_crop_active',
    'clear_crop_state'
]