#!/usr/bin/env python3
"""Stream the pinned FFR File Geodatabase into deterministic GeoParquet."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import platform
import shutil
from importlib.metadata import version
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pyogrio
import shapely
from pyproj import CRS
from source_schema import verify_source_schema

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOCAL = ROOT / ".local" / "free-flowing-rivers"
GEOMETRY_TYPE_NAMES = {
    0: "Point",
    1: "LineString",
    2: "LinearRing",
    3: "Polygon",
    4: "MultiPoint",
    5: "MultiLineString",
    6: "MultiPolygon",
    7: "GeometryCollection",
}
LOCK = json.loads((HERE / "source-inspection.json").read_text())
LAYER = LOCK["layers"][0]["name"]
GEOMETRY = LOCK["layers"][0]["geometry_name"]
EXPECTED_PACKAGES = {
    "pyarrow": "23.0.1",
    "pyogrio": "0.11.1",
    "pyproj": "3.8.0",
    "shapely": "2.1.2",
    "PyYAML": "6.0.3",
}


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            sha.update(block)
    return sha.hexdigest()


def source_vfs(path: Path) -> str:
    return f"/vsizip/{path.resolve()}/{LOCK['gdb_path_in_zip']}"


def parquet_schema(schema: pa.Schema) -> pa.Schema:
    metadata = dict(schema.metadata or {})
    metadata.pop(b"geo", None)
    metadata[b"folia:source_doi"] = LOCK["article_doi"].encode()
    metadata[b"folia:source_sha256"] = LOCK["archive"]["sha256"].encode()
    return schema.with_metadata(metadata)


def owned_storage_bytes() -> int:
    total = 0
    for path in (LOCAL, HERE / ".venv"):
        if not path.exists():
            continue
        if path.is_file():
            total += path.stat().st_size
            continue
        total += sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
    return total


def observed_geometry_types(wkb: list[bytes | None]) -> Counter[str]:
    geometries = shapely.from_wkb(wkb)
    counts: Counter[str] = Counter()
    for type_id in shapely.get_type_id(geometries):
        if type_id >= 0:
            name = GEOMETRY_TYPE_NAMES[int(type_id)]
            counts[name] += 1
    return counts


def output_batch(batch: pa.RecordBatch, row_start: int) -> pa.RecordBatch:
    arrays = []
    fields = []
    for field, array in zip(batch.schema, batch.columns, strict=True):
        if field.name == GEOMETRY:
            # Store the source WKB bytes directly without an extension-type wrapper.
            fields.append(pa.field(GEOMETRY, pa.binary(), nullable=field.nullable))
            arrays.append(pa.array(array.to_pylist(), type=pa.binary()))
        else:
            fields.append(field)
            arrays.append(array)
    fields.append(pa.field("source_row", pa.int64(), nullable=False))
    arrays.append(pa.array(range(row_start, row_start + batch.num_rows), type=pa.int64()))
    return pa.RecordBatch.from_arrays(arrays, schema=pa.schema(fields))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit("Output exists; release directories are immutable")
    if not output.is_relative_to(LOCAL.resolve()):
        raise SystemExit("Output must stay under ignored .local/free-flowing-rivers storage")
    if source.stat().st_size != LOCK["archive"]["size_bytes"] or digest(source) != LOCK["archive"]["sha256"]:
        raise SystemExit("Source archive differs from the committed inspection pin")
    max_owned_bytes = 8 * 1024**3
    output_reserve = 5 * 1024**3
    if owned_storage_bytes() + output_reserve > max_owned_bytes:
        raise SystemExit("FFR-owned local files plus a 5 GiB output reserve would exceed the 8 GiB task budget")
    output.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(output.parent).free < 40 * 1024**3:
        raise SystemExit("At least 40 GiB of free disk is required before the local build")
    packages = {name: version(name) for name in EXPECTED_PACKAGES}
    if packages != EXPECTED_PACKAGES:
        raise SystemExit(f"Environment differs from the committed uv lock: {packages}")
    selected = next(layer for layer in LOCK["layers"] if layer["name"] == LAYER)
    if selected["feature_count"] != 8_477_883 or selected["crs"] != "EPSG:4326":
        raise SystemExit("Unexpected producer layer count or CRS")
    output.mkdir()
    shutil.copyfile(HERE / "dataset.yaml", output / "dataset.yaml")
    data_dir = output / "free-flowing-rivers"
    data_dir.mkdir()
    shutil.copyfile(HERE / "source-metadata.json", output / "source-metadata.json")
    shutil.copyfile(HERE / "source-inspection.json", output / "source-inspection.json")
    parquet_path = data_dir / "free-flowing-rivers-figshare-v1.parquet"
    bounds = selected["total_bounds"]
    row = 1
    null_counts: dict[str, int] = {}
    geometry_counts: Counter[str] = Counter()
    writer = None
    with pyogrio.open_arrow(
        source_vfs(source), layer=LAYER, return_fids=True, batch_size=4096, use_pyarrow=True
    ) as (meta, reader):
        if meta["crs"] != "EPSG:4326" or meta["geometry_name"] != GEOMETRY:
            raise SystemExit(f"Unexpected source Arrow metadata: {meta}")
        for batch in reader:
            if row == 1:
                verify_source_schema(batch.schema)
            for name, array in zip(batch.schema.names, batch.columns, strict=True):
                null_counts[name] = null_counts.get(name, 0) + array.null_count
            geometry_counts.update(observed_geometry_types(batch.column(GEOMETRY).to_pylist()))
            out_batch = output_batch(batch, row)
            if writer is None:
                schema = parquet_schema(out_batch.schema)
                writer = pq.ParquetWriter(
                    parquet_path,
                    schema,
                    compression="zstd",
                    compression_level=7,
                    use_dictionary=True,
                    write_statistics=True,
                    version="2.6",
                    data_page_version="2.0",
                )
            writer.write_batch(out_batch, row_group_size=4096)
            row += batch.num_rows
            if row % (4096 * 64) == 1:
                if owned_storage_bytes() > max_owned_bytes:
                    writer.close()
                    raise SystemExit("FFR-owned local files exceeded the 8 GiB task budget during build; partial artifact retained")
                if shutil.disk_usage(output.parent).free < 10 * 1024**3:
                    writer.close()
                    raise SystemExit("Free disk fell below 10 GiB; partial artifact retained")
    if writer is not None:
        if not geometry_counts:
            raise SystemExit("Source layer has no non-null geometries; cannot declare GeoParquet geometry types")
        geo = {
            "version": "1.1.0",
            "primary_column": GEOMETRY,
            "columns": {
                GEOMETRY: {
                    "encoding": "WKB",
                    "geometry_types": sorted(geometry_counts),
                    "crs": CRS.from_epsg(4326).to_json_dict(),
                    "bbox": bounds,
                }
            },
        }
        writer.add_key_value_metadata({b"geo": json.dumps(geo, separators=(",", ":")).encode()})
        writer.close()
    if row - 1 != selected["feature_count"]:
        raise SystemExit(f"Expected {selected['feature_count']} rows, wrote {row - 1}")
    (data_dir / "field-dictionary.json").write_text(
        json.dumps(LOCK["field_dictionary"], indent=2, ensure_ascii=False) + "\n"
    )
    manifest = {
        "status": "locally_built_not_prepared",
        "dataset": "free-flowing-rivers",
        "release": "figshare-v1-local-r1",
        "source": LOCK,
        "source_metadata_sha256": digest(HERE / "source-metadata.json"),
        "dataset_record_sha256": digest(output / "dataset.yaml"),
        "layer": LAYER,
        "records": row - 1,
        "source_attribute_fields_in_order": [f["name"] for f in selected["fields"]],
        "source_columns_in_order": [f["name"] for f in LOCK["field_dictionary"]],
        "null_counts": null_counts,
        "geometry_type_counts": dict(sorted(geometry_counts.items())),
        "bbox": bounds,
        "conversion_git_commit": __import__("subprocess").check_output(
            ["git", "rev-parse", "HEAD"], cwd=HERE.parents[1], text=True
        ).strip(),
        "environment": {"python": platform.python_version(), "packages": packages},
        "build_input_sha256": {
            name: digest(HERE / name)
            for name in (
                "build.py",
                "acquire.py",
                "inspect_source.py",
                "source_schema.py",
                "validate.py",
                "fault_tests.py",
                "pyproject.toml",
                "uv.lock",
                "dataset.yaml",
                "source-inspection.json",
                "source-metadata.json",
                "VALIDATION.md",
                "README.md",
            )
        },
        "assets": {
            "free-flowing-rivers/free-flowing-rivers-figshare-v1.parquet": {
                "size_bytes": parquet_path.stat().st_size,
                "sha256": digest(parquet_path),
                "media_type": "application/vnd.apache.parquet",
                "records": row - 1,
                "columns": [f["name"] for f in LOCK["field_dictionary"]] + ["source_row"],
                "geometry_column": GEOMETRY,
                "geometry_types": sorted(geometry_counts),
                "crs": "EPSG:4326",
                "bbox": bounds,
                "schema": LOCK["field_dictionary"] + [
                    {"name": "source_row", "type": "int64", "nullable": False, "description": "One-based row ordinal in the producer layer stream.", "unit": "1", "source_field_metadata": {}}
                ],
            },
            "free-flowing-rivers/field-dictionary.json": {
                "size_bytes": (data_dir / "field-dictionary.json").stat().st_size,
                "sha256": digest(data_dir / "field-dictionary.json"),
            },
        },
        "limitations": [
            "Exact conversion fidelity to the pinned producer archive only; scientific accuracy not assessed.",
            "Source assessment is static and based on data assembled circa 2017.",
            "No display derivative or public hosting is included.",
        ],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"records": row - 1, "output": str(output), "parquet_bytes": parquet_path.stat().st_size}, indent=2))


if __name__ == "__main__":
    main()
