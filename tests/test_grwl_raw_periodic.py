"""Focused tests for the raw display validator's compact periodic frame."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

import shapely
from pyproj import Transformer
from shapely.geometry import LineString, MultiLineString, Point

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('grwl_raw_periodic_oracle', ROOT/'datasets/grwl-raw/validate_display.py')
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)
wrap = oracle.load_wrap()
INVERSE = Transformer.from_crs(3857, 4326, always_xy=True, force_over=True)


def source_wkb(parts):
    return shapely.to_wkb(MultiLineString(parts))


def framed(wkb, reference, observed):
    anchor = oracle.source_frame_anchor(wkb, wrap, reference)
    expected = wrap.comparison_geometry(wrap.comparison_components(reference), anchor)
    actual_parts = [part for geom in observed for part in wrap.comparison_components(geom)]
    actual = wrap.comparison_geometry(actual_parts, anchor)
    return anchor, expected, actual


class SourceFrameAnchorTests(unittest.TestCase):
    def test_exact_positive_and_negative_seams_and_reversed_vertex_order(self):
        cases = [
            ('west seam forward', [(-180, 15), (-179.999, 15)], -wrap.HALF),
            ('east seam forward', [(180, 15), (179.999, 15)], wrap.HALF),
            ('west seam reversed', [(-179.999, 15), (-180, 15)], wrap.TRANSFORM.transform(-179.999, 15)[0]),
            ('east seam reversed', [(179.999, 15), (180, 15)], wrap.TRANSFORM.transform(179.999, 15)[0]),
        ]
        for label, coords, expected_anchor in cases:
            with self.subTest(label=label):
                wkb = source_wkb([coords])
                reference = wrap.wrapped_reference(wkb)
                anchor = oracle.source_frame_anchor(wkb, wrap, reference)
                self.assertAlmostEqual(anchor, expected_anchor, delta=1e-6)
                result = wrap.comparison_geometry(wrap.comparison_components(reference), anchor)
                self.assertLess(result.bounds[2]-result.bounds[0], 250)

    def test_half_metre_inside_both_seams_rounds_to_edge_and_order_stays_compact(self):
        side = wrap.WORLD/(1 << 12)
        pixel = side/4096
        for label, sign in [('west', -1), ('east', 1)]:
            seam_x = sign*wrap.HALF
            inside_x = seam_x-sign*0.5
            next_x = seam_x-sign*10.5
            seam_lon, lat = INVERSE.transform(inside_x, 11_000_000)
            next_lon, next_lat = INVERSE.transform(next_x, 11_000_000)
            coords = [(seam_lon, lat), (next_lon, next_lat)]
            for order in ('source-first', 'reversed'):
                test_coords = coords if order == 'source-first' else list(reversed(coords))
                with self.subTest(seam=label, order=order):
                    wkb = source_wkb([test_coords])
                    reference = wrap.wrapped_reference(wkb)
                    anchor = oracle.source_frame_anchor(wkb, wrap, reference)
                    first_x = wrap.TRANSFORM.transform(*test_coords[0])[0]
                    self.assertAlmostEqual(anchor, first_x, delta=1e-6)
                    local_pixel = ((inside_x+wrap.HALF)/pixel if sign < 0
                                   else 4096-(wrap.HALF-inside_x)/pixel)
                    self.assertEqual(round(local_pixel), 0 if sign < 0 else 4096)
                    result = wrap.comparison_geometry(wrap.comparison_components(reference), anchor)
                    self.assertLess(result.bounds[2]-result.bounds[0], 20)

    def test_true_crossings_in_both_directions_anchor_to_first_source_vertex(self):
        for coords in [[(179.999, 25), (-179.999, 25)], [(-179.999, 25), (179.999, 25)]]:
            with self.subTest(coords=coords):
                wkb = source_wkb([coords])
                reference = wrap.wrapped_reference(wkb)
                anchor = oracle.source_frame_anchor(wkb, wrap, reference)
                expected = wrap.TRANSFORM.transform(*coords[0])[0]
                self.assertAlmostEqual(anchor, expected, delta=1e-6)
                self.assertEqual(len(reference.geoms), 2)
                compact = wrap.comparison_geometry(wrap.comparison_components(reference), anchor)
                self.assertLess(compact.bounds[2]-compact.bounds[0], 300)
                self.assertGreater(compact.length, 200)

    def test_compact_multipart_keeps_each_component_without_joining_remote_parts(self):
        parts = [[(179.7, 10), (-179.8, 10)], [(-179.6, 11), (-179.5, 11)],
                 [(179.4, 12), (179.5, 12)]]
        wkb = source_wkb(parts)
        reference = wrap.wrapped_reference(wkb)
        anchor = oracle.source_frame_anchor(wkb, wrap, reference)
        self.assertAlmostEqual(anchor, wrap.TRANSFORM.transform(*parts[0][0])[0], delta=1e-6)
        ordered = wrap.comparison_components(reference)
        self.assertEqual(len(ordered), 4)
        ordered_lengths = [part.length for part in ordered]
        self.assertGreater(ordered_lengths[0], ordered_lengths[1])
        self.assertGreater(ordered_lengths[1], ordered_lengths[2])
        self.assertAlmostEqual(ordered_lengths[2], ordered_lengths[3], delta=1e-6)
        compact = wrap.comparison_geometry(ordered, anchor)
        self.assertEqual(compact.geom_type, 'MultiLineString')
        self.assertEqual(len(compact.geoms), 4)
        self.assertLess(compact.bounds[2]-compact.bounds[0], wrap.WORLD/2)
        lengths = sorted(round(part.length, 6) for part in compact.geoms)
        self.assertEqual(lengths, sorted(round(part.length, 6) for part in wrap.comparison_components(reference)))

    def test_opposite_edge_core_point_is_retained_and_periodically_matched(self):
        lat = 71.19728974037749
        coords = [(-180, lat), (-179.99929548238572, 71.1973010125156)]
        wkb = source_wkb([coords])
        reference = wrap.wrapped_reference(wkb)
        x_start, y_start = wrap.TRANSFORM.transform(*coords[0])
        side = wrap.WORLD/(1 << 12)
        pixel = side/4096
        # MVT rounding of this source vertex puts it at pixel 2718 in tile y=875.
        decoded_y = wrap.HALF-(875*side+2718*pixel)
        decoded_edgepoint = wrap.decoded_geometry(
            {'geometry': {'type': 'Point', 'coordinates': [4096, 2718]}}, 4095, 875, 12, 4096)
        self.assertEqual(decoded_edgepoint.geom_type, 'Point')
        self.assertAlmostEqual(decoded_edgepoint.x, wrap.HALF, delta=1e-6)
        self.assertAlmostEqual(decoded_edgepoint.y, decoded_y, delta=1e-6)
        west_core, east_core = wrap.core(0, 875, 12), wrap.core(4095, 875, 12)
        expected_parts = [part for core in (west_core, east_core)
                          for part in wrap.comparison_components(reference.intersection(core))]
        observed_parts = [part for core in (west_core, east_core)
                          for geom in (reference, decoded_edgepoint)
                          for part in wrap.comparison_components(geom.intersection(core))]
        self.assertEqual(sum(part.geom_type == 'Point' for part in observed_parts), 1)
        canonical = shapely.hausdorff_distance(shapely.union_all(expected_parts), shapely.union_all(observed_parts))
        self.assertAlmostEqual(canonical, 40074938.259, delta=0.01)
        anchor = oracle.source_frame_anchor(wkb, wrap, reference)
        expected = wrap.comparison_geometry(expected_parts, anchor)
        actual = wrap.comparison_geometry(observed_parts, anchor)
        periodic = shapely.hausdorff_distance(expected, actual)
        self.assertAlmostEqual(abs(decoded_y-y_start), 1.105104, delta=0.00001)
        self.assertAlmostEqual(periodic, 1.105104, delta=0.00001)
        self.assertEqual(anchor, -wrap.HALF)
        self.assertEqual(sum(part.geom_type == 'Point' for part in wrap.comparison_components(decoded_edgepoint)), 1)

    def test_missing_actual_line_and_remote_multipart_still_exceed_30m(self):
        line_wkb = source_wkb([[(10, 10), (10.1, 10)]])
        line_reference = wrap.wrapped_reference(line_wkb)
        missing_line = Point(line_reference.geoms[0].coords[0])
        _, expected, actual = framed(line_wkb, line_reference, [missing_line])
        self.assertGreater(shapely.hausdorff_distance(expected, actual), 30)

        multipart_cases = [
            ('local first', [[(179.7, 20), (179.8, 20)], [(-160, 30), (-159.9, 30)]], 0),
            ('remote first', [[(-160, 30), (-159.9, 30)], [(179.7, 20), (179.8, 20)]], 1),
            ('component and vertex order reversed', [[(-159.9, 30), (-160, 30)],
                                                        [(179.8, 20), (179.7, 20)]], 1),
        ]
        for label, parts, local_index in multipart_cases:
            with self.subTest(order=label):
                multipart_wkb = source_wkb(parts)
                multipart_reference = wrap.wrapped_reference(multipart_wkb)
                self.assertEqual(len(multipart_reference.geoms), 2)
                _, expected, actual = framed(multipart_wkb, multipart_reference,
                                             [multipart_reference.geoms[local_index]])
                self.assertGreater(shapely.hausdorff_distance(expected, actual), 30)

    def test_genuine_central_world_chord_clipped_across_cores_fails_closed(self):
        source = source_wkb([[(-135, 0), (135, 0)]])
        central_chord = LineString([(-0.75*wrap.HALF, 0), (0.75*wrap.HALF, 0)])
        tiles = wrap.bbox_tiles(central_chord.bounds, 2)
        clipped = [central_chord.intersection(wrap.core(x, y, 2)) for x, y in tiles]
        clipped_lines = [part for geom in clipped for part in wrap.comparison_components(geom)]
        self.assertGreater(len(clipped_lines), 1)
        with self.assertRaisesRegex(ValueError, 'spans half a world or more'):
            oracle.source_frame_anchor(source, wrap, central_chord)

    def test_wrong_observed_central_world_chord_cannot_match_compact_seam_source(self):
        source = source_wkb([[(179.99, 10), (179.999, 10)]])
        reference = wrap.wrapped_reference(source)
        self.assertLess(reference.bounds[2]-reference.bounds[0], 10_000)
        y = wrap.TRANSFORM.transform(179.995, 10)[1]
        wrong_chord = LineString([(-0.75*wrap.HALF, y), (0.75*wrap.HALF, y)])
        tiles = wrap.bbox_tiles(wrong_chord.bounds, 2)
        clipped = [part for x, ty in tiles
                   for part in wrap.comparison_components(wrong_chord.intersection(wrap.core(x, ty, 2)))]
        self.assertGreater(len(clipped), 1)
        anchor, expected, actual = framed(source, reference, clipped)
        self.assertGreater(abs(anchor), wrap.HALF*0.99)
        self.assertGreater(shapely.hausdorff_distance(expected, actual), 1_000_000)

    def test_half_world_and_extensive_multipart_frames_fail_closed(self):
        half_world_wkb = source_wkb([[(-90, 0), (90, 0)]])
        half_world_ref = wrap.wrapped_reference(half_world_wkb)
        self.assertAlmostEqual(half_world_ref.bounds[2]-half_world_ref.bounds[0], wrap.WORLD/2, delta=1e-6)
        with self.assertRaisesRegex(ValueError, 'spans half a world or more'):
            oracle.source_frame_anchor(half_world_wkb, wrap, half_world_ref)

        extensive_wkb = source_wkb([[(0, 0), (1, 0)], [(180, 10), (179, 10)]])
        extensive_ref = wrap.wrapped_reference(extensive_wkb)
        with self.assertRaisesRegex(ValueError, 'spans half a world or more'):
            oracle.source_frame_anchor(extensive_wkb, wrap, extensive_ref)


if __name__ == '__main__':
    unittest.main()
