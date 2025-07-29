# General Notes For Claude (work in progress)
1. Research things before guessing
2. Use docstrings
3. Discuss big changes before going ahead.

# BL EasyCrop - Context for Claude

## Project Overview
BL EasyCrop is a Blender addon that adds professional crop tools to the Video Sequence Editor (VSE). It provides both modal operator-based and gizmo-based interfaces for cropping video strips in the sequencer preview.

## Current Implementation

### Core Architecture
- **Modal Operator**: `SEQUENCER_OT_crop_modal` - Original click-and-drag cropping interface
- **Gizmo System**: `EASYCROP_GGT_crop_handles` - Visual handles for interactive cropping
- **Toolbar Integration**: Custom tools in VSE toolbar for easy access
- **Core Logic**: Shared crop calculation functions in `operators/crop_core.py`

### File Structure
```
D:\Dev\BL_EasyCrop\BL_EasyCrop\
├── __init__.py                     # Main addon registration
├── operators/
│   ├── crop_modal.py              # Modal operator implementation
│   ├── crop_core.py               # Shared crop calculation functions
│   └── crop_drawing.py            # Drawing utilities for crop handles
├── gizmos/
│   └── crop_handles_gizmo.py      # Gizmo-based crop interface
├── tools/
│   └── crop_tools.py              # Toolbar tool definitions
└── presets/
    └── keymap/
        └── sequencer.py           # Keymap for sequencer shortcuts
```

### Key Features
1. **Visual Crop Handles**: 8 handles (4 corners, 4 edges) + center symbol
2. **Real-time Preview**: Live preview of crop changes in sequencer
3. **Transform Support**: Handles rotation, scaling, and flipping correctly
4. **Keyboard Shortcuts**: C key activates gizmo tool, Shift+C for modal
5. **Toolbar Integration**: Dedicated crop tools in VSE toolbar
6. **Handle Visual Feedback**: Orange highlight on hover, consistent 6px sizing

## Current Tool Setup

### Primary Interface: Gizmo Tool
- **Activation**: C key or toolbar button
- **Tool ID**: `sequencer.crop_handles_tool`
- **Visual**: Persistent handles with orange hover feedback
- **Workflow**: Click and drag handles directly, gizmos stay visible

### Secondary Interface: Modal Operator
- **Activation**: Shift+C key or menu
- **Tool ID**: `SEQUENCER_OT_crop_modal`
- **Visual**: Temporary handles that appear during operation
- **Workflow**: Single-use operation, handles disappear after use

## Technical Implementation Details

### Crop Calculation Logic
- **Coordinate System**: Uses Blender's sequencer preview coordinate system
- **Transform Handling**: Accounts for strip rotation, scaling, and flip states
- **Boundary Constraints**: Prevents invalid crop values
- **Strip Geometry**: Calculates precise handle positions based on current crop state

### Handle Positioning
- **Corner Handles**: Positioned at actual crop boundaries
- **Edge Handles**: Positioned at midpoints of crop edges
- **Center Handle**: Shows crop tool icon, positioned at strip center
- **Visual Rotation**: Handles rotate with strip to maintain visual alignment

### Flip State Management
- **Remap Logic**: Handles are remapped based on flip_x and flip_y states
- **Visual Consistency**: Users see handles in logical positions regardless of flips
- **Coordinate Translation**: Internal coordinate system accounts for all transform states

## Usage Patterns
1. **Standard Cropping**: Activate gizmo tool (C), drag handles to adjust crop
3. **Menu Access**: Strip menu > Transform > Crop options
4. **Toolbar**: Click crop tool icons in VSE toolbar

## Critical Technical Lessons Learned

### Gizmo Cursor Behavior and Mouse Warping
- **Problem**: Gizmo `use_grab_cursor=True` automatically restores cursor to drag start position after `exit()` method
- **Solution**: Use `bpy.app.timers.register()` with 50ms delay to warp cursor after Blender's restoration
- **Implementation**: Hide cursor with `cursor_modal_set('NONE')` during restoration, then warp and restore with `cursor_modal_restore()`
- **Coordinate Conversion**: Must convert region coordinates to window coordinates: `window_x = region.x + screen_x`

### Gizmo Multi-Layer Rotation System
- **Critical Issue**: Gizmos have two separate rotation calculations that must match:
  1. **Positioning Layer** (`refresh()` method): Where handles appear on screen
  2. **Drawing Layer** (`_draw_handle_square()` method): How handle squares are rotated
- **Problem**: Using different rotation sources causes visual mismatch with flipped strips
- **Solution**: Drawing layer must extract rotation from gizmo's `matrix_basis` (set by positioning layer)
- **Code**: `rotation_angle = self.matrix_basis.to_3x3().to_euler().z`

### Strip Flip State Handling  
- **Flip Compensation**: Already handled in `crop_core.py` geometry calculation - don't double-compensate
- **Flip Detection**: Check `flip_x != flip_y` for single-axis flips (problematic cases)
- **Geometry Source**: Both modal and gizmo use `get_strip_geometry_with_flip_support()` - ensures consistency

### Menu Integration Best Practices
- **Context Setting**: Use `self.layout.operator_context = 'INVOKE_REGION_PREVIEW'` for menu items
- **Automatic Shortcuts**: Blender automatically adds keyboard shortcuts to menu items - don't manually format
- **Modal vs Tool**: Menu items should call modal operators like native transforms, not switch tools

## Known Working Features
- ✅ Gizmo tool activation and handle display
- ✅ Real-time crop preview during drag operations
- ✅ Handle positioning with rotation/flip support
- ✅ Keyboard shortcuts and toolbar integration  
- ✅ Handle visual feedback (orange hover highlighting)
- ✅ Proper tool registration and polling
- ✅ Cross-compatibility with modal operator
- ✅ Boundary constraint handling
- ✅ Consistent handle sizing (6px)
- ✅ Deferred cursor warping to final handle position
- ✅ Multi-layer rotation system with flip compensation
- ✅ Menu integration with proper context handling

## Current Status
The addon is fully functional with both gizmo and modal interfaces working correctly. The gizmo system provides the primary user interface with persistent visual handles and proper cursor targeting. The modal operator serves as a secondary interface accessible via menus and shortcuts. All rotation, flipping, and cursor behavior issues have been resolved.