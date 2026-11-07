"""Focused Parquet row-group statistics contract tests for FFR validation."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
FFR_DIR = ROOT / "datasets/free-flowing-rivers"
sys.path.insert(0, str(FFR_DIR))
spec = importlib.util.spec_from_file_location("ffr_validate", FFR_DIR / "validate.py")
validator = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(validator)


def _table(source_rows=(1, 2, 3, 4)):
    return pa.table({
        "source_row": pa.array(source_rows, type=pa.int64()),
        "count": pa.array([10, 9, 4, 6], type=pa.int64()),
        "all_null": pa.array([None, None, None, None], type=pa.int32()),
        "label": pa.array(["b", "a", "d", "c"], type=pa.string()),
        "Shape": pa.array([b"geom-a", b"geom-b", b"geom-c", b"geom-d"], type=pa.binary()),
        "bbox": pa.array([
            {"xmin": 1.0, "ymin": 2.0}, {"xmin": 3.0, "ymin": 4.0},
            {"xmin": 5.0, "ymin": 6.0}, {"xmin": 7.0, "ymin": 8.0},
        ], type=pa.struct([pa.field("xmin", pa.float64()), pa.field("ymin", pa.float64())])),
    })


class FFRStatisticsContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write_parquet(self, name, source_rows=(1, 2, 3, 4), *, write_statistics=True):
        path = self.root / name
        pq.write_table(_table(source_rows), path, row_group_size=2, write_statistics=write_statistics)
        return pq.ParquetFile(path)

    def test_continuous_groups_and_all_null_scalar_statistics_pass(self):
        parquet = self.write_parquet("valid.parquet")
        layout = validator.check_row_group_statistics(parquet, expected_group_rows=2)
        self.assertEqual(layout["row_groups"], 2)
        self.assertEqual(layout["source_row_ranges_checked"], 2)
        for group_no, (group, batch) in enumerate(zip(
            (parquet.metadata.row_group(i) for i in range(parquet.metadata.num_row_groups)),
            parquet.iter_batches(batch_size=2), strict=True,
        )):
            checked = validator.check_batch_statistics(group, batch, group_no)
            self.assertGreater(checked["scalar_min_max_columns_checked"], 0)
        all_null = parquet.metadata.row_group(0).column(2).statistics
        self.assertEqual(all_null.null_count, 2)
        self.assertFalse(all_null.has_min_max)

    def test_incorrect_source_row_maximum_is_rejected(self):
        parquet = self.write_parquet("bad-max.parquet", (1, 3, 4, 5))
        with self.assertRaisesRegex(ValueError, "source_row maximum"):
            validator.check_row_group_statistics(parquet, expected_group_rows=2)

    def test_source_row_group_discontinuity_is_rejected(self):
        parquet = self.write_parquet("gap.parquet", (1, 2, 4, 5))
        with self.assertRaisesRegex(ValueError, "source_row minimum"):
            validator.check_row_group_statistics(parquet, expected_group_rows=2)

    def test_missing_statistics_are_rejected(self):
        parquet = self.write_parquet("no-stats.parquet", write_statistics=False)
        with self.assertRaisesRegex(ValueError, "missing statistics"):
            validator.check_row_group_statistics(parquet, expected_group_rows=2)

    def test_scalar_bounds_are_checked_but_geometry_byte_bounds_are_not(self):
        parquet = self.write_parquet("bounds.parquet")
        group = parquet.metadata.row_group(0)
        batch = next(parquet.iter_batches(batch_size=2))
        changed_scalar = batch.set_column(1, batch.schema.field(1), pa.array([9, 99], type=pa.int64()))
        with self.assertRaisesRegex(ValueError, "maximum statistic for count"):
            validator.check_batch_statistics(group, changed_scalar, 0)
        changed_geometry = batch.set_column(4, batch.schema.field(4), pa.array([b"z", b"y"], type=pa.binary()))
        validator.check_batch_statistics(group, changed_geometry, 0)


if __name__ == "__main__":
    unittest.main()
