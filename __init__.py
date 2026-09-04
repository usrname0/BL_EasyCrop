"""
BL Easy Crop - Crop interface for Blender's Video Sequence Editor
"""


import bpy
from pathlib import Path
from bpy.types import WorkSpaceTool

from .operators.crop_operators import EASYCROP_OT_crop, get_preview_keymap_name
from .operators.crop_core import (
    is_strip_visible_at_frame,
    get_crop_state,
    clear_crop_state,
    get_draw_handle,
    get_selected_strips
)
from .gizmos import (
    register_crop_handles_gizmo,
    unregister_crop_handles_gizmo
)


class EASYCROP_OT_clear_crop(bpy.types.Operator):
    """Clear crop from selected strips"""
    bl_idname = "sequencer.clear_crop"
    bl_label = "Clear Crop"
    bl_description = "Clear crop from all selected strips"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context: bpy.types.Context):
        if not context.scene.sequence_editor:
            return False

        for strip in get_selected_strips(context):
            if hasattr(strip, 'crop'):
                return True
        return False

    def execute(self, context: bpy.types.Context):
        cleared_count = 0

        for strip in get_selected_strips(context):
            # crop is declared on the concrete strip subclasses, not on Strip,
            # so one getattr is both the capability check and the handle.
            crop = getattr(strip, 'crop', None)
            if crop:
                crop.min_x = 0
                crop.max_x = 0
                crop.min_y = 0
                crop.max_y = 0
                cleared_count += 1

        if cleared_count > 0:
            self.report({'INFO'}, f"Cleared crop from {cleared_count} strip(s)")
        else:
            self.report({'INFO'}, "No strips with crop found")

        return {'FINISHED'}


class EASYCROP_TOOL_crop_handles(WorkSpaceTool):
    """The toolbar entry that turns the crop handles on.

    Selecting it is the only way in: bl_keymap is None and nothing registers a
    shortcut for it. The two shortcuts this addon does register, Shift+C and
    Alt+C, both belong to the modal operator.
    """
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_context_mode = 'PREVIEW'

    bl_idname = "sequencer.crop_handles_tool"
    bl_label = "Crop"
    bl_description = "Crop strips using individual handle gizmos"
    # An absolute path with no suffix; Blender appends .dat itself.
    bl_icon = str(Path(__file__).parent / "icons" / "crop")
    bl_widget = "EASYCROP_GGT_crop_handles"

    # The gizmos take their own events (use_event_handle_all), so there is
    # nothing left for a tool-level keymap to do.
    bl_keymap = None

    @staticmethod
    def draw_settings(context, layout, tool):
        """Report in the tool header why handles are or are not showing."""
        seq_editor = context.scene.sequence_editor
        if not seq_editor:
            layout.label(text="No sequence editor")
            return

        active_strip = seq_editor.active_strip
        current_frame = context.scene.frame_current

        crop_state = get_crop_state()
        if crop_state['active']:
            layout.label(text="Modal crop mode active", icon='INFO')
            layout.label(text="(Handles tool disabled)")
        elif active_strip and hasattr(active_strip, 'crop'):
            if is_strip_visible_at_frame(active_strip, current_frame):
                layout.label(text=f"Ready: {active_strip.name}")
                layout.label(text="Drag handles to crop directly")
                layout.label(text="Click center to start modal mode")
            else:
                layout.label(text="Strip not at current frame")
        else:
            layout.label(text="Select a croppable strip")


# Menu functions
def menu_func_crop(self, context):
    """Add Easy Crop to Strip/Image Transform menus."""
    if context.space_data.view_type in {'PREVIEW', 'SEQUENCER_PREVIEW'}:
        self.layout.operator_context = 'INVOKE_REGION_PREVIEW'
        self.layout.operator("sequencer.crop", text="Crop")


def menu_func_image_clear(self, context):
    """Add Clear Crop to Image > Clear menu"""
    if context.space_data.view_type in {'PREVIEW', 'SEQUENCER_PREVIEW'}:
        self.layout.operator("sequencer.clear_crop", text="Crop")


# Registration
classes = [
    EASYCROP_OT_crop,
    EASYCROP_OT_clear_crop,
]

# Menus this addon appends to. All three exist in every supported Blender
# (measured 4.4.3 through 5.2.1), but they are resolved by name so that a
# future rename costs a missing menu entry rather than a failed registration.
_MENUS = (
    ("SEQUENCER_MT_strip_transform", menu_func_crop),
    ("SEQUENCER_MT_image_transform", menu_func_crop),
    ("SEQUENCER_MT_image_clear", menu_func_image_clear),
)

addon_keymaps = []


def register():
    """Register operators, gizmos, the toolbar tool, keymaps and menu entries."""
    for cls in classes:
        bpy.utils.register_class(cls)

    register_crop_handles_gizmo()

    keyconfig = bpy.context.window_manager.keyconfigs.addon
    if keyconfig:
        # The VSE preview keymap was renamed "SequencerPreview" -> "Preview" in
        # Blender 4.5: 4.4.3 has only the old name, 4.5.3+ only the new. The
        # modal operator resolves the same name when it reads the user's keymap,
        # so the rule lives in one place.
        keymap = keyconfig.keymaps.new(name=get_preview_keymap_name(),
                                       space_type="SEQUENCE_EDITOR",
                                       region_type="WINDOW")
        addon_keymaps.append(
            (keymap, keymap.keymap_items.new("sequencer.crop", 'C', 'PRESS', shift=True)))
        addon_keymaps.append(
            (keymap, keymap.keymap_items.new("sequencer.clear_crop", 'C', 'PRESS', alt=True)))

    bpy.utils.register_tool(EASYCROP_TOOL_crop_handles,
                            after={"builtin.transform"}, separator=False)

    for menu_name, func in _MENUS:
        menu = getattr(bpy.types, menu_name, None)
        if menu is not None:
            menu.append(func)


def unregister():
    """Undo everything register() did, in reverse order."""
    clear_crop_state()

    # Restore gizmo visibility in case a modal crop was interrupted with the
    # gizmos hidden. There is no screen in background mode.
    screen = getattr(bpy.context, "screen", None)
    if screen is not None:
        for area in screen.areas:
            if area.type == 'SEQUENCE_EDITOR':
                for space in area.spaces:
                    if space.type == 'SEQUENCE_EDITOR':
                        space.show_gizmo = True

    for menu_name, func in reversed(_MENUS):
        menu = getattr(bpy.types, menu_name, None)
        if menu is not None:
            menu.remove(func)

    bpy.utils.unregister_tool(EASYCROP_TOOL_crop_handles)

    for keymap, item in addon_keymaps:
        keymap.keymap_items.remove(item)
    addon_keymaps.clear()

    unregister_crop_handles_gizmo()

    # The modal operator installs a preview draw handler; drop it if a crop was
    # still running when the addon was disabled.
    handle = get_draw_handle()
    if handle is not None:
        bpy.types.SpaceSequenceEditor.draw_handler_remove(handle, 'PREVIEW')

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()