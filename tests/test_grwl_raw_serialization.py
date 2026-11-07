"""Batched GRWL display GeoJSON must remain identical to the scalar reference."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest

import pyarrow as pa
import shapely


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('grwl_raw_display_builder_serialization',
                                              ROOT / 'datasets/grwl-raw/build_display.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def row(feature_id, parts, width, width_valid):
    geometry = shapely.MultiLineString(parts)
    xmin, ymin, xmax, ymax = geometry.bounds
    return {'feature_id': feature_id, 'width_m': width, 'width_valid': width_valid,
            'bbox': {'xmin': xmin, 'ymin': ymin, 'xmax': xmax, 'ymax': ymax},
            'geometry': shapely.to_wkb(geometry)}


def record_batch(rows):
    schema = pa.schema([
        ('feature_id', pa.uint64()), ('width_m', pa.int64()), ('width_valid', pa.bool_()),
        ('bbox', pa.struct([(name, pa.float64()) for name in builder.BBOX])), ('geometry', pa.binary()),
    ])
    return pa.RecordBatch.from_pylist(rows, schema=schema)


class BatchedSerializationTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            row(0x010200000001, [[(0.0, -0.0), (1.123456789012, -2.987654321)]], 1, False),
            row(0x010200000002, [[(179.8, 10.0), (-179.6, 10.3)],
                                 [(20.0, 20.0), (21.0, 20.0)]], 50, True),
            row(0x010200000003, [[(-179.5, -20.0), (179.7, -20.2)]], None, False),
            row(0x010200000004, [[(11.0, 0.0), (11.000000001, 0.000000001)],
                                 [(12.0, 1.0), (12.1, 1.1)]], 200, True),
        ]
        self.batch = record_batch(self.rows)

    def test_batched_lines_parse_to_scalar_reference_features(self):
        actual = list(builder.iter_feature_lines(self.batch))
        expected = [json.dumps(builder.display_feature(source), separators=(',', ':'), allow_nan=False).encode() + b'\n'
                    for source in self.rows]
        self.assertEqual(actual, expected)
        self.assertEqual([json.loads(line) for line in actual], [builder.display_feature(source) for source in self.rows])

    def test_batch_preserves_ids_width_null_sentinel_negative_zero_and_part_order(self):
        features = [json.loads(line) for line in builder.iter_feature_lines(self.batch)]
        self.assertEqual([feature['id'] for feature in features], [row['feature_id'] for row in self.rows])
        self.assertEqual(features[0]['properties']['width_m'], 1)
        self.assertIsNone(features[2]['properties'].get('width_m'))
        self.assertEqual(len(features[1]['geometry']['coordinates']), 3)
        self.assertEqual(features[3]['geometry']['coordinates'][0][0], [11.0, 0.0])
        self.assertEqual(features[0]['geometry']['coordinates'][0][0][1], -0.0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
