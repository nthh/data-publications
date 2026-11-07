"""Independent source-to-GeoParquet fidelity validation tests."""
from __future__ import annotations

import importlib.util
import json
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

import pyarrow as pa
import pyarrow.parquet as pq
from pyproj import CRS

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("grwl_raw_validate", ROOT / "datasets/grwl-raw/validate.py")
validator = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(validator)

FIELDS = [
    ("utm_east", 9, 0), ("utm_north", 10, 0), ("width_m", 8, 0),
    ("nchannels", 19, 15), ("segmentID", 9, 0), ("segmentInd", 10, 0),
    ("lakeFlag", 19, 15), ("lon", 19, 14), ("lat", 19, 14), ("elev_m", 7, 0),
]
INTEGER_FIELDS = {"width_m", "segmentID", "segmentInd", "elev_m"}
DECIMAL_FIELDS = {name for name, _, _ in FIELDS} - INTEGER_FIELDS
WGS84_WKT = CRS.from_epsg(4326).to_wkt()


def _shape(parts):
    points = [point for part in parts for point in part]
    starts, count = [], 0
    for part in parts:
        starts.append(count)
        count += len(part)
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    body = struct.pack("<i4d2i", 3, min(xs), min(ys), max(xs), max(ys), len(parts), len(points))
    body += struct.pack("<" + "i" * len(starts), *starts)
    body += b"".join(struct.pack("<dd", *point) for point in points)
    return body


def _header(file_bytes):
    return (struct.pack(">7i", 9994, 0, 0, 0, 0, 0, file_bytes // 2)
            + struct.pack("<2i8d", 1000, 3, -180.0, -90.0, 180.0, 90.0, 0, 0, 0, 0))


def _fixture(source: Path):
    features = [
        {"parts": [[(1.0, 2.0), (2.0, 3.0)], [(10.0, 11.0), (12.0, 13.0)]],
         "attrs": {"utm_east": 100, "utm_north": 200, "width_m": 1,
                   "nchannels": "0.123456789012345", "segmentID": 77, "segmentInd": 1,
                   "lakeFlag": None, "lon": "-89.12345678901234", "lat": "41.12345678901234", "elev_m": -2}},
        {"parts": [[(-70.0, 8.0), (-69.5, 8.5)]],
         "attrs": {"utm_east": 101, "utm_north": 201, "width_m": 5,
                   "nchannels": "0.000000000000001", "segmentID": 77, "segmentInd": 2,
                   "lakeFlag": "0.000000000000001", "lon": "-69.75000000000000", "lat": "8.25000000000000", "elev_m": 3}},
    ]
    shapes, shx_entries, shp_records = [], [], []
    offset_words = 50
    for number, feature in enumerate(features, start=1):
        body = _shape(feature["parts"])
        words = len(body) // 2
        shapes.append(body)
        shp_records.append(struct.pack(">2i", number, words) + body)
        shx_entries.append(struct.pack(">2i", offset_words, words))
        offset_words += 4 + words
    shp_bytes = b"".join(shp_records)
    shx_bytes = b"".join(shx_entries)
    (source / "NI15.shp").write_bytes(_header(100 + len(shp_bytes)) + shp_bytes)
    (source / "NI15.shx").write_bytes(_header(100 + len(shx_bytes)) + shx_bytes)

    header_len = 32 + len(FIELDS) * 32 + 1
    record_len = 1 + sum(width for _, width, _ in FIELDS)
    header = bytearray(32)
    header[0] = 3
    struct.pack_into("<IHH", header, 4, len(features), header_len, record_len)
    descriptors = bytearray()
    for name, width, scale in FIELDS:
        desc = bytearray(32)
        desc[:len(name)] = name.encode()
        desc[11], desc[16], desc[17] = ord("N"), width, scale
        descriptors.extend(desc)
    dbf_rows = bytearray()
    for feature in features:
        dbf_rows.append(0x20)
        for name, width, _ in FIELDS:
            value = feature["attrs"][name]
            raw = b"" if value is None else str(value).encode()
            dbf_rows.extend(raw.rjust(width, b" "))
    (source / "NI15.dbf").write_bytes(bytes(header) + bytes(descriptors) + b"\r" + bytes(dbf_rows) + b"\x1a")
    (source / "NI15.prj").write_text(WGS84_WKT)
    rows = []
    for row_number, feature in enumerate(features, start=1):
        points = [point for part in feature["parts"] for point in part]
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        attrs = dict(feature["attrs"])
        for name in DECIMAL_FIELDS:
            attrs[name] = None if attrs[name] is None else __import__("decimal").Decimal(attrs[name])
        attrs.update({"source_tile": "NI15", "source_row": row_number,
                      "feature_id": validator._feature_id("NI15", row_number),
                      "width_valid": attrs["width_m"] is not None and attrs["width_m"] > 0 and attrs["width_m"] != 1,
                      "bbox": {"xmin": min(xs), "ymin": min(ys), "xmax": max(xs), "ymax": max(ys)},
                      "geometry": _wkb(feature["parts"])})
        rows.append(attrs)
    return rows


def _wkb(parts):
    data = bytearray(struct.pack("<BI", 1, 5) + struct.pack("<I", len(parts)))
    for part in parts:
        data.extend(struct.pack("<BI", 1, 2) + struct.pack("<I", len(part)))
        for point in part:
            data.extend(struct.pack("<dd", *point))
    return bytes(data)


def _write_parquet(path: Path, rows):
    fields = []
    for name, _, _ in FIELDS:
        fields.append(pa.field(name, pa.int64() if name in INTEGER_FIELDS else pa.decimal128(38, 18)))
    fields.extend([
        pa.field("source_tile", pa.string(), nullable=False), pa.field("source_row", pa.uint32(), nullable=False),
        pa.field("feature_id", pa.uint64(), nullable=False), pa.field("width_valid", pa.bool_(), nullable=False),
        pa.field("bbox", pa.struct([pa.field(k, pa.float64(), nullable=False)
                                    for k in ("xmin", "ymin", "xmax", "ymax")]), nullable=False),
        pa.field("geometry", pa.binary(), nullable=False),
    ])
    geo = {"version": "1.1.0", "primary_column": "geometry", "columns": {"geometry": {
        "encoding": "WKB", "geometry_types": ["MultiLineString"], "crs": CRS.from_epsg(4326).to_json_dict(),
        "edges": "planar", "covering": {"bbox": {key: ["bbox", key] for key in ("xmin", "ymin", "xmax", "ymax")}}}}}
    schema = pa.schema(fields, metadata={b"geo": json.dumps(geo).encode()})
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path, compression="zstd")


class GRWLRawValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.rows = _fixture(self.source)
        self.manifest = self.root / "manifest.json"
        self.manifest.write_text(json.dumps({"tiles": [{"tile": "NI15", "records": 2}]}))

    def tearDown(self):
        self.temp.cleanup()

    def write_manifest(self, parquet, archive=None):
        boxes = [row["bbox"] for row in self.rows]
        extent = [min(box["xmin"] for box in boxes), min(box["ymin"] for box in boxes),
                  max(box["xmax"] for box in boxes), max(box["ymax"] for box in boxes)]
        tile = {"tile": "NI15", "records": 2, "extent": extent,
                "source_sha256": {ext: hashlib.sha256((self.source / f"NI15.{ext}").read_bytes()).hexdigest()
                                  for ext in ("shp", "shx", "dbf", "prj")}}
        manifest = {"tiles": [tile], "parquet_sha256": hashlib.sha256(parquet.read_bytes()).hexdigest()}
        if archive is not None:
            manifest["archive"] = {"filename": archive.name, "size_bytes": archive.stat().st_size,
                                   "provider_md5": hashlib.md5(archive.read_bytes()).hexdigest(),
                                   "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}
        self.manifest.write_text(json.dumps(manifest))
        return manifest

    def validate_rows(self, rows, report):
        parquet = self.root / f"{report.stem}.parquet"
        _write_parquet(parquet, rows)
        self.write_manifest(parquet)
        return validator.validate(self.source, None, parquet, self.manifest, report)

    def test_exact_synthetic_tile_passes(self):
        report = self.validate_rows(self.rows, self.root / "pass.json")
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["progress"]["source_rows"], 2)
        self.assertEqual(report["progress"]["parts"], 3)
        self.assertEqual(report["progress"]["width_sentinel_1"], 1)
        self.assertEqual(len(report["tiles"][0]["first_records"]), 2)
        self.assertTrue(report["usable_release"])

    def test_altered_dbf_value_and_inserted_connector_fail(self):
        altered_attrs = [dict(row) for row in self.rows]
        altered_attrs[1]["utm_east"] += 1
        report = self.validate_rows(altered_attrs, self.root / "altered-attrs.json")
        self.assertEqual(report["status"], "failed")
        self.assertTrue(any(error.get("field") == "utm_east" for error in report["errors"]))

        altered_geometry = [dict(row) for row in self.rows]
        altered_geometry[0]["geometry"] = _wkb([[(1.0, 2.0), (2.0, 3.0), (3.0, 4.0)],
                                                   [(10.0, 11.0), (12.0, 13.0)]])
        report = self.validate_rows(altered_geometry, self.root / "altered-geometry.json")
        self.assertEqual(report["status"], "failed")
        self.assertTrue(any(error.get("field") == "geometry" for error in report["errors"]))

    def test_zip_member_stream_is_supported(self):
        archive = self.root / "source.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
            for ext in ("shp", "shx", "dbf", "prj"):
                zipped.write(self.source / f"NI15.{ext}", f"GRWL_vector_V01.01/NI15.{ext}")
        parquet = self.root / "zip.parquet"
        _write_parquet(parquet, self.rows)
        self.write_manifest(parquet, archive)
        report = validator.validate(None, archive, parquet, self.manifest, self.root / "zip-report.json")
        self.assertEqual(report["status"], "passed")

    def test_equal_valued_float_rewrite_fails_exact_arrow_schema(self):
        parquet = self.root / "float-width.parquet"
        _write_parquet(parquet, self.rows)
        table = pq.read_table(parquet)
        index = table.schema.get_field_index("width_m")
        pq.write_table(table.set_column(index, "width_m", table["width_m"].cast(pa.float64())), parquet)
        self.write_manifest(parquet)
        report = validator.validate(self.source, None, parquet, self.manifest, self.root / "float-width.json")
        self.assertEqual(report["status"], "failed")
        self.assertTrue(any(error.get("field") == "schema" for error in report["errors"]))

    def test_wrong_or_missing_prj_fails(self):
        parquet = self.root / "prj.parquet"
        _write_parquet(parquet, self.rows)
        self.write_manifest(parquet)
        prj = self.source / "NI15.prj"
        prj.unlink()
        missing = validator.validate(self.source, None, parquet, self.manifest, self.root / "missing-prj.json")
        self.assertEqual(missing["status"], "failed")
        self.assertIn("Missing source member", missing["fatal_error"]["message"])

        prj.write_text(CRS.from_epsg(3857).to_wkt())
        self.write_manifest(parquet)
        wrong = validator.validate(self.source, None, parquet, self.manifest, self.root / "wrong-prj.json")
        self.assertEqual(wrong["status"], "failed")
        self.assertIn("PRJ CRS is not EPSG:4326", wrong["fatal_error"]["message"])

    def test_altered_source_member_pin_fails(self):
        parquet = self.root / "source-pin.parquet"
        _write_parquet(parquet, self.rows)
        manifest = self.write_manifest(parquet)
        manifest["tiles"][0]["source_sha256"]["dbf"] = "0" * 64
        self.manifest.write_text(json.dumps(manifest))
        report = validator.validate(self.source, None, parquet, self.manifest, self.root / "source-pin.json")
        self.assertEqual(report["status"], "failed")
        self.assertIn("SHA-256 differs", report["fatal_error"]["message"])

    def test_altered_archive_identity_fails(self):
        archive = self.root / "source.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
            for ext in ("shp", "shx", "dbf", "prj"):
                zipped.write(self.source / f"NI15.{ext}", f"GRWL_vector_V01.01/NI15.{ext}")
        parquet = self.root / "archive-pin.parquet"
        _write_parquet(parquet, self.rows)
        manifest = self.write_manifest(parquet, archive)
        manifest["archive"]["sha256"] = "0" * 64
        self.manifest.write_text(json.dumps(manifest))
        report = validator.validate(None, archive, parquet, self.manifest, self.root / "archive-pin.json")
        self.assertEqual(report["status"], "failed")
        self.assertIn("Source ZIP", report["fatal_error"]["message"])

    def test_misdeclared_covering_and_bbox_fail(self):
        parquet = self.root / "bad-geo.parquet"
        _write_parquet(parquet, self.rows)
        table = pq.read_table(parquet)
        geo = json.loads(table.schema.metadata[b"geo"])
        geo["columns"]["geometry"]["covering"]["bbox"]["xmin"] = ["bbox", "xmax"]
        geo["columns"]["geometry"]["bbox"] = [0, 0, 1, 1]
        table = table.replace_schema_metadata({**table.schema.metadata, b"geo": json.dumps(geo).encode()})
        pq.write_table(table, parquet)
        self.write_manifest(parquet)
        report = validator.validate(self.source, None, parquet, self.manifest, self.root / "bad-geo.json")
        self.assertEqual(report["status"], "failed")
        self.assertTrue(any("covering bbox" in error["message"] for error in report["errors"]))
        self.assertTrue(any(error.get("field") == "geo.bbox" for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
