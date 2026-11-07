import tempfile
import unittest
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
from check_spatial_pruning import check


class SpatialPruningTests(unittest.TestCase):
    def test_disjoint_groups_prune_and_empty_windows_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "points.parquet"
            xs = [0., 1., 100., 101.]
            box = pa.StructArray.from_arrays([pa.array(xs), pa.array([0.] * 4), pa.array(xs), pa.array([0.] * 4)],
                                             names=["xmin", "ymin", "xmax", "ymax"])
            pq.write_table(pa.table({"bbox": box}), path, row_group_size=2)
            report = check(path, {"local": [-1, -1, 2, 1], "empty": [40, 40, 41, 41]})
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["queries"][0]["prunable_fraction"], .5)
            self.assertEqual(report["queries"][0]["matching_rows"], 2)
            self.assertEqual(report["queries"][1]["status"], "empty_reported")

    def test_interleaved_groups_fail_locality_and_missing_stats_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "points.parquet"
            xs = [0., 100., 1., 101.]
            box = pa.StructArray.from_arrays([pa.array(xs), pa.array([0.] * 4), pa.array(xs), pa.array([0.] * 4)],
                                             names=["xmin", "ymin", "xmax", "ymax"])
            table = pa.table({"bbox": box})
            pq.write_table(table, path, row_group_size=2)
            self.assertEqual(check(path, {"local": [-1, -1, 2, 1]})["status"], "failed")
            self.assertEqual(check(path, {"empty": [40, 40, 41, 41]})["status"], "failed")
            pq.write_table(table, path, write_statistics=False)
            with self.assertRaisesRegex(ValueError, "missing bbox min/max"):
                check(path)


if __name__ == "__main__":
    unittest.main()
