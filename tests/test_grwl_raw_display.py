"""Focused tests for independent GRWL raw display accounting and geography."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

import mapbox_vector_tile
import pyarrow as pa
import pyarrow.parquet as pq
import shapely
from shapely.geometry import MultiLineString
from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import Writer

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


oracle = module('grwl_raw_display_oracle', ROOT/'datasets/grwl-raw/validate_display.py')
builder = module('grwl_raw_display_builder', ROOT/'datasets/grwl-raw/build_display.py')
wrap = oracle.load_wrap()


def row(tile, number, width, parts):
    geometry = MultiLineString(parts)
    xmin, ymin, xmax, ymax = geometry.bounds
    return {'source_tile': tile, 'source_row': number,
            'feature_id': (oracle.tile_code(tile) << 32) | number,
            'width_m': width, 'width_valid': width is not None and width > 0 and width != 1,
            'bbox': {'xmin': xmin, 'ymin': ymin, 'xmax': xmax, 'ymax': ymax},
            'geometry': shapely.to_wkb(geometry)}


def parquet_file(path, rows, row_group_size=2):
    schema = pa.schema([
        ('source_tile', pa.string()), ('source_row', pa.uint32()), ('feature_id', pa.uint64()),
        ('width_m', pa.int64()), ('width_valid', pa.bool_()),
        ('bbox', pa.struct([(key, pa.float64()) for key in oracle.BBOX])), ('geometry', pa.binary()),
    ])
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path,
                   compression='zstd', row_group_size=row_group_size, write_statistics=True)


def pmtiles_file(path, rows, omit=None, wrong_width=False, stray_geometry=False):
    omit = set() if omit is None else set(omit)
    project = lambda lon, lat: wrap.TRANSFORM.transform(lon, lat)
    x, y = next(iter(wrap.bbox_tiles((*project(10.0, 10.0), *project(10.0, 10.0)), 12)))
    side = wrap.WORLD / (1 << 12)

    def pixel(lon, lat):
        merc_x, merc_y = project(lon, lat)
        return ((merc_x + wrap.HALF) / side - x) * 4096, ((wrap.HALF-merc_y) / side - y) * 4096

    features = []
    for source in rows:
        if source['feature_id'] in omit:
            continue
        feature = builder.display_feature(source)
        if wrong_width:
            feature['properties']['width_m'] = 999
        features.append(feature)
    tile = mapbox_vector_tile.encode({'name': oracle.LAYER, 'features': features},
                                     default_options={'y_coord_down': True, 'transformer': pixel})
    empty = mapbox_vector_tile.encode({'name': oracle.LAYER, 'features': []})
    with path.open('wb') as stream:
        writer = Writer(stream)
        writer.write_tile(zxy_to_tileid(8, 0, 0), empty)
        writer.write_tile(zxy_to_tileid(12, x, y), tile)
        if stray_geometry:
            stray = builder.display_feature(rows[0])
            stray['geometry'] = {'type': 'LineString', 'coordinates': [[100, 100], [200, 200]]}
            raw = mapbox_vector_tile.encode({'name': oracle.LAYER, 'features': [stray]},
                                            default_options={'y_coord_down': True})
            writer.write_tile(zxy_to_tileid(12, x+1, y), raw)
        writer.finalize({'tile_compression': Compression.NONE, 'tile_type': TileType.MVT}, {})
    return x, y


class DisplayOracleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.rows = [row('NI15', 1, 1, [[(10.001, 10.001), (10.003, 10.003)]]),
                     row('NI15', 2, 17, [[(10.004, 10.004), (10.006, 10.006)]])]
        self.parquet = self.base/'source.parquet'
        parquet_file(self.parquet, self.rows)
        empty_tiles = [{'tile': f'AA{i:02d}', 'records': 0, 'parts': 0} for i in range(1, 10)]
        empty_evidence = [{'tile': tile['tile'], 'source_rows': 0, 'parts': 0,
                           'first_records': [], 'longest_parts': []} for tile in empty_tiles]
        self.manifest = self.base/'manifest.json'
        self.manifest.write_text(json.dumps({'rows': 2, 'parquet_sha256': oracle.sha256(self.parquet),
                                              'tiles': empty_tiles+[{'tile': 'NI15', 'records': 2, 'parts': 2}]}))
        geod = oracle.Geod(ellps='WGS84')
        longest = []
        for source_row in self.rows:
            coordinates = shapely.from_wkb(source_row['geometry']).geoms[0].coords
            xy = list(coordinates)
            longest.append({'source_tile': 'NI15', 'source_row': source_row['source_row'],
                            'feature_id': source_row['feature_id'], 'part': 1,
                            'length_m': abs(geod.line_length([p[0] for p in xy], [p[1] for p in xy]))})
        longest.sort(key=lambda item: (-item['length_m'], item['source_row'], item['part']))
        self.fidelity = self.base/'fidelity.json'
        self.fidelity.write_text(json.dumps({'status': 'passed', 'parquet_sha256': oracle.sha256(self.parquet),
                                              'manifest_sha256': oracle.sha256(self.manifest),
                                              'progress': {'source_rows': 2, 'parts': 2,
                                                           'tiles_completed': [x['tile'] for x in empty_tiles]+['NI15']},
                                              'sample_policy': {'kind': 'global_controls',
                                                                'first_records_per_tile': 8,
                                                                'longest_parts_per_tile': 8},
                                              'tiles': empty_evidence+[{'tile': 'NI15', 'source_rows': 2, 'parts': 2,
                                                         'first_records': [{'source_tile': 'NI15',
                                                                            'source_row': i,
                                                                            'feature_id': r['feature_id']}
                                                                           for i, r in enumerate(self.rows, 1)],
                                                         'longest_parts': longest}]}))
        self.pmtiles = self.base/'display.pmtiles'
        self.report = self.base/'report.json'

    def tearDown(self):
        self.temp.cleanup()

    def run_oracle(self):
        return oracle.validate(self.parquet, self.manifest, self.fidelity, self.pmtiles, self.report)

    def test_complete_native_id_attribute_and_geometry_accounting(self):
        pmtiles_file(self.pmtiles, self.rows)
        result = self.run_oracle()
        self.assertEqual(result['status'], 'passed', result['errors'])
        self.assertEqual(result['maxzoom_unique_ids'], 2)
        self.assertEqual(result['maxzoom_attribute_occurrences_checked'], 2)
        self.assertEqual(result['maxzoom_missing_ids'], 0)
        self.assertEqual(result['dateline_bbox_candidate_feature_ids'], [])
        self.assertEqual(result['validator_sha256'], oracle.sha256(Path(oracle.__file__)))
        self.assertEqual(len(result['frozen_geometry_samples']), 2)
        self.assertEqual(len(result['frozen_sample_counts']), 10)
        self.assertTrue(all(x['validated_first_records'] == x['validated_longest_parts'] == 0
                            for x in result['frozen_sample_counts'][:9]))
        self.assertFalse(result['longest_part_rank_independently_recomputed'])
        self.assertEqual(json.loads(self.report.read_text()), result)

    def test_attribute_mismatch_is_failure_even_when_id_is_present(self):
        pmtiles_file(self.pmtiles, self.rows, wrong_width=True)
        result = self.run_oracle()
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(any('attribute mismatch' in error for error in result['errors']))
        self.assertEqual(result['maxzoom_unique_ids'], 2)

    def test_missing_noncollapsed_id_is_enumerated_and_fails(self):
        pmtiles_file(self.pmtiles, self.rows, omit={self.rows[1]['feature_id']})
        result = self.run_oracle()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['maxzoom_missing_classification'], {'unexpected_loss': 1})
        records = [json.loads(line) for line in self.report.with_name('report.maxzoom-missing.jsonl').read_text().splitlines()]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['id'], self.rows[1]['feature_id'])
        self.assertEqual(records[0]['cause'], 'unexpected_loss')
        self.assertGreater(records[0]['source_geodesic_length_m'], 30)
        self.assertEqual(len(records[0]['parts'][0]['rounded_grid_xy']), 2)

    def test_stray_geometry_for_valid_sampled_id_fails_union_comparison(self):
        pmtiles_file(self.pmtiles, self.rows, stray_geometry=True)
        result = self.run_oracle()
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(any('frozen sample geometry' in error for error in result['errors']))

    def test_source_selected_seam_supplement_keeps_crossings_and_prunes_other_groups(self):
        margin = 30 / wrap.HALF * 180
        samples = [
            row('NI15', 1, 1, [[(179.9, 0), (-179.9, 0)]]),
            row('NI15', 2, 1, [[(-180, 0), (-179.99, 0)]]),
            row('NI15', 3, 1, [[(-180+margin/2, 0), (-180+margin*2, 0)]]),
            row('NI15', 4, 1, [[(180-margin*2, 0), (180-margin/2, 0)]]),
            row('NI15', 5, 1, [[(-180+margin*2, 0), (-180+margin*3, 0)]]),
            row('NI15', 6, 1, [[(180-margin*3, 0), (180-margin*2, 0)]]),
            row('NI15', 7, 1, [[(10, 0), (10.1, 0)]]),
        ]
        path = self.base/'seam-candidates.parquet'
        parquet_file(path, samples, row_group_size=1)
        index = oracle.SourceIndex(path, {'rows': len(samples), 'tiles': [{'tile': 'NI15', 'records': len(samples)}]})
        self.assertEqual(set(index.dateline_candidates()), {samples[0]['feature_id']})
        self.assertEqual(set(index.dateline_candidates(margin)), {r['feature_id'] for r in samples[:4]})

    def test_row_group_index_and_id_order_guards(self):
        extra = row('NI16', 1, None, [[(10.01, 10.01), (10.02, 10.02)]])
        path = self.base/'two-tiles.parquet'
        parquet_file(path, self.rows+[extra], row_group_size=2)
        index = oracle.SourceIndex(path, {'rows': 3, 'tiles': [
            {'tile': 'NI15', 'records': 2}, {'tile': 'NI16', 'records': 1}]})
        self.assertEqual(index.locate(extra['feature_id']), (1, 0, 1, 0))
        self.assertIsNone(index.locate((oracle.tile_code('NI16') << 32) | 2))
        self.assertEqual(index.attrs(1)['width_m'], [None])
        with self.assertRaisesRegex(ValueError, 'mixes source tiles'):
            oracle.SourceIndex(path, {'rows': 3, 'tiles': [
                {'tile': 'NI15', 'records': 1}, {'tile': 'NI16', 'records': 2}]})

    def test_existing_validation_evidence_cannot_be_overwritten(self):
        pmtiles_file(self.pmtiles, self.rows)
        self.run_oracle()
        original = self.report.read_bytes()
        with self.assertRaisesRegex(FileExistsError, "overwrite"):
            self.run_oracle()
        self.assertEqual(self.report.read_bytes(), original)

    def test_fidelity_sha_binding_is_required(self):
        pmtiles_file(self.pmtiles, self.rows)
        fidelity = json.loads(self.fidelity.read_text())
        fidelity['parquet_sha256'] = '0'*64
        self.fidelity.write_text(json.dumps(fidelity))
        with self.assertRaisesRegex(ValueError, 'binding'):
            self.run_oracle()

    def test_empty_and_truncated_sample_arrays_fail_before_display_scan(self):
        original = self.fidelity.read_text()
        for change in ('empty', 'truncated'):
            with self.subTest(change=change):
                fidelity = json.loads(original)
                if change == 'empty':
                    fidelity['tiles'][-1]['first_records'] = []
                    fidelity['tiles'][-1]['longest_parts'] = []
                else:
                    fidelity['tiles'][-1]['first_records'].pop()
                self.fidelity.write_text(json.dumps(fidelity))
                with self.assertRaisesRegex(ValueError, 'sample count'):
                    self.run_oracle()

    def test_replaced_first_id_and_wrong_policy_fail_preflight(self):
        original = json.loads(self.fidelity.read_text())
        replaced = json.loads(json.dumps(original))
        replaced['tiles'][-1]['first_records'][0]['feature_id'] = self.rows[1]['feature_id']
        self.fidelity.write_text(json.dumps(replaced))
        with self.assertRaisesRegex(ValueError, 'feature ID does not encode'):
            self.run_oracle()

        wrong_policy = json.loads(json.dumps(original))
        wrong_policy['sample_policy']['first_records_per_tile'] = 32
        self.fidelity.write_text(json.dumps(wrong_policy))
        with self.assertRaisesRegex(ValueError, 'sample policy'):
            self.run_oracle()

    def test_forged_part_count_cannot_reduce_expected_longest_sample_count(self):
        fidelity = json.loads(self.fidelity.read_text())
        fidelity['tiles'][-1]['parts'] = 1
        fidelity['tiles'][-1]['longest_parts'].pop()
        fidelity['progress']['parts'] = 1
        self.fidelity.write_text(json.dumps(fidelity))
        with self.assertRaisesRegex(ValueError, 'part count differs from manifest'):
            self.run_oracle()

    def test_longest_samples_must_follow_length_and_tie_order(self):
        fidelity = json.loads(self.fidelity.read_text())
        fidelity['tiles'][-1]['longest_parts'].reverse()
        self.fidelity.write_text(json.dumps(fidelity))
        with self.assertRaisesRegex(ValueError, 'descending length and deterministic tie order'):
            self.run_oracle()

    def test_all_empty_source_cannot_claim_geometry_pass(self):
        empty_parquet = self.base/'empty.parquet'
        parquet_file(empty_parquet, [])
        empty_manifest = self.base/'empty-manifest.json'
        empty_manifest.write_text(json.dumps({'rows': 0, 'parquet_sha256': oracle.sha256(empty_parquet),
                                               'tiles': [{'tile': 'NI14', 'records': 0, 'parts': 0}]}))
        empty_fidelity = self.base/'empty-fidelity.json'
        empty_fidelity.write_text(json.dumps({
            'status': 'passed', 'parquet_sha256': oracle.sha256(empty_parquet),
            'manifest_sha256': oracle.sha256(empty_manifest), 'progress': {'source_rows': 0, 'parts': 0},
            'sample_policy': {'kind': 'global_controls', 'first_records_per_tile': 8,
                              'longest_parts_per_tile': 8},
            'tiles': [{'tile': 'NI14', 'source_rows': 0, 'parts': 0,
                       'first_records': [], 'longest_parts': []}],
        }))
        with self.assertRaisesRegex(ValueError, 'no frozen geometry samples'):
            oracle.validate(empty_parquet, empty_manifest, empty_fidelity,
                            self.base/'nonexistent.pmtiles', self.base/'empty-report.json')
        self.assertFalse((self.base/'empty-report.json').exists())

    def test_both_dateline_directions_tiny_tails_and_separated_parts(self):
        cases = [
            [[(178.8, 40), (179.999999, 40)], [(-179.999999, 40), (-178.8, 40)]],
            [[(178.8, 40), (-179.999999, 40)]],
            [[(-178.8, 40), (179.999999, 40)]],
        ]
        for parts in cases:
            with self.subTest(parts=parts):
                source = row('NI15', 1, 1, parts)
                display = builder.display_feature(source)
                result = wrap.wrapped_reference(shapely.to_wkb(shapely.geometry.shape(display['geometry'])))
                expected = wrap.wrapped_reference(source['geometry'])
                self.assertLess(shapely.hausdorff_distance(result, expected), 1e-6)
        left = row('NI15', 1, 17, [[(10, 0), (10.1, 0)]])
        right = row('NI15', 2, 20, [[(20, 0), (20.1, 0)]])
        self.assertNotEqual(left['feature_id'], right['feature_id'])
        self.assertEqual(len(shapely.from_wkb(left['geometry']).geoms), 1)
        self.assertEqual(len(shapely.from_wkb(right['geometry']).geoms), 1)

    def test_zero_length_and_grid_collapse_are_separate_exceptions(self):
        zero = row('NI15', 1, 1, [[(10, 10), (10, 10)]])
        short = row('NI15', 2, 1, [[(10, 10), (10+1e-8, 10)]])
        ordinary = self.rows[0]
        self.assertEqual(oracle.classify_geometry(zero['geometry'], wrap), 'zero_length')
        self.assertEqual(oracle.classify_geometry(short['geometry'], wrap), 'quantization_collapse')
        self.assertEqual(oracle.classify_geometry(ordinary['geometry'], wrap), 'unexpected_loss')


if __name__ == '__main__':
    unittest.main()
