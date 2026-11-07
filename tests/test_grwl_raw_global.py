"""Small ZIP fixtures for the bounded global GRWL converter."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile
from collections import namedtuple
from decimal import Decimal
from unittest import mock

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("grwl_raw_build_global", ROOT / "datasets/grwl-raw/build_global.py")
builder = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(builder)
validator_spec = importlib.util.spec_from_file_location("grwl_raw_validate", ROOT / "datasets/grwl-raw/validate.py")
validator = importlib.util.module_from_spec(validator_spec)
assert validator_spec.loader is not None
validator_spec.loader.exec_module(validator)

FIELDS = [
    ("utm_east", 19, 10), ("utm_north", 19, 9), ("width_m", 8, 0),
    ("nchannels", 19, 15), ("segmentID", 9, 0), ("segmentInd", 10, 0),
    ("lakeFlag", 19, 15), ("lon", 19, 14), ("lat", 19, 14), ("elev_m", 7, 0),
]
WGS84_WKT = ('GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
             'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]')


def _shape(parts):
    points = [xy for part in parts for xy in part]
    starts, count = [], 0
    for part in parts:
        starts.append(count)
        count += len(part)
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    data = struct.pack("<i4d2i", 3, min(xs), min(ys), max(xs), max(ys), len(parts), len(points))
    data += struct.pack("<" + "i" * len(starts), *starts)
    data += b"".join(struct.pack("<dd", *p) for p in points)
    return data


def _shape_header(size):
    return (struct.pack(">7i", 9994, 0, 0, 0, 0, 0, size // 2)
            + struct.pack("<2i8d", 1000, 3, -180, -90, 180, 90, 0, 0, 0, 0))


def _tile_members(tile, features):
    shape_bodies, shp_records, shx_records = [], [], []
    offset = 50
    for record_no, feature in enumerate(features, start=1):
        body = _shape(feature["parts"])
        words = len(body) // 2
        shape_bodies.append(body)
        shp_records.append(struct.pack(">2i", record_no, words) + body)
        shx_records.append(struct.pack(">2i", offset, words))
        offset += 4 + words
    shp_body, shx_body = b"".join(shp_records), b"".join(shx_records)
    shp = _shape_header(100 + len(shp_body)) + shp_body
    shx = _shape_header(100 + len(shx_body)) + shx_body
    header_len = 32 + len(FIELDS) * 32 + 1
    record_len = 1 + sum(width for _, width, _ in FIELDS)
    dbf_header = bytearray(32)
    dbf_header[0] = 3
    struct.pack_into("<IHH", dbf_header, 4, len(features), header_len, record_len)
    descriptors = bytearray()
    for name, width, scale in FIELDS:
        desc = bytearray(32)
        desc[:len(name)] = name.encode("ascii")
        desc[11], desc[16], desc[17] = ord("N"), width, scale
        descriptors.extend(desc)
    records = bytearray()
    for feature in features:
        records.append(0x20)
        for name, width, _ in FIELDS:
            value = feature["attrs"][name]
            raw = b"" if value is None else str(value).encode("ascii")
            records.extend(raw.rjust(width, b" "))
    dbf = bytes(dbf_header) + bytes(descriptors) + b"\r" + bytes(records) + b"\x1a"
    return {f"GRWL_vector_V01.01/{tile}.shp": shp,
            f"GRWL_vector_V01.01/{tile}.shx": shx,
            f"GRWL_vector_V01.01/{tile}.dbf": dbf,
            f"GRWL_vector_V01.01/{tile}.prj": WGS84_WKT.encode("ascii")}


def _attrs(**updates):
    attrs = {"utm_east": "563025.0000000000", "utm_north": "5903175.000000000", "width_m": 1,
             "nchannels": "0.123456789012345", "segmentID": 7, "segmentInd": 1,
             "lakeFlag": None, "lon": "-89.12345678901234", "lat": "41.12345678901234", "elev_m": -2}
    attrs.update(updates)
    return attrs


def _fixture_archive(path, *, invalid_dbf=False, empty_tile=False, fractional_nn29=False):
    files = {}
    first_tile, second_tile = ("NN29", "NP12") if fractional_nn29 else ("NI15", "NJ12")
    first_value = "563025.1250000000" if fractional_nn29 else "563025.0000000000"
    north_value = "5903175.000000001" if fractional_nn29 else "5903175.000000000"
    files.update(_tile_members(first_tile, [
        {"parts": [[(1.0, 2.0), (2.0, 3.0)], [(10.0, 11.0), (12.0, 13.0)]],
         "attrs": _attrs(utm_east=first_value, utm_north=north_value, width_m=1, segmentInd=1)},
        # Repeated segmentID is intentionally a separate raw record.
        {"parts": [[(100.0, -4.0), (100.5, -3.5)]],
         "attrs": _attrs(utm_east="563025.2500000000" if fractional_nn29 else "563025.0000000000",
                         utm_north="5903175.250000000" if fractional_nn29 else "5903175.000000000",
                         width_m=5, segmentInd=2)},
    ]))
    files.update(_tile_members(second_tile, [
        {"parts": [[(-70.125, 8.25), (-69.875, 8.5)]], "attrs": _attrs(width_m=0, segmentInd=1)},
    ]))
    if empty_tile:
        files.update(_tile_members("NI36", []))
    if invalid_dbf:
        dbf_name = f"GRWL_vector_V01.01/{first_tile}.dbf"
        damaged = bytearray(files[dbf_name])
        # Corrupt the first numeric value while preserving the DBF header and ZIP CRC.
        numeric_start = 32 + len(FIELDS) * 32 + 1 + 1
        damaged[numeric_start:numeric_start + 3] = b"BAD"
        files[dbf_name] = bytes(damaged)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in sorted(files.items()):
            archive.writestr(name, payload)
    with zipfile.ZipFile(path) as archive:
        members = []
        for info in archive.infolist():
            members.append({"name": info.filename, "compressed_bytes": info.compress_size,
                            "uncompressed_bytes": info.file_size, "crc32": f"{info.CRC:08x}",
                            "header_offset": info.header_offset})
    inventory = {"archive_size_bytes": path.stat().st_size, "members": members}
    md5 = hashlib.md5(path.read_bytes()).hexdigest()
    criteria = {"raw_component": {"filename": path.name, "archive_size_bytes": path.stat().st_size,
                                   "provider_md5": md5, "expected_tiles": 3 if empty_tile else 2}}
    pin = {"archive_size_bytes": path.stat().st_size, "provider_md5": md5,
           "expected_tiles": 3 if empty_tile else 2, "expected_rows": 3}
    return criteria, inventory, pin


def _disk_usage(_path):
    Usage = namedtuple("Usage", "total used free")
    return Usage(100 * 1024**3, 0, 100 * 1024**3)


class GlobalGRWLBuildTests(unittest.TestCase):
    def test_empty_source_tile_is_retained_in_inventory(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); archive=root/"tiny.zip"
            criteria, inventory, pin=_fixture_archive(archive, empty_tile=True)
            output=root/"release"
            manifest=builder.build_global(archive,output,criteria,inventory,pin,disk_usage_fn=_disk_usage,min_free_bytes=1,max_task_bytes=1024**3)
            empty=next(t for t in manifest["tiles"] if t["tile"]=="NI36")
            self.assertEqual(empty["records"],0)
            self.assertIsNone(empty["extent"])
            result=validator.validate(None,archive,output/"grwl-raw.parquet",output/"manifest.json",root/"validation.json")
            self.assertEqual(result["status"],"passed")
            geo=json.loads(pq.ParquetFile(output/"grwl-raw.parquet").schema_arrow.metadata[b"geo"])
            self.assertEqual(geo["columns"]["geometry"]["bbox"],[-70.125,-4.0,100.5,13.0])

    def test_pinned_synthetic_zip_builds_one_sorted_parquet(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "tiny.zip"
            criteria, inventory, pin = _fixture_archive(archive)
            output = root / "release"
            manifest = builder.build_global(archive, output, criteria, inventory, pin,
                                            disk_usage_fn=_disk_usage, min_free_bytes=1,
                                            max_task_bytes=1024**3)
            table = pq.read_table(output / "grwl-raw.parquet")
            rows = table.to_pylist()
            self.assertEqual(manifest["status"], "provisional")
            self.assertFalse(manifest["usable_release"])
            self.assertEqual(manifest["validation"]["status"], "pending")
            self.assertEqual(manifest["rows"], 3)
            self.assertEqual([tile["tile"] for tile in manifest["tiles"]], ["NI15", "NJ12"])
            self.assertEqual([row["source_row"] for row in rows], [1, 2, 1])
            self.assertEqual([row["source_tile"] for row in rows], ["NI15", "NI15", "NJ12"])
            self.assertEqual(rows[0]["segmentID"], rows[1]["segmentID"])
            self.assertEqual(rows[0]["width_m"], 1)
            self.assertFalse(rows[0]["width_valid"])
            self.assertEqual(manifest["tiles"][0]["parts"], 3)
            self.assertTrue(all("source_sha256" in tile and "source_record_digest_sha256" in tile
                                for tile in manifest["tiles"]))
            self.assertFalse((output / "partial.json").exists())
            self.assertFalse((output / ".scratch").exists())
            validation = validator.validate(None, archive, output / "grwl-raw.parquet",
                                            output / "manifest.json", root / "validation.json")
            self.assertEqual(validation["status"], "passed")
            with self.assertRaisesRegex(FileExistsError, "Refusing to overwrite"):
                builder.build_global(archive, output, criteria, inventory, pin,
                                     disk_usage_fn=_disk_usage, min_free_bytes=1,
                                     max_task_bytes=1024**3)

    def test_nn29_decimal_coordinate_schema_preserves_fractional_values(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "nn29.zip"
            criteria, inventory, pin = _fixture_archive(archive, fractional_nn29=True)
            output = root / "nn29-release"
            manifest = builder.build_global(archive, output, criteria, inventory, pin,
                                            disk_usage_fn=_disk_usage, min_free_bytes=1,
                                            max_task_bytes=1024**3)
            rows = pq.read_table(output / "grwl-raw.parquet").to_pylist()
            schema = pq.ParquetFile(output / "grwl-raw.parquet").schema_arrow
            self.assertEqual(manifest["tiles"][0]["tile"], "NN29")
            self.assertEqual(manifest["tiles"][0]["source_dbf_schema"][0]["scale"], 10)
            self.assertEqual(manifest["tiles"][0]["source_dbf_schema"][1]["scale"], 9)
            self.assertEqual(rows[0]["utm_east"], Decimal("563025.1250000000"))
            self.assertEqual(rows[0]["utm_north"], Decimal("5903175.000000001"))
            self.assertEqual(schema.field("utm_east").type, builder.pa.decimal128(38, 18))
            for name in ("width_m", "segmentID", "segmentInd", "elev_m"):
                self.assertEqual(schema.field(name).type, builder.pa.int64())
            self.assertFalse(manifest["usable_release"])

    def test_missing_environment_lock_fails_before_output_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "tiny.zip"
            criteria, inventory, pin = _fixture_archive(archive)
            output = root / "must-not-exist"
            with mock.patch.object(builder.sys, "prefix", str(root / "unlocked-env" / ".venv")):
                with self.assertRaisesRegex(ValueError, "locked repository Python environment"):
                    builder.build_global(archive, output, criteria, inventory, pin,
                                         disk_usage_fn=_disk_usage, min_free_bytes=1,
                                         max_task_bytes=1024**3)
            self.assertFalse(output.exists())

    def test_wrong_archive_pin_fails_before_output_is_created(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "tiny.zip"
            criteria, inventory, pin = _fixture_archive(archive)
            pin["provider_md5"] = "0" * 32
            criteria["raw_component"]["provider_md5"] = "0" * 32
            output = root / "should-not-exist"
            with self.assertRaisesRegex(ValueError, "provider MD5 mismatch"):
                builder.build_global(archive, output, criteria, inventory, pin,
                                     disk_usage_fn=_disk_usage, min_free_bytes=1, max_task_bytes=1024**3)
            self.assertFalse(output.exists())

    def test_parse_failure_retains_failure_report_and_current_tile_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "bad.zip"
            criteria, inventory, pin = _fixture_archive(archive, invalid_dbf=True)
            output = root / "partial-release"
            with self.assertRaisesRegex(ValueError, "Malformed numeric value"):
                builder.build_global(archive, output, criteria, inventory, pin,
                                     disk_usage_fn=_disk_usage, min_free_bytes=1, max_task_bytes=1024**3)
            failure = json.loads((output / "failure.json").read_text())
            self.assertEqual(failure["status"], "failed_partial")
            self.assertFalse(failure["usable_release"])
            self.assertEqual(failure["current_tile"], "NI15")
            self.assertIn(".scratch/NI15/NI15.dbf", failure["retained_files"])
            self.assertTrue((output / "partial.json").is_file())
            self.assertTrue((output / ".scratch/NI15/NI15.shp").is_file())


if __name__ == "__main__":
    unittest.main()
