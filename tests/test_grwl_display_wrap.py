"""Independent geography and opt-in native Tippecanoe wrap regressions."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import shapely
from shapely.geometry import MultiLineString

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('grwl_display_wrap', ROOT / 'datasets/grwl/validate_display_wrap.py')
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)
builder_spec = importlib.util.spec_from_file_location('grwl_display_builder', ROOT / 'datasets/grwl/build_display.py')
builder = importlib.util.module_from_spec(builder_spec)
builder_spec.loader.exec_module(builder)


def fixture():
    return [
        (1, [[178, 10], [-178, 10]]),
        (2, [[-178, 20], [178, 20]]),
        (3, [[-40, 0], [40, 0]]),
        (4, [[[170, 30], [179, 30]], [[-179, 31], [-170, 31]]]),
        (5, [[178, 40], [180, 40], [-178, 40]]),
        (6, [[-178, 45], [-180, 45], [178, 45]]),
    ]


class GeographyTests(unittest.TestCase):
    def test_unwrap_both_directions_and_preserve_non_crossing_long_line(self):
        central = shapely.box(-oracle.HALF / 2, -oracle.HALF, oracle.HALF / 2, oracle.HALF)
        for fid, coords in fixture()[:3]:
            geom = MultiLineString([coords])
            reference = oracle.wrapped_reference(shapely.to_wkb(geom))
            if fid in {1, 2}:
                self.assertEqual(len(reference.geoms), 2)
                self.assertTrue(reference.intersection(central).is_empty)
            else:
                self.assertEqual(len(reference.geoms), 1)
                self.assertGreater(reference.intersection(central).length, 1_000_000)

    def test_multipart_boundaries_never_become_a_dateline_edge(self):
        parts = fixture()[3][1]
        row = {'source_row': 4, 'geometry': shapely.to_wkb(MultiLineString(parts))}
        self.assertEqual(oracle.crossing_records([row]), [])
        reference = oracle.wrapped_reference(row['geometry'])
        self.assertEqual(len(reference.geoms), 2)
        self.assertLess(reference.length, 3_000_000)

    def test_builder_preserves_non_crossing_vertices_and_parts_exactly(self):
        geometry = MultiLineString([fixture()[2][1], *fixture()[3][1]])
        original = shapely.to_wkb(geometry)
        self.assertEqual(shapely.to_wkb(builder.split_dateline(geometry)), original)
        self.assertEqual(shapely.to_wkb(geometry), original)

    def test_builder_boundary_endpoints_and_zero_length_boundary_transition(self):
        for parts in [
            [[[178, 40], [180, 40], [-178, 40]]],
            [[[-178, 45], [-180, 45], [178, 45]]],
            [[[180, 50], [-180, 50], [-178, 50]]],
            [[[180, 50], [-180, 51], [-178, 51]]],
            [[[178, 55], [180, 55]]],
        ]:
            with self.subTest(parts=parts):
                geometry = MultiLineString(parts)
                split = builder.split_dateline(geometry)
                reference = oracle.wrapped_reference(shapely.to_wkb(geometry))
                got = oracle.wrapped_reference(shapely.to_wkb(split))
                self.assertLess(shapely.hausdorff_distance(reference, got), 1e-6)
                for part in split.geoms:
                    self.assertTrue(all(abs(b[0] - a[0]) <= 180 for a, b in zip(part.coords, list(part.coords)[1:])))

    def test_tiny_crossing_tail_quantized_to_boundary_point_uses_periodic_frame(self):
        for direction in (1, -1):
            with self.subTest(direction=direction):
                edge = direction * oracle.HALF
                reference = [shapely.LineString([(edge - direction * 1000, 10), (edge, 0)]),
                             shapely.LineString([(-edge, 0), (-edge + direction, .3)])]
                observed = [shapely.LineString([(edge - direction * 1000, 10), (edge, -4)]),
                            shapely.Point(-edge, -4)]
                components = [p for geom in observed for p in oracle.comparison_components(geom)]
                self.assertEqual(sum(p.geom_type == 'Point' for p in components), 1)
                # The old oracle discarded the boundary Point before comparing
                # canonical map copies; reproduce that exact failure first.
                old_line_only = [part for geom in observed for part in oracle.lines(geom)]
                canonical = shapely.hausdorff_distance(shapely.union_all(reference), shapely.union_all(old_line_only), densify=.25)
                self.assertGreater(canonical, oracle.WORLD / 2)
                anchor = edge - direction * 1000
                distance = shapely.hausdorff_distance(oracle.comparison_geometry(reference, anchor),
                                                       oracle.comparison_geometry(components, anchor), densify=.25)
                self.assertLess(distance, 5)


@unittest.skipUnless(os.environ.get('GRWL_NATIVE_WRAP_TESTS') == '1',
                     'native fixtures require explicit free-build-lane opt-in')
class NativeTippecanoeTests(unittest.TestCase):
    def test_tiny_eastward_and_westward_tail_at_z10(self):
        tip = shutil.which('tippecanoe') or '/opt/homebrew/bin/tippecanoe'
        lock = json.loads((ROOT / 'datasets/grwl/tippecanoe.lock.json').read_text())
        self.assertEqual(oracle.sha256(tip), lock['binary_sha256'])
        rows = [(11, MultiLineString([[[178.8, 67.99], [179.2, 67.9], [179.9884, 67.92553], [-179.999991, 67.92383]]])),
                (12, MultiLineString([[[-178.8, 66.99], [-179.2, 66.9], [-179.9884, 66.92553], [179.999991, 66.92383]]]))]
        with tempfile.TemporaryDirectory(prefix='grwl-native-tiny-tail-') as tmp:
            path = Path(tmp)
            features = [{'type': 'Feature', 'id': fid, 'properties': {'source_row': fid},
                         'geometry': shapely.geometry.mapping(builder.split_dateline(geometry))}
                        for fid, geometry in rows]
            (path / 'fixture.geojsonl').write_text(''.join(json.dumps(f) + '\n' for f in features))
            subprocess.run([tip, '--quiet', '--output', 'tiny.pmtiles', '--layer', 'grwl',
                            '--minimum-zoom', '10', '--maximum-zoom', '10', '--simplification', '2',
                            '--no-feature-limit', '--no-tile-size-limit', '--use-attribute-for-id', 'source_row',
                            '--detect-longitude-wraparound', 'fixture.geojsonl'], cwd=path, check=True,
                           env={**os.environ, 'TIPPECANOE_MAX_THREADS': '2'}, capture_output=True)
            archive = oracle.Archive(path / 'tiny.pmtiles')
            try:
                for fid, geometry in rows:
                    with self.subTest(fid=fid):
                        wkb = shapely.to_wkb(geometry)
                        reference = oracle.wrapped_reference(wkb)
                        expected, observed = [], []
                        tiles = oracle.reference_tiles(reference, 10)
                        for x, y in sorted(tiles):
                            tile_core = oracle.core(x, y, 10)
                            expected.extend(oracle.comparison_components(reference.intersection(tile_core)))
                            for actual in oracle.matching(archive, 10, x, y, fid):
                                observed.extend(oracle.comparison_components(actual.intersection(tile_core)))
                        self.assertGreater(sum(p.geom_type == 'Point' for p in observed), 0)
                        anchor = oracle.periodic_anchor(wkb)
                        self.assertIsNotNone(anchor)
                        distance = shapely.hausdorff_distance(oracle.comparison_geometry(expected, anchor),
                                                               oracle.comparison_geometry(observed, anchor), densify=.25)
                        self.assertLessEqual(distance, oracle.TOLERANCE)
                        for y in {y for _, y in tiles}:
                            self.assertEqual(oracle.matching(archive, 10, 512, y, fid), [])
            finally:
                archive.close()

    def test_flag_only_fails_and_explicit_split_corrects_both_directions(self):
        tip = shutil.which('tippecanoe') or '/opt/homebrew/bin/tippecanoe'
        self.assertTrue(Path(tip).is_file())
        lock = json.loads((ROOT / 'datasets/grwl/tippecanoe.lock.json').read_text())
        self.assertEqual(oracle.sha256(tip), lock['binary_sha256'])
        with tempfile.TemporaryDirectory(prefix='grwl-native-wrap-') as tmp:
            path = Path(tmp)
            source = path / 'fixture.geojsonl'
            for split in (False, True):
                features = []
                for fid, coords in fixture():
                    geometry = MultiLineString(coords if fid == 4 else [coords])
                    if split:
                        geometry = builder.split_dateline(geometry)
                    features.append({'type': 'Feature', 'id': fid, 'properties': {'source_row': fid},
                                     'geometry': shapely.geometry.mapping(geometry)})
                source.write_text(''.join(json.dumps(f) + '\n' for f in features))
                out = path / ('split.pmtiles' if split else 'flag-only.pmtiles')
                command = [tip, '--quiet', '--output', out.name, '--layer', 'grwl',
                           '--minimum-zoom', '0', '--maximum-zoom', '3', '--simplification', '2',
                           '--no-feature-limit', '--no-tile-size-limit', '--use-attribute-for-id', 'source_row']
                command.append('--detect-longitude-wraparound')
                subprocess.run(command + [source.name], check=True, cwd=path,
                               env={**os.environ, 'TIPPECANOE_MAX_THREADS': '2'}, capture_output=True)
                archive = oracle.Archive(out)
                central = shapely.box(-oracle.HALF / 2, -oracle.HALF, oracle.HALF / 2, oracle.HALF)
                try:
                    for z in range(4):
                        geometries = {fid: [] for fid, _ in fixture()}
                        for x in range(1 << z):
                            for y in range(1 << z):
                                tile = archive.tile(z, x, y)
                                if not tile:
                                    continue
                                layer = tile['grwl']
                                for feature in layer['features']:
                                    geom = oracle.decoded_geometry(feature, x, y, z, layer['extent'])
                                    geometries[feature['id']].append(geom.intersection(oracle.core(x, y, z)))
                        for fid in (1, 2, 5, 6):
                            union = shapely.union_all(geometries[fid])
                            self.assertFalse(union.is_empty)
                            if split:
                                self.assertLess(union.intersection(central).length, 1)
                                for west in (True, False):
                                    edge = shapely.box(-oracle.HALF, -oracle.HALF, -oracle.HALF + oracle.WORLD / 64, oracle.HALF) if west else shapely.box(oracle.HALF - oracle.WORLD / 64, -oracle.HALF, oracle.HALF, oracle.HALF)
                                    self.assertGreater(union.intersection(edge).length, 1)
                            elif fid in (1, 2):
                                self.assertGreater(union.intersection(central).length, 1_000_000)
                        self.assertGreater(shapely.union_all(geometries[3]).intersection(central).length, 1_000_000)
                        self.assertLess(shapely.union_all(geometries[4]).intersection(central).length, 1)
                finally:
                    archive.close()


if __name__ == '__main__':
    unittest.main()
