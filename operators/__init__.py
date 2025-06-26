# Make operators a proper Python package
from . import crop
from . import select

# Import the operator classes for easier access
from .crop import EASYCROP_OT_crop
from .select import EASYCROP_OT_select

__all__ = [
    'crop',
    'select',
    'EASYCROP_OT_crop',
    'EASYCROP_OT_select',
]