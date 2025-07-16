"""
BL Easy Crop - Main crop module

This module imports and coordinates all crop functionality.
It serves as the main entry point for the crop system.
"""

# Import all submodules
from . import crop_core
from . import crop_drawing  
from . import crop_operators

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

# Export everything needed by the main __init__.py
__all__ = [
    # Submodules
    'crop_core',
    'crop_drawing', 
    'crop_operators',
    
    # Main operator classes
    'EASYCROP_OT_crop',
    'EASYCROP_OT_select_and_crop',
    'EASYCROP_OT_activate_tool',
    
    # Core functions
    'is_strip_visible_at_frame',
    'get_crop_state',
    'set_crop_active', 
    'clear_crop_state'
]