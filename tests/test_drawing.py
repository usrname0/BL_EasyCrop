"""
The gizmo tool draws its handles twice, and the two must produce equal pixels.

Idle, Blender draws the group from the matrices refresh() sets. Once a drag owns
the input Blender stops drawing the group and _draw_handles_with_gpu redraws all
nine by hand from the strip geometry. Two implementations of one picture, and a
disagreement shows up at the instant a drag starts - which reads as the handles
glitching rather than as the two code paths it is.

They were compared on angle and size once before and pronounced equal. That was
too narrow a question, and a user looking at the actual screen caught it: the
handles had visibly different anti-aliasing on their diagonals. Both were true.
The angles agreed; the *pixels* did not.

The cause was that refresh() gave each handle the angle of the edge it sits on,
which for handle i is 90 degrees further round than for handle i-1. A square is
symmetric under 90 degrees, so the drawn shape was identical and the difference
was invisible to any comparison of angle or position. But draw_rotated_square
cuts its square into two triangles by fixed vertex index - ((0,1,2),(2,1,3)) -
so the split diagonal turned with the angle, and 6 of the 8 handles were split
along the other diagonal from how the drag path draws them. Vertex displacements
reached 16.4px, one square's worth of vertex permutation.

So this file asserts on the vertex lists, not on angles. That is the only level
at which the original bug is visible at all.

There were three of these paths, not two: the modal operator's own draw handler
is a third, and it had a third copy of the angle derivation. All three now call
crop_core.handle_screen_angle, and test_both_draw_paths_call_the_shared_helper
is what stops a fourth appearing.

The second half of the same problem was GPU state, and it survived the angle
fix - reported again from a real session, with the right diagnosis attached.
The three paths are called from three different Blender passes: the gizmo tool's
idle draw from the gizmo pass, its drag draw and the modal operator's from
POST_PIXEL draw handlers. Only one of the three set alpha blending, so the other
two rendered the same RGBA at whatever blending their pass happened to leave on,
and a pass without it draws a 0.8-alpha handle opaque. The white handles also
differed outright, 0.8 in the gizmo against 0.7 in the modal operator.

Both are now owned one level down: draw_rotated_square and draw_crop_symbol_at
set and restore their own blend state, and the palette is two constants in
crop_core. A caller cannot forget either. That is what the last two checks here
are for - GPU state itself is not observable from a background Blender, so they
inspect the source instead.

    "/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b \
        --factory-startup --python tests/test_drawing.py
"""

import math
import sys
import traceback
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

WORKSPACE = str(Path(__file__).resolve().parents[2])
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)

from BL_EasyCrop.operators.crop_core import (  # noqa: E402
    get_strip_geometry_with_flip_support, get_edge_midpoints,
    handle_screen_angle, res_to_screen, HANDLE_RADIUS)

WIDTH, HEIGHT = 1920, 1080

failures = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}: expected {want}, got {got}")


class FakeView2D:
    """Identity on resolution space; res_to_screen re-centers before calling."""

    def view_to_region(self, x, y, clip=False):
        return (x + WIDTH / 2, y + HEIGHT / 2)


def make_strip(rot=0.0, sx=1.0, sy=1.0, fx=False, fy=False, crop=None):
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = WIDTH, HEIGHT
    scene.frame_current = 1

    if scene.sequence_editor:
        scene.sequence_editor_clear()
    editor = scene.sequence_editor_create()
    strips = editor.strips if hasattr(editor, "strips") else editor.sequences

    try:
        strip = strips.new_effect(name="video", type='COLOR',
                                  channel=1, frame_start=1, frame_end=50)
    except TypeError:
        # new_effect(frame_end=...) became new_effect(length=...) in 5.1.
        strip = strips.new_effect(name="video", type='COLOR',
                                  channel=1, frame_start=1, length=50)

    strip.transform.rotation = rot
    strip.transform.scale_x, strip.transform.scale_y = sx, sy
    # Mirror lives on the strip, not on strip.transform - the names on the
    # transform do not exist, and setting them there fails silently.
    strip.use_flip_x, strip.use_flip_y = fx, fy
    if crop:
        strip.crop.min_x, strip.crop.max_x, strip.crop.min_y, strip.crop.max_y = crop

    editor.active_strip = strip
    return strip


def square_vertices(center_x, center_y, angle):
    """Exactly what crop_drawing.draw_rotated_square builds, its branch included.

    Duplicated rather than imported because the real one hands its vertices
    straight to a GPU batch and returns nothing. Kept byte-for-byte in step with
    it by test_the_local_copy_matches_the_real_one below.
    """
    half = HANDLE_RADIUS
    if abs(angle) > 0.01:
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        corners_rel = [(-half, -half), (half, -half), (half, half), (-half, half)]
        verts = [(x * cos_a - y * sin_a + center_x, x * sin_a + y * cos_a + center_y)
                 for x, y in corners_rel]
        return [verts[0], verts[1], verts[3], verts[2]]
    return [(center_x - half, center_y - half), (center_x + half, center_y - half),
            (center_x - half, center_y + half), (center_x + half, center_y + half)]


def both_paths(strip):
    """The vertex list each path would draw, for handles 0-7."""
    scene = bpy.context.scene
    corners, _, _ = get_strip_geometry_with_flip_support(strip, scene)
    midpoints = get_edge_midpoints(corners)
    view2d = FakeView2D()

    screen = [Vector(res_to_screen(c.x, c.y, WIDTH, HEIGHT, view2d)) for c in corners]
    screen += [Vector(res_to_screen(m.x, m.y, WIDTH, HEIGHT, view2d)) for m in midpoints]

    # Both paths call handle_screen_angle - the real one, so that a change to
    # it is a change to what this test measures. The drag path hands the result
    # straight to draw_rotated_square.
    angle = handle_screen_angle(screen[:4])
    drag = [square_vertices(p.x, p.y, angle) for p in screen]

    # The idle path puts it through matrix_basis in refresh() and draw() reads
    # it back out, so the float32 matrix round trip is part of what is compared.
    idle = []
    for p in screen:
        matrix = Matrix.Translation((p.x, p.y, 0)) @ Matrix.Rotation(angle, 4, 'Z')
        translation = matrix.translation
        idle.append(square_vertices(translation.x, translation.y,
                                    matrix.to_3x3().to_euler().z))
    return idle, drag


CASES = [
    ("no rotation", {}),
    ("rotation 30deg", dict(rot=math.radians(30))),
    ("rotation -30deg", dict(rot=math.radians(-30))),
    ("rotation 180deg", dict(rot=math.pi)),
    ("rotation 5deg", dict(rot=math.radians(5))),
    ("rotation 0.008 rad, under the threshold", dict(rot=0.008)),
    ("30deg + flip x", dict(rot=math.radians(30), fx=True)),
    ("30deg + flip y", dict(rot=math.radians(30), fy=True)),
    ("30deg + flip both", dict(rot=math.radians(30), fx=True, fy=True)),
    ("flip x, no rotation", dict(fx=True)),
    ("flip both, no rotation", dict(fx=True, fy=True)),
    ("30deg + scale 2.0, 1.0", dict(rot=math.radians(30), sx=2.0, sy=1.0)),
    ("30deg + scale 1.0, 3.0", dict(rot=math.radians(30), sx=1.0, sy=3.0)),
    ("negative scale x", dict(sx=-1.0)),
    ("30deg + a real crop", dict(rot=math.radians(30), crop=(200, 150, 100, 90))),
]

# A tenth of a pixel. Comfortably above the float32 matrix round trip, which
# measures around 1e-6, and far below anything that could be seen.
TOLERANCE = 0.1


def test_both_paths_draw_the_same_square():
    """Every handle, every strip state: the two vertex lists must coincide.

    The tolerance is deliberately loose. This is not a precision test - the bug
    it guards against displaced vertices by 16.4px, and any regression of the
    same kind is a whole vertex permutation, not a rounding difference.
    """
    for label, kwargs in CASES:
        strip = make_strip(**kwargs)
        idle, drag = both_paths(strip)

        worst, worst_handle = 0.0, -1
        for handle, (i_verts, d_verts) in enumerate(zip(idle, drag)):
            for (ix, iy), (dx, dy) in zip(i_verts, d_verts):
                distance = math.hypot(ix - dx, iy - dy)
                if distance > worst:
                    worst, worst_handle = distance, handle

        if worst > TOLERANCE:
            failures.append(
                f"{label}: handle {worst_handle} differs between the idle and "
                f"drag paths by {worst:.3f}px")


def test_an_unrotated_strip_gives_exactly_zero():
    """The one-angle derivation must not need a threshold to reach zero.

    refresh() used to gate on abs(rotation) > 0.01 and snap to 0 below it. The
    gate is gone, so the edge measurement has to land on exactly 0 by itself -
    otherwise an unrotated strip takes draw_rotated_square's rotated branch,
    its vertices stop landing on integer pixels, and every handle in the
    common case softens for no reason.
    """
    for label, kwargs in [("no rotation", {}), ("flip x", dict(fx=True)),
                          ("flip both", dict(fx=True, fy=True))]:
        strip = make_strip(**kwargs)
        scene = bpy.context.scene
        corners, _, _ = get_strip_geometry_with_flip_support(strip, scene)
        view2d = FakeView2D()
        screen = [Vector(res_to_screen(c.x, c.y, WIDTH, HEIGHT, view2d)) for c in corners]

        angle = handle_screen_angle(screen)
        check(f"{label} derives an angle under the draw threshold",
              abs(angle) < 0.01, True)


def test_the_local_copy_matches_the_real_one():
    """square_vertices duplicates draw_rotated_square; pin them together.

    The real one draws rather than returns, so it cannot be called here. If its
    vertex construction changes and this copy does not, every assertion above
    silently starts testing the wrong geometry - the failure mode this suite
    exists to catch, one level up.
    """
    import inspect
    from BL_EasyCrop.operators import crop_drawing

    source = inspect.getsource(crop_drawing.draw_rotated_square)
    for fragment in ("x_rel * cos_a - y_rel * sin_a + center_x",
                     "x_rel * sin_a + y_rel * cos_a + center_y",
                     "vertices = [vertices[0], vertices[1], vertices[3], vertices[2]]",
                     "indices = ((0, 1, 2), (2, 1, 3))",
                     "if abs(angle) > 0.01:"):
        check(f"draw_rotated_square still contains {fragment!r}",
              fragment in source, True)


def test_both_draw_paths_call_the_shared_helper():
    """The comparison above is only meaningful if the real code uses the helper.

    Everything else here reimplements the two paths against handle_screen_angle,
    so it would keep passing if refresh() or the drag path went back to working
    the angle out for itself. This is the assertion that stops that - the exact
    always-passes trap DEV.md warns about, one level up from the one it warns
    about.
    """
    import inspect
    from BL_EasyCrop.gizmos.crop_handles_gizmo import (
        EASYCROP_GT_crop_handle, EASYCROP_GGT_crop_handles)

    from BL_EasyCrop.operators import crop_drawing

    paths = {
        "gizmo drag": inspect.getsource(EASYCROP_GT_crop_handle._draw_handles_with_gpu),
        "gizmo idle": inspect.getsource(EASYCROP_GGT_crop_handles.refresh),
        "modal operator": inspect.getsource(crop_drawing.draw_crop_handles),
    }

    for name, src in paths.items():
        check(f"{name} calls handle_screen_angle",
              "handle_screen_angle" in src, True)
        # Either of the two derivations it replaced is the regression.
        check(f"{name} does not derive an angle itself",
              "atan2" in src, False)
        check(f"{name} does not read transform.rotation for an angle",
              "get_strip_rotation" in src, False)
        check(f"{name} does not gate on a rotation threshold",
              "> 0.01" in src, False)


def test_the_drawing_primitives_manage_their_own_blend_state():
    """A primitive drawn from three different passes cannot trust the pass.

    Each of the three draw paths runs in a different Blender pass, and a pass
    without alpha blending renders a translucent colour opaque. Leaving it to
    the callers meant one of the three remembered and the same handle looked
    different in each interface. Save-set-restore in the primitive is the only
    arrangement a caller cannot get wrong.
    """
    import inspect
    from BL_EasyCrop.operators import crop_drawing

    for name in ("draw_rotated_square", "draw_crop_symbol_at"):
        src = inspect.getsource(getattr(crop_drawing, name))
        check(f"{name} reads the previous blend state", "blend_get()" in src, True)
        check(f"{name} sets alpha blending", "blend_set('ALPHA')" in src, True)
        check(f"{name} restores what it found", "blend_set(prev_blend)" in src, True)


def test_one_palette_for_every_handle():
    """The gizmo drew white handles at 0.8 and the modal operator at 0.7.

    Nothing recorded why, and it is a visible step between the two interfaces.
    Both now read crop_core's constants, and no draw path may carry a literal
    RGBA of its own.
    """
    import inspect
    from BL_EasyCrop.operators import crop_core, crop_drawing
    from BL_EasyCrop.gizmos.crop_handles_gizmo import (
        EASYCROP_GT_crop_handle, EASYCROP_GGT_crop_handles)

    check("white handle alpha is 0.8", crop_core.HANDLE_COLOR, (1.0, 1.0, 1.0, 0.8))
    check("accent is opaque orange", crop_core.ACCENT_COLOR, (1.0, 0.5, 0.0, 1.0))

    sources = {
        "modal operator": inspect.getsource(crop_drawing.draw_crop_handles),
        "gizmo idle draw": inspect.getsource(EASYCROP_GT_crop_handle.draw),
        "gizmo drag draw": inspect.getsource(EASYCROP_GT_crop_handle._draw_handles_with_gpu),
        "gizmo modal draw": inspect.getsource(EASYCROP_GT_crop_handle._draw_handle_common),
    }
    for label, src in sources.items():
        check(f"{label} uses the shared palette",
              "HANDLE_COLOR" in src or "ACCENT_COLOR" in src, True)
        # A literal 4-tuple of floats is the thing that drifted last time.
        for literal in ("1.0, 1.0, 1.0, 0.7", "1.0, 1.0, 1.0, 0.8",
                        "1.0, 0.5, 0.0, 1.0", "1.0, 1.0, 1.0, 0.6"):
            check(f"{label} carries no literal ({literal})", literal in src, False)


def main():
    tests = [
        test_both_paths_draw_the_same_square,
        test_an_unrotated_strip_gives_exactly_zero,
        test_both_draw_paths_call_the_shared_helper,
        test_the_drawing_primitives_manage_their_own_blend_state,
        test_one_palette_for_every_handle,
        test_the_local_copy_matches_the_real_one,
    ]

    for test in tests:
        try:
            test()
        except Exception:
            failures.append(f"{test.__name__} raised:\n{traceback.format_exc()}")

    version = bpy.app.version_string
    if failures:
        print(f"DRAWING {version} FAIL")
        for failure in failures:
            print(f"  - {failure}")
        sys.exit(1)

    print(f"DRAWING {version} PASS")


if __name__ == "__main__":
    main()
