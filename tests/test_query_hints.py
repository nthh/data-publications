from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

PATH = Path(__file__).resolve().parents[1] / "scripts/source_publish/prepare_query_hints.py"
SPEC = importlib.util.spec_from_file_location("prepare_query_hints_tested", PATH)
assert SPEC and SPEC.loader
hints = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = hints
SPEC.loader.exec_module(hints)


def fixture(tmp_path):
    path = tmp_path / "one.parquet"
    geo = {"version": "1.1.0", "primary_column": "geometry", "columns": {
        "geometry": {"encoding": "WKB", "geometry_types": ["Point"],
                     "covering": {"bbox": {name: ["bbox", name]
                                            for name in ("xmin", "ymin", "xmax", "ymax")}}}}}
    bbox = pa.struct([(name, pa.float64()) for name in ("xmin", "ymin", "xmax", "ymax")])
    point = b"\x01" + struct.pack("<I", 1) + struct.pack("<dd", 1., 2.)
    table = pa.table({"FID": pa.array([7], type=pa.int64()),
                      "bbox": pa.array([{"xmin": 1., "ymin": 2., "xmax": 1., "ymax": 2.}], type=bbox),
                      "geometry": pa.array([point], type=pa.binary())})
    table = table.replace_schema_metadata({"geo": json.dumps(geo).encode()})
    pq.write_table(table, path)
    entry = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "size_bytes": path.stat().st_size}
    query = {"name": "fixed", "path": "one.parquet", "id_column": "FID", "ids": [7],
             "selection": {"row_count": 1}}
    return path, entry, query


def test_selected_id_bbox_wkb_and_metadata_bounds_are_reproducible(tmp_path):
    path, entry, query = fixture(tmp_path)
    output = hints._query_hint(query, entry, path)
    assert output["ids"] == [7]
    assert output["selected_ids"][0]["source_wkb_geometry_type"] == 1
    assert output["selected_ids"][0]["source_wkb_xy_point_count"] == 1
    assert output["selected_ids"][0]["source_wkb_envelope"] == {
        "minx": 1., "miny": 2., "maxx": 1., "maxy": 2.}
    bounds = output["candidate_row_group_compressed_byte_bounds"]
    assert bounds["query_union_id_only"]["row_group_indices"] == [0]
    assert bounds["query_union_id_plus_spatial"]["row_group_indices"] == [0]
    assert bounds["whole_file_all_column_chunks"]["all_column_chunks_compressed_bytes_upper_bound"] > 0


@pytest.mark.parametrize("change", ["hash", "missing_id", "mapping"])
def test_refuses_wrong_bytes_missing_id_or_non_geo_covering_mapping(tmp_path, change):
    path, entry, query = fixture(tmp_path)
    if change == "hash":
        entry["sha256"] = "0" * 64
    elif change == "missing_id":
        query["ids"] = [8]
    else:
        table = pq.read_table(path)
        geo = json.loads(table.schema.metadata[b"geo"])
        geo["columns"]["geometry"]["covering"]["bbox"]["xmin"] = ["wrong", "xmin"]
        table = table.replace_schema_metadata({"geo": json.dumps(geo).encode()})
        pq.write_table(table, path)
        entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        entry["size_bytes"] = path.stat().st_size
    with pytest.raises(hints.HintError):
        hints._query_hint(query, entry, path)


def test_wkb_reader_rejects_z_and_trailing_bytes():
    point = b"\x01" + struct.pack("<I", 1) + struct.pack("<dd", 1., 2.)
    assert hints._wkb_info(point) == (1, 1, {"minx": 1., "miny": 2., "maxx": 1., "maxy": 2.})
    with pytest.raises(hints.HintError):
        hints._wkb_info(point + b"x")
    with pytest.raises(hints.HintError):
        hints._wkb_info(b"\x01" + struct.pack("<I", 1001) + struct.pack("<ddd", 1., 2., 3.))


def test_existing_output_is_refused_before_any_input_read(tmp_path):
    output = tmp_path / "hints.json"
    output.write_text("preserve me")
    with pytest.raises(SystemExit, match="2"):
        hints.main(["--plan", str(tmp_path / "absent-plan"), "--plan-sha256", "0" * 64,
                    "--controls", str(tmp_path / "absent-controls"), "--controls-sha256", "0" * 64,
                    "--output", str(output)])
    assert output.read_text() == "preserve me"


def test_expected_sha_pin_rejects_changed_json_bytes(tmp_path):
    path = tmp_path / "controls.json"
    path.write_text('{"schema_version": 1}\n')
    with pytest.raises(hints.HintError, match="SHA-256"):
        hints._read_pinned_json(path, "0" * 64, "controls")
