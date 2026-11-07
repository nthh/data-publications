"""Frozen semantic mutations and resource refusals for compact GRWL detail."""
from __future__ import annotations
import copy
import gzip
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mapbox_vector_tile.Mapbox import vector_tile_pb2
from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import Writer

ROOT = Path(__file__).resolve().parents[1]


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


oracle = module('grwl_repack_oracle', 'datasets/grwl-raw/compare_detail.py')
builder = module('grwl_repack_builder', 'datasets/grwl-raw/repack_detail.py')


def tile(source=True, *, duplicate=False):
    value = vector_tile_pb2.tile()
    layer = value.layers.add(name='grwl_raw', version=2, extent=4096)
    feature = layer.features.add(id=123456789012345, type=2)
    feature.geometry.extend([9, 20, 40, 10, 4, 6])
    fields = [('width_m', 'int_value', 73), ('width_valid', 'bool_value', True)]
    if source:
        fields += [(key, 'double_value', 1.25 + i) for i, key in enumerate(builder.DROP)]
    for key, kind, val in fields:
        feature.tags.extend([len(layer.keys), len(layer.values)])
        layer.keys.append(key)
        setattr(layer.values.add(), kind, val)
    if duplicate:
        layer.features.add().CopyFrom(feature)
    return value


def archive(path, tiles):
    with path.open('wb') as stream:
        writer = Writer(stream)
        for xyz, value in sorted(tiles, key=lambda t: zxy_to_tileid(*t[0])):
            writer.write_tile(zxy_to_tileid(*xyz), gzip.compress(value.SerializeToString(), mtime=0))
        writer.finalize({'tile_compression': Compression.GZIP, 'tile_type': TileType.MVT}, {})


class DetailComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / 'source.pmtiles'
        self.candidate = self.base / 'candidate.pmtiles'
        archive(self.source, [((8, 0, 0), tile()), ((12, 0, 0), tile(duplicate=True))])

    def valid_candidate(self):
        archive(self.candidate, [((8, 0, 0), tile(False)), ((12, 0, 0), tile(False, duplicate=True))])

    def test_exact_semantics_with_bbox_removal_and_multiplicity(self):
        self.valid_candidate()
        result = oracle.compare(self.source, self.candidate)
        self.assertEqual(result['detail_tiles'], 2)
        self.assertEqual(result['detail_features'], 3)

    def test_mutations_are_refused(self):
        mutations = {
            'changed_id': lambda t: setattr(t.layers[0].features[0], 'id', 9),
            'dropped_id': lambda t: t.layers[0].features[0].ClearField('id'),
            'geometry': lambda t: t.layers[0].features[0].geometry.__setitem__(4, 6),
            'width': lambda t: setattr(t.layers[0].values[0], 'int_value', 74),
            'width_type': lambda t: (t.layers[0].values[0].ClearField('int_value'), setattr(t.layers[0].values[0], 'uint_value', 73)),
            'valid': lambda t: setattr(t.layers[0].values[1], 'bool_value', False),
            'unexpected_field': lambda t: t.layers[0].keys.append('invented'),
            'bad_tags': lambda t: t.layers[0].features[0].tags.append(100),
            'duplicate_property': lambda t: t.layers[0].features[0].tags.extend([0, 0]),
            'wrong_extent': lambda t: setattr(t.layers[0], 'extent', 8192),
            'wrong_layer': lambda t: setattr(t.layers[0], 'name', 'invented'),
            'wrong_type': lambda t: setattr(t.layers[0].features[0], 'type', 1),
            'dropped_feature': lambda t: t.layers[0].ClearField('features'),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                changed = tile(False)
                mutate(changed)
                archive(self.candidate, [((8, 0, 0), changed), ((12, 0, 0), tile(False, duplicate=True))])
                with self.assertRaises(ValueError):
                    oracle.compare(self.source, self.candidate)

    def test_missing_extra_tiles_and_multiplicity_refused(self):
        choices = [[], [((8, 0, 0), tile(False))],
                   [((8, 0, 0), tile(False)), ((12, 0, 0), tile(False))],
                   [((8, 0, 0), tile(False)), ((12, 0, 0), tile(False, duplicate=True)), ((12, 1, 0), tile(False))]]
        for items in choices:
            if not items:
                continue  # Writer cannot create an empty archive.
            archive(self.candidate, items)
            with self.assertRaises(ValueError):
                oracle.compare(self.source, self.candidate)

    def test_dictionary_and_feature_order_do_not_matter(self):
        original = tile(False, duplicate=True)
        changed = copy.deepcopy(original)
        layer = changed.layers[0]
        layer.keys.reverse()
        layer.values.reverse()
        for feature in layer.features:
            feature.tags[:] = [1, 1, 0, 0]
        self.assertEqual(oracle.signature(original.SerializeToString(), source=False),
                         oracle.signature(changed.SerializeToString(), source=False))

    def test_report_bound_and_immutable_including_failures(self):
        self.valid_candidate()
        report = self.base / 'report.json'
        result = oracle.run(self.source, self.candidate, report, source_sha256=oracle.sha256(self.source))
        self.assertEqual(result['status'], 'passed')
        with self.assertRaises(FileExistsError):
            oracle.run(self.source, self.candidate, report, source_sha256=oracle.sha256(self.source))
        failed = self.base / 'failed.json'
        with self.assertRaises(ValueError):
            oracle.run(self.source, self.candidate, failed, source_sha256='bad')
        self.assertEqual(json.loads(failed.read_text())['status'], 'failed')

    def test_unexpected_overview_layer_refused(self):
        overview = tile(False)
        archive(self.candidate, [((0, 0, 0), overview), ((8, 0, 0), tile(False)), ((12, 0, 0), tile(False, duplicate=True))])
        with self.assertRaises(ValueError):
            oracle.compare(self.source, self.candidate, allow_overview=True)
        overview.layers[0].name = 'grwl_overview'
        archive(self.candidate, [((0, 0, 0), overview), ((8, 0, 0), tile(False)), ((12, 0, 0), tile(False, duplicate=True))])
        self.assertEqual(oracle.compare(self.source, self.candidate, allow_overview=True)['overview_tiles'], 1)

    @unittest.skipUnless(os.environ.get('GRWL_NATIVE_TEST') == '1', 'Explicit opt-in to tiny pinned native fixture')
    def test_tiny_native_repack(self):
        output = self.base / 'native'
        builder.build(self.source, output, self.base, builder.sha256(self.source), maximum_gib=4)
        result = oracle.compare(self.source, output / 'assets/grwl-raw.pmtiles')
        self.assertEqual(result['detail_features'], 3)


class ResourceRefusalTests(unittest.TestCase):
    def test_no_skip_drop_or_rescale_flags(self):
        command = builder.command(Path('/source.pmtiles'))
        self.assertIn('--no-tile-size-limit', command)
        self.assertEqual(command.count('-x'), 4)
        self.assertNotIn('-f', command)
        self.assertNotIn('-z', command)
        self.assertNotIn('-Z', command)
        self.assertEqual(command[-1], 'inputs/detail.pmtiles')
        self.assertNotIn('/source.pmtiles', command)
        self.assertEqual(builder.command(Path('/other/path'), Path('/another/overview'))[-2:],
                         ['inputs/detail.pmtiles', 'inputs/overview.pmtiles'])

    def test_disk_start_stop_and_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'new'
            class Disk:
                free = 39 * builder.GIB
            with patch.object(builder.shutil, 'disk_usage', return_value=Disk()):
                with self.assertRaises(RuntimeError):
                    builder.resource_check(output, start=True)
                Disk.free = 14 * builder.GIB
                with self.assertRaises(RuntimeError):
                    builder.resource_check(output)
                Disk.free = 45 * builder.GIB
                with self.assertRaises(RuntimeError):
                    builder.resource_check(output, 70 * builder.GIB)

    def test_immutable_and_checksum_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / 'source'
            source.write_bytes(b'fixture')
            with self.assertRaises(FileExistsError):
                builder.preflight(source, base, base, builder.sha256(source))
            with self.assertRaises(ValueError):
                builder.preflight(source, base / 'new', base, 'bad')
            with self.assertRaises(ValueError):
                builder.preflight(source, base.parent / 'outside', base, builder.sha256(source))

    def test_native_pin_and_overview_checksum_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / 'source'
            source.write_bytes(b'fixture')
            with self.assertRaises(ValueError):
                builder.preflight(source, base / 'new', base, builder.sha256(source), source, 'wrong')
            with patch.object(builder, 'BINARY_SHA256', 'wrong'):
                with self.assertRaises(ValueError):
                    builder.preflight(source, base / 'new', base, builder.sha256(source))

    def test_source_symlinks_are_not_new_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / 'source'
            source.write_bytes(b'fixture')
            output = base / 'new'
            output.mkdir()
            (output / 'input').symlink_to(source)
            class Disk:
                free = 45 * builder.GIB
            with patch.object(builder.shutil, 'disk_usage', return_value=Disk()):
                self.assertEqual(builder.resource_check(output)['named_output_bytes'], 0)


if __name__ == '__main__':
    unittest.main()
