"""
Suppression tests: which handles a collapsed crop must stop offering.

The defect these exist for was found in a user's blend on 2026-09-04. A crop
collapsed to the 1px floor apply_crop_changes enforces leaves nine handles
sitting on three screen points 0-2px apart, and only three of the eight can
widen the crop again. Which one a click took was decided by aim the user could
not see, so the crop read as unrecoverable while being perfectly legal.

The rule under test is in crop_core: a handle is suppressed when another handle
within COLLISION_RADIUS can move on every axis it can and on at least one more.
See handle_mobility for why the handle a drag is holding is never the one
suppressed.

These are pure - they take screen positions as numbers - so no region, no
view2d and no GUI. They do need a strip only for the flip state, which the
mobility helper takes directly, so they need no Blender scene at all beyond
what the import costs.

    "/c/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b \
        --factory-startup --python tests/test_suppression.py
"""

import sys
import traceback
from pathlib import Path

import bpy

WORKSPACE = str(Path(__file__).resolve().parents[2])
if WORKSPACE not in sys.path:
    sys.path.insert(0, WORKSPACE)

from BL_EasyCrop.operators.crop_core import (  # noqa: E402
    COLLISION_RADIUS, HANDLE_RADIUS, handle_mobility, suppressed_handles)

# Handle indices, as crop_core numbers them.
BL, TL, TR, BR, EDGE_L, EDGE_T, EDGE_R, EDGE_B = range(8)
NAMES = {BL: "corner BL", TL: "corner TL", TR: "corner TR", BR: "corner BR",
         EDGE_L: "edge L", EDGE_T: "edge T", EDGE_R: "edge R",
         EDGE_B: "edge B"}

# error.blend, the file the defect came from: a 512x512 image strip cropped to
# (min_x, max_x, min_y, max_y) = (0, 511, 115, 0), so 1px of image survives.
ERROR_BLEND_CROP = (0, 511, 115, 0)
ERROR_BLEND_SIZE = (512, 512)

failures = []


def check(label, got, want):
    if got != want:
        failures.append(f"{label}: expected {want}, got {got}")


def spread(gap=200.0):
    """Eight handle positions far enough apart that nothing collides."""
    return [(0.0, 0.0), (0.0, gap), (gap, gap), (gap, 0.0),
            (0.0, gap / 2), (gap / 2, gap), (gap, gap / 2), (gap / 2, 0.0)]


def collapsed_x(height=640.0):
    """Positions for a crop collapsed on X, as error.blend has it.

    Corners land in two stacks 1px wide; the perpendicular edge midpoints land
    dead centre in those stacks, which is the whole trap. edge L and edge R sit
    2px apart halfway up.
    """
    return [(100.0, 0.0), (100.0, height), (101.0, height), (101.0, 0.0),
            (100.0, height / 2), (100.5, height), (102.0, height / 2),
            (100.5, 0.0)]


def only_pair(first, second, gap):
    """Positions where exactly two named handles are `gap` apart.

    Every other handle is parked on its own far-away spot. Reusing a `spread`
    slot for one of the pair is a trap: the first version of this file put the
    pair on top of corner BL's position and measured BL's domination instead of
    the collision under test.
    """
    positions = [(10000.0 + 500.0 * i, 10000.0) for i in range(8)]
    positions[first] = (0.0, 0.0)
    positions[second] = (gap, 0.0)
    return positions


def mobility(index, crop, size=ERROR_BLEND_SIZE, flips=(False, False)):
    return handle_mobility(index, crop, size[0], size[1], *flips)


def suppress(positions, crop, size=ERROR_BLEND_SIZE, flips=(False, False)):
    return suppressed_handles(positions, crop, size[0], size[1], *flips)


# --- the mobility predicate ---

def test_an_uncropped_strip_has_every_handle_mobile():
    """Corners move on both axes, edge midpoints on the one they drive."""
    crop = (0, 0, 0, 0)
    want = {BL: {"x", "y"}, TL: {"x", "y"}, TR: {"x", "y"}, BR: {"x", "y"},
            EDGE_L: {"x"}, EDGE_R: {"x"}, EDGE_T: {"y"}, EDGE_B: {"y"}}
    for index in range(8):
        check(f"uncropped mobility of {NAMES[index]}",
              set(mobility(index, crop)), want[index])


def test_error_blend_mobility_truth_table():
    """The measured case: min_x pinned at 0 with a limit of 0."""
    crop = ERROR_BLEND_CROP
    want = {BL: {"y"}, TL: {"y"}, TR: {"x", "y"}, BR: {"x", "y"},
            EDGE_L: set(), EDGE_T: {"y"}, EDGE_R: {"x"}, EDGE_B: {"y"}}
    for index in range(8):
        check(f"error.blend mobility of {NAMES[index]}",
              set(mobility(index, crop)), want[index])


def test_a_handle_at_its_limit_is_still_mobile():
    """It arrived there from 0, so it can go back - this is why a drag is safe.

    max_x = 511 with min_x = 0 sits exactly on the limit (512 - 0 - 1). If this
    read as immobile, the handle a drag had just pushed to the limit would
    vanish from under it.
    """
    check("max_x at its limit stays mobile",
          set(mobility(TR, (0, 511, 0, 0))), {"x", "y"})
    check("min_x at its limit stays mobile",
          set(mobility(TL, (511, 0, 0, 0))), {"x", "y"})


def test_only_pinned_against_both_stops_is_immobile():
    """Immobility needs value 0 *and* a limit of 0 or less."""
    check("min_x=0 with room above is mobile",
          set(mobility(EDGE_L, (0, 0, 0, 0))), {"x"})
    check("min_x=0 with the far side closed is immobile",
          set(mobility(EDGE_L, (0, 511, 0, 0))), set())
    check("min_x=0 with the far side past the end is immobile",
          set(mobility(EDGE_L, (0, 512, 0, 0))), set())


def test_edge_handles_never_report_the_perpendicular_axis():
    """The property the whole fix leans on: an edge drives one axis only."""
    for index, axis in ((EDGE_L, "x"), (EDGE_R, "x"),
                        (EDGE_T, "y"), (EDGE_B, "y")):
        got = set(mobility(index, (0, 0, 0, 0)))
        check(f"{NAMES[index]} drives only {axis}", got, {axis})


def test_mobility_survives_flips():
    """Mirroring swaps handles within an axis, so it cannot change which axis."""
    for flips in ((True, False), (False, True), (True, True)):
        for index, axis in ((EDGE_L, "x"), (EDGE_R, "x"),
                            (EDGE_T, "y"), (EDGE_B, "y")):
            got = set(mobility(index, (0, 0, 0, 0), flips=flips))
            check(f"{NAMES[index]} drives only {axis} under flips={flips}",
                  got, {axis})


# --- the suppression rule ---

def test_nothing_is_suppressed_when_nothing_collides():
    """A pinned handle that stands alone stays: it is still the right target."""
    check("spread out, error.blend crop",
          suppress(spread(), ERROR_BLEND_CROP), frozenset())


def test_error_blend_leaves_only_the_handles_that_recover():
    """The regression case. Replaying drags found TR, BR and edge R recover."""
    got = suppress(collapsed_x(), ERROR_BLEND_CROP)
    check("error.blend suppressed set", got, frozenset({BL, TL, EDGE_L,
                                                        EDGE_T, EDGE_B}))
    check("error.blend survivors", frozenset(range(8)) - got,
          frozenset({TR, BR, EDGE_R}))


def test_the_mirror_case_leaves_the_other_side():
    """Pinned at max_x instead: the left-hand handles must be the survivors."""
    crop = (511, 0, 115, 0)
    got = suppress(collapsed_x(), crop)
    check("mirrored survivors", frozenset(range(8)) - got,
          frozenset({BL, TL, EDGE_L}))


def test_a_mid_range_collapse_suppresses_only_the_useless_ones():
    """Collapsed but pinned to neither side: both sides recover, so both stay.

    Only the perpendicular edge midpoints go, because they offer no motion on
    the collapsed axis at all. This is the case where a user finds out which
    handle they have by moving it either way.
    """
    crop = (200, 311, 0, 0)
    got = suppress(collapsed_x(), crop)
    check("mid-range collapse suppressed", got, frozenset({EDGE_T, EDGE_B}))
    check("mid-range collapse keeps both sides",
          frozenset({BL, TL, TR, BR, EDGE_L, EDGE_R}) - got,
          frozenset({BL, TL, TR, BR, EDGE_L, EDGE_R}))


def test_both_axes_collapsed_leaves_one_handle_that_still_works():
    """The degenerate corner. Everything is dominated by the far corner."""
    crop = (0, 511, 0, 511)
    positions = [(100.0, 100.0)] * 8      # a single point
    got = suppress(positions, crop)
    survivors = frozenset(range(8)) - got
    check("double collapse survivors", survivors, frozenset({TR}))
    check("the survivor can move on both axes",
          set(mobility(TR, crop)), {"x", "y"})


def test_a_suppressor_is_never_itself_suppressed():
    """Every suppressed handle must be beaten by one that is still there."""
    for crop in ((0, 511, 115, 0), (511, 0, 115, 0), (0, 511, 0, 511),
                 (200, 311, 0, 0), (0, 0, 0, 0)):
        for positions in (collapsed_x(), [(100.0, 100.0)] * 8, spread()):
            got = suppress(positions, crop)
            check(f"crop {crop} leaves at least one handle",
                  len(got) < 8, True)


def test_the_collision_radius_is_a_screen_distance():
    """Same crop, two zooms: only the one where the squares touch suppresses.

    COLLISION_RADIUS is 2 * HANDLE_RADIUS, so handles exactly that far apart
    collide and handles further apart do not.
    """
    crop = ERROR_BLEND_CROP
    just_inside = COLLISION_RADIUS - 1.0
    just_outside = COLLISION_RADIUS + 1.0

    check("touching squares suppress the pinned one",
          suppress(only_pair(EDGE_L, EDGE_R, just_inside), crop),
          frozenset({EDGE_L}))
    check("separated squares suppress nothing",
          suppress(only_pair(EDGE_L, EDGE_R, just_outside), crop),
          frozenset())
    check("COLLISION_RADIUS is 2 * HANDLE_RADIUS",
          COLLISION_RADIUS, 2.0 * HANDLE_RADIUS)


def test_equal_mobility_never_suppresses():
    """Strict subset, not fewer-or-equal: a tie means either handle works."""
    crop = (200, 311, 0, 0)          # neither side pinned
    check("two equally mobile handles both survive",
          suppress(only_pair(EDGE_L, EDGE_R, 1.0), crop), frozenset())


TESTS = (
    test_an_uncropped_strip_has_every_handle_mobile,
    test_error_blend_mobility_truth_table,
    test_a_handle_at_its_limit_is_still_mobile,
    test_only_pinned_against_both_stops_is_immobile,
    test_edge_handles_never_report_the_perpendicular_axis,
    test_mobility_survives_flips,
    test_nothing_is_suppressed_when_nothing_collides,
    test_error_blend_leaves_only_the_handles_that_recover,
    test_the_mirror_case_leaves_the_other_side,
    test_a_mid_range_collapse_suppresses_only_the_useless_ones,
    test_both_axes_collapsed_leaves_one_handle_that_still_works,
    test_a_suppressor_is_never_itself_suppressed,
    test_the_collision_radius_is_a_screen_distance,
    test_equal_mobility_never_suppresses,
)


def main():
    version = bpy.app.version_string
    for test in TESTS:
        try:
            test()
        except Exception as exc:
            failures.append(
                f"{test.__name__} raised {type(exc).__name__}: {exc}")

    if failures:
        print(f"SUPPRESSION {version} FAIL")
        for line in failures:
            print(f"  - {line}")
        return 1

    print(f"SUPPRESSION {version} PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print(f"SUPPRESSION {bpy.app.version_string} ERROR")
        traceback.print_exc()
        sys.exit(1)
