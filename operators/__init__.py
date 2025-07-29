"""
Operators package for BL Easy Crop

This package contains all the crop-related operators and functionality.
"""

# Import the main classes and functions for external use
from .crop_operators import (
    EASYCROP_OT_crop,
    EASYCROP_OT_select_and_crop, 
    EASYCROP_OT_activate_tool
)

from .crop_core import (
    is_strip_visible_at_frame,
    get_crop_state,
    set_crop_active,
    clear_crop_state
)

__all__ = [
    'EASYCROP_OT_crop',
    'EASYCROP_OT_select_and_crop', 
    'EASYCROP_OT_activate_tool',
    'is_strip_visible_at_frame',
    'get_crop_state',
    'set_crop_active',
    'clear_crop_state'
]