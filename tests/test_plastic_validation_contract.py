"""Focused checks for exact plastic DBF decimal types and PMTiles zoom contract."""
import importlib.util
from decimal import Decimal
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

import pyarrow as pa


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / 'datasets/river-plastic-inputs'
sys.path.insert(0, str(DATASET))


def load_validator():
    stubs = {}
    if importlib.util.find_spec('pmtiles') is None:
        package = types.ModuleType('pmtiles')
        package.__path__ = []
        reader = types.ModuleType('pmtiles.reader')
        reader.Reader = object
        reader.all_tiles = lambda source: iter(())
        tile = types.ModuleType('pmtiles.tile')
        tile.Compression = types.SimpleNamespace(GZIP=2, NONE=1)
        stubs = {'pmtiles': package, 'pmtiles.reader': reader, 'pmtiles.tile': tile}
    if importlib.util.find_spec('mapbox_vector_tile') is None:
        stubs['mapbox_vector_tile'] = types.ModuleType('mapbox_vector_tile')
    spec = importlib.util.spec_from_file_location('plastic_validator_contract', DATASET / 'validate.py')
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


validator = load_validator()


class PlasticValidationContractTests(unittest.TestCase):
    def test_dbf_width_and_scale_map_to_exact_decimal128_type(self):
        self.assertEqual(validator.dbf_decimal_type(10, 2), pa.decimal128(9, 2))
        self.assertEqual(validator.dbf_decimal_type(6, 0), pa.decimal128(6, 0))
        with self.assertRaisesRegex(ValueError, 'cannot fit decimal128'):
            validator.dbf_decimal_type(3, 4)

    def test_equal_numeric_values_with_rewritten_precision_are_rejected(self):
        value = pa.array([Decimal('1.25')], type=pa.decimal128(9, 2)).to_pylist()
        rewritten = pa.array([Decimal('1.25')], type=pa.decimal128(38, 2)).to_pylist()
        self.assertEqual(value, rewritten)
        with self.assertRaisesRegex(ValueError, r'expected decimal128\(9, 2\), found decimal128\(38, 2\)'):
            validator.require_dbf_decimal_type('amount', pa.decimal128(38, 2), 10, 2)

    def test_non_decimal_and_wrong_scale_types_are_rejected(self):
        for datatype in (pa.float64(), pa.decimal128(9, 3)):
            with self.subTest(datatype=datatype), self.assertRaisesRegex(ValueError, 'Source decimal type differs'):
                validator.require_dbf_decimal_type('amount', datatype, 10, 2)

    def test_pmtiles_header_must_match_frozen_minimum_and_configured_maximum(self):
        validator.require_pmtiles_zoom_range({'min_zoom': 0, 'max_zoom': validator.CONFIG['pmtiles_maxzoom']})
        with self.assertRaisesRegex(ValueError, 'maximum zoom differs'):
            validator.require_pmtiles_zoom_range({'min_zoom': 0, 'max_zoom': validator.CONFIG['pmtiles_maxzoom'] - 1})
        with self.assertRaisesRegex(ValueError, 'minimum zoom differs'):
            validator.require_pmtiles_zoom_range({'min_zoom': 1, 'max_zoom': validator.CONFIG['pmtiles_maxzoom']})


if __name__ == '__main__':
    unittest.main(verbosity=2)
