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

# For backward compatibility, expose the global state variable
# This allows existing code to check _crop_active directly
def _get_crop_active():
    """Get crop active state for backward compatibility"""
    return crop_core._crop_active

def _set_crop_active(value):
    """Set crop active state for backward compatibility"""
    crop_core._crop_active = value

# Create a property-like access to _crop_active
import sys
module = sys.modules[__name__]
module._crop_active = property(_get_crop_active, _set_crop_active)

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
    'clear_crop_state',
    
    # Backward compatibility
    '_crop_active'
]