"""Lossless raw GRWL SHP/DBF conversion tests using tiny synthetic tiles."""
from __future__ import annotations

import importlib.util
import json
from decimal import Decimal
from pathlib import Path
import struct
import tempfile
import unittest

import pyarrow as pa
import pyarrow.parquet as pq
import shapely

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("grwl_raw_convert", ROOT / "datasets/grwl-raw/convert.py")
convert_module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(convert_module)

FIELDS = [
    ("utm_east", 19, 10), ("utm_north", 19, 9), ("width_m", 8, 0),
    ("nchannels", 19, 15), ("segmentID", 9, 0), ("segmentInd", 10, 0),
    ("lakeFlag", 19, 15), ("lon", 19, 14), ("lat", 19, 14), ("elev_m", 7, 0),
]


def _shape_record(parts: list[list[tuple[float, float]]]) -> bytes:
    points = [p for part in parts for p in part]
    starts, cursor = [], 0
    for part in parts:
        starts.append(cursor)
        cursor += len(part)
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    body = struct.pack("<i4d2i", 3, min(xs), min(ys), max(xs), max(ys), len(parts), len(points))
    body += struct.pack("<" + "i" * len(starts), *starts)
    body += b"".join(struct.pack("<dd", *point) for point in points)
    return body


def _shape_header(file_bytes: int) -> bytes:
    return (struct.pack(">7i", 9994, 0, 0, 0, 0, 0, file_bytes // 2)
            + struct.pack("<2i8d", 1000, 3, -180.0, -90.0, 180.0, 90.0, 0, 0, 0, 0))


def _write_tile(directory: Path, tile: str, rows: list[dict]) -> None:
    shapes = [_shape_record(row["parts"]) for row in rows]
    shp_records = []
    shx_entries = []
    offset_words = 50
    for number, shape in enumerate(shapes, 1):
        content_words = len(shape) // 2
        shp_records.append(struct.pack(">2i", number, content_words) + shape)
        shx_entries.append(struct.pack(">2i", offset_words, content_words))
        offset_words += 4 + content_words
    shp_body = b"".join(shp_records)
    shx_body = b"".join(shx_entries)
    (directory / f"{tile}.shp").write_bytes(_shape_header(100 + len(shp_body)) + shp_body)
    (directory / f"{tile}.shx").write_bytes(_shape_header(100 + len(shx_body)) + shx_body)
    (directory / f"{tile}.prj").write_text(
        'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
        'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]')

    header_len, record_len = 32 + 32 * len(FIELDS) + 1, 1 + sum(width for _, width, _ in FIELDS)
    dbf_header = bytearray(32)
    dbf_header[0] = 3
    dbf_header[1:4] = bytes((126, 1, 1))
    struct.pack_into("<IHH", dbf_header, 4, len(rows), header_len, record_len)
    descriptors = bytearray()
    for name, width, scale in FIELDS:
        descriptor = bytearray(32)
        descriptor[:len(name)] = name.encode("ascii")
        descriptor[11] = ord("N")
        descriptor[16] = width
        descriptor[17] = scale
        descriptors.extend(descriptor)
    records = bytearray()
    for row in rows:
        records.append(0x20)
        for name, width, _ in FIELDS:
            value = row["attrs"].get(name)
            raw = b"" if value is None else str(value).encode("ascii")
            if len(raw) > width:
                raise ValueError(f"Fixture value does not fit {name}: {value}")
            records.extend(raw.rjust(width, b" "))
    (directory / f"{tile}.dbf").write_bytes(bytes(dbf_header) + bytes(descriptors) + b"\r" + bytes(records) + b"\x1a")


def _attrs(**updates):
    values = {"utm_east": 123, "utm_north": 456, "width_m": 2,
              "nchannels": "0.123456789012345", "segmentID": 77, "segmentInd": 4,
              "lakeFlag": "0.000000000000001", "lon": "-89.12345678901234",
              "lat": "41.12345678901234", "elev_m": -3}
    values.update(updates)
    return values


def _fixture(directory: Path) -> None:
    _write_tile(directory, "NI15", [
        {"parts": [[(1.0, 2.0), (-0.0, 3.0)], [(10.25, 11.5), (12.75, 13.125)]],
         "attrs": _attrs(width_m=1, nchannels="0.123456789012345", lakeFlag=None)},
        # Deliberately shares segmentID yet is an independent source record.
        {"parts": [[(100.0, -4.0), (100.5, -3.5)]], "attrs": _attrs(width_m=0, segmentInd=5)},
    ])
    _write_tile(directory, "NJ12", [
        {"parts": [[(-70.125, 8.25), (-69.875, 8.5)]],
         "attrs": _attrs(width_m=12, segmentID=77, segmentInd=4, nchannels=None)},
    ])


class GRWLConversionTests(unittest.TestCase):
    def test_lossless_record_parts_decimal_nulls_sentinel_and_tile_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source, output = base / "source", base / "output"
            source.mkdir()
            _fixture(source)
            dbf = bytearray((source / "NI15.dbf").read_bytes())
            # A DBF descriptor may declare a scale above the pilot's maximum;
            # values that fit the common schema remain exact.
            dbf[32 + 3 * 32 + 17] = 18
            (source / "NI15.dbf").write_bytes(dbf)
            batches = list(convert_module.iter_tile_batches(source, "NI15", batch_size=1))
            self.assertEqual([batch.num_rows for batch in batches], [1, 1])
            self.assertEqual(batches[0].schema.field("nchannels").type, pa.decimal128(38, 18))
            self.assertIn(b"geo", batches[0].schema.metadata)
            report = convert_module.convert(source, ["NI15", "NJ12"], output)

            table = pq.read_table(output / "grwl-raw.parquet")
            rows = table.to_pylist()
            self.assertEqual(len(rows), 3)
            self.assertEqual([row["source_row"] for row in rows], [1, 2, 1])
            self.assertEqual([row["source_tile"] for row in rows], ["NI15", "NI15", "NJ12"])
            self.assertEqual(len({row["feature_id"] for row in rows}), 3)
            self.assertEqual(rows[0]["feature_id"], convert_module.feature_id("NI15", 1))
            self.assertNotEqual(rows[0]["feature_id"], rows[2]["feature_id"])
            self.assertEqual(rows[0]["segmentID"], rows[1]["segmentID"])
            self.assertEqual(rows[0]["width_m"], 1)
            self.assertFalse(rows[0]["width_valid"])
            self.assertFalse(rows[1]["width_valid"])
            self.assertTrue(rows[2]["width_valid"])
            self.assertIsNone(rows[0]["lakeFlag"])
            self.assertIsNone(rows[2]["nchannels"])
            self.assertEqual(rows[0]["nchannels"], Decimal("0.123456789012345"))
            self.assertEqual(rows[0]["utm_east"], Decimal("123"))
            self.assertEqual(rows[0]["lon"], Decimal("-89.12345678901234"))

            first = shapely.from_wkb(rows[0]["geometry"])
            self.assertEqual(first.geom_type, "MultiLineString")
            self.assertEqual(len(first.geoms), 2)
            # Compare raw IEEE-754 bits so signed zero and ordinary values must
            # survive SHP input, WKB output and WKB decoding unchanged.
            expected = [(1.0, 2.0), (-0.0, 3.0), (10.25, 11.5), (12.75, 13.125)]
            actual = [xy for part in first.geoms for xy in part.coords]
            self.assertEqual([struct.pack("<dd", *p) for p in actual], [struct.pack("<dd", *p) for p in expected])
            self.assertEqual(rows[0]["bbox"], {"xmin": -0.0, "ymin": 2.0, "xmax": 12.75, "ymax": 13.125})

            metadata = json.loads(table.schema.metadata[b"geo"])
            self.assertEqual(metadata["version"], "1.1.0")
            self.assertEqual(metadata["columns"]["geometry"]["encoding"], "WKB")
            self.assertEqual(report["rows"], 3)
            self.assertEqual([tile["records"] for tile in report["tiles"]], [2, 1])
            self.assertEqual(report["tiles"][0]["source_dbf_schema"][3]["scale"], 18)
            self.assertTrue((output / "manifest.json").is_file())
            self.assertFalse((output / "partial.json").exists())
            with self.assertRaisesRegex(FileExistsError, "Refusing to overwrite"):
                convert_module.convert(source, ["NI15", "NJ12"], output)

    def test_feature_id_validation_and_json_safe_bound(self):
        self.assertEqual(convert_module.feature_id("AA00", 1), 1)
        with self.assertRaisesRegex(ValueError, "Invalid GRWL tile"):
            convert_module.feature_id("aa00", 1)
        with self.assertRaisesRegex(ValueError, "1-based uint32"):
            convert_module.feature_id("AA00", 0)
        self.assertLess(convert_module.feature_id("ZZ99", 1), convert_module.MAX_SAFE_JSON_INTEGER)

    def test_failed_conversion_retains_partial_output_and_refuses_reuse(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source, output = base / "source", base / "failed-output"
            source.mkdir()
            _fixture(source)
            shx_path = source / "NI15.shx"
            shx = bytearray(shx_path.read_bytes() + b"\0\0")
            struct.pack_into(">i", shx, 24, len(shx) // 2)
            shx_path.write_bytes(shx)

            with self.assertRaisesRegex(ValueError, "complete 8-byte index records"):
                convert_module.convert(source, ["NI15"], output)
            failure = json.loads((output / "failure.json").read_text())
            marker = json.loads((output / "partial.json").read_text())
            self.assertEqual(failure["status"], "failed_partial")
            self.assertFalse(failure["usable_release"])
            self.assertFalse(marker["usable_release"])
            self.assertIn("grwl-raw.parquet", failure["partial_files"])
            self.assertTrue((output / "grwl-raw.parquet").is_file())
            with self.assertRaisesRegex(FileExistsError, "Refusing to overwrite"):
                convert_module.convert(source, ["NI15"], output)

    def test_one_vertex_part_is_rejected(self):
        body = _shape_record([[(1.0, 2.0)]])
        with self.assertRaisesRegex(ValueError, "fewer than two vertices"):
            convert_module._geometry_from_record(body, "NI15", 1)

    def test_nn29_decimal_coordinate_fields_keep_fractional_values(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source, output = base / "source", base / "output"
            source.mkdir()
            _write_tile(source, "NN29", [
                {"parts": [[(1.0, 2.0), (2.0, 3.0)]],
                 "attrs": _attrs(utm_east="563025.0000000000", utm_north="5903175.000000000")},
                {"parts": [[(4.0, 5.0), (6.0, 7.0)]],
                 "attrs": _attrs(utm_east="563025.1250000000", utm_north="5903175.000000001")},
            ])
            report = convert_module.convert(source, ["NN29"], output)
            table = pq.read_table(output / "grwl-raw.parquet")
            rows = table.to_pylist()
            self.assertEqual(table.schema.field("utm_east").type, pa.decimal128(38, 18))
            self.assertEqual(table.schema.field("utm_north").type, pa.decimal128(38, 18))
            self.assertEqual(rows[0]["utm_east"], Decimal("563025.0000000000"))
            self.assertEqual(rows[0]["utm_north"], Decimal("5903175.000000000"))
            self.assertEqual(rows[1]["utm_east"], Decimal("563025.1250000000"))
            self.assertEqual(rows[1]["utm_north"], Decimal("5903175.000000001"))
            self.assertEqual(report["tiles"][0]["source_dbf_schema"][0]["scale"], 10)
            self.assertEqual(report["tiles"][0]["source_dbf_schema"][1]["scale"], 9)

    def test_nonrepresentable_decimal_precision_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "cannot fit decimal128"):
            convert_module._parse_numeric(b"0.1234567890123456789", {"name": "utm_east"}, "NN29", 1)


if __name__ == "__main__":
    unittest.main()
