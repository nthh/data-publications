"""Build the complete LakeATLAS v1.0 analytic GeoParquet layers."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.metadata
import json
import resource
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pyogrio
import pyproj
import shapely

from source import EXPECTED_LAYERS, FILES, acquire, digest, verified_file, zip_inventory

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SOURCE_NAME = "LakeATLAS_Data_v10.gdb.zip"
CACHE_DEFAULT = REPO / ".local/lakeatlas/source"
RELEASE_NAME = "lakeatlas-v1.0-r1"
BATCH_SIZE = 1024
GEOMETRY_BATCH_SIZE = 128
ROW_GROUP_SIZE = 4096
BBOX_FIELDS = ["xmin", "ymin", "xmax", "ymax"]


def json_write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return digest(path, "sha256")


def peak_rss_bytes() -> int:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak if sys.platform == "darwin" else peak * 1024)


def source_uri(source: Path) -> str:
    return "/vsizip/" + str(source.resolve())


def py_type(value: Any) -> dict[str, str]:
    return {"arrow": str(value.type), "nullable": str(value.nullable).lower(),
            "metadata": {k.decode("utf-8"): v.decode("utf-8") for k, v in (value.metadata or {}).items()}}


def inspect_source(source: Path, verify_crc: bool = True) -> dict[str, Any]:
    source = source.resolve()
    pin = verified_file(source, FILES[SOURCE_NAME])
    zipinfo = zip_inventory(source) if verify_crc else None
    if zipinfo and zipinfo["total_uncompressed_bytes"] != 3_061_068_949:
        raise ValueError("ZIP uncompressed byte total differs from pinned producer archive")
    uri = source_uri(source)
    discovered = {str(name): str(geom) for name, geom in pyogrio.list_layers(uri)}
    if discovered != {name: spec["geometry"] for name, spec in EXPECTED_LAYERS.items()}:
        raise ValueError(f"Source layer inventory differs: {discovered}")
    layers = {}
    for name, spec in EXPECTED_LAYERS.items():
        info = pyogrio.read_info(uri, layer=name)
        if info["features"] != spec["rows"] or info["geometry_type"] != spec["geometry"]:
            raise ValueError(f"Layer count or geometry type changed: {name}")
        if not pyproj.CRS.from_user_input(info["crs"]).equals(pyproj.CRS.from_epsg(4326), ignore_axis_order=True):
            raise ValueError(f"Unexpected CRS in {name}: {info['crs']}")
        with pyogrio.open_arrow(uri, layer=name, use_pyarrow=True, return_fids=True, batch_size=1) as (meta, reader):
            schema = reader.schema
            if meta["geometry_name"] not in schema.names or "Hylak_id" not in schema.names:
                raise ValueError(f"Expected native ID and WKB geometry not found: {name}")
            if not pa.types.is_binary(schema.field(meta["geometry_name"]).type):
                raise ValueError(f"Expected WKB binary geometry: {name}")
        if info["fid_column"] != spec["fid_field"] or len([f for f in schema if f.name != meta["geometry_name"]]) != spec["fields"] + 1:
            raise ValueError(f"Source field count differs: {name}")
        layers[name] = {
            "name": name,
            "geometry_type": info["geometry_type"],
            "source_geometry_field": meta["geometry_name"],
            "feature_count": info["features"],
            "fid_column": info["fid_column"],
            "native_fid_type": str(schema.field(info["fid_column"]).type),
            "attribute_field_count": spec["fields"],
            "output_source_field_count": spec["fields"] + 1,
            "crs": "EPSG:4326",
            "extent": [float(v) for v in info["total_bounds"]],
            "fields": [
                {"name": f.name, **py_type(f)} for f in schema if f.name != meta["geometry_name"]
            ],
            "geometry_arrow_type": str(schema.field(meta["geometry_name"]).type),
        }
    documents = {}
    for filename, spec in FILES.items():
        if filename != SOURCE_NAME:
            documents[filename] = verified_file(source.parent / filename, spec)
    return {
        "producer": "HydroSHEDS / HydroATLAS",
        "figshare_article": "https://api.figshare.com/v2/articles/19312001",
        "doi": "10.6084/m9.figshare.19312001.v1",
        "release": "LakeATLAS version 1.0",
        "collective_database_license": "CC-BY-4.0",
        "attribute_column_licenses": ["CC-BY-4.0", "ODbL-1.0"],
        "source_documents": documents,
        "source_file": {"name": SOURCE_NAME, **pin},
        "zip_inventory": zipinfo,
        "layers": layers,
    }


def output_schema(source_schema: pa.Schema, geometry_name: str, source_info: dict[str, Any], bbox: list[float]) -> pa.Schema:
    fields = [pa.field("geometry" if f.name == geometry_name else f.name, f.type, f.nullable, f.metadata)
              for f in source_schema]
    layer_info = source_info["layers"][source_info["active_layer"]]
    fields.append(pa.field("bbox", pa.struct([pa.field(name, pa.float64(), nullable=True) for name in BBOX_FIELDS])))
    geo = {
        "version": "1.1.0",
        "primary_column": "geometry",
        "columns": {
            "geometry": {
                "encoding": "WKB",
                "geometry_types": [layer_info["geometry_type"]],
                "crs": pyproj.CRS.from_epsg(4326).to_json_dict(),
                "bbox": bbox,
                "covering": {"bbox": {name: ["bbox", name] for name in BBOX_FIELDS}},
            }
        },
    }
    metadata = {
        b"geo": json.dumps(geo, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(),
        b"folia:producer": b"HydroSHEDS / HydroATLAS",
        b"folia:source_doi": b"10.6084/m9.figshare.19312001.v1",
        b"folia:source_sha256": source_info["source_file"]["sha256"].encode(),
        b"folia:source_layer": layer_info["name"].encode(),
    }
    return pa.schema(fields, metadata=metadata)


def native_table(batch: pa.RecordBatch, geometry_name: str) -> pa.Table:
    names = ["geometry" if name == geometry_name else name for name in batch.schema.names]
    return pa.Table.from_batches([batch.rename_columns(names)])


GEOMETRY_TYPE_NAMES = {0: "Point", 1: "LineString", 2: "LinearRing", 3: "Polygon", 4: "MultiPoint", 5: "MultiLineString", 6: "MultiPolygon", 7: "GeometryCollection"}


def bounds_for(wkb: pa.Array) -> tuple[np.ndarray, np.ndarray, Counter[str]]:
    geoms = shapely.from_wkb(wkb.to_numpy(zero_copy_only=False))
    bounds = shapely.bounds(geoms)
    nonempty = ~shapely.is_empty(geoms)
    finite = np.isfinite(bounds).all(axis=1)
    usable = nonempty & finite
    codes, counts = np.unique(shapely.get_type_id(geoms), return_counts=True)
    geom_types = Counter({GEOMETRY_TYPE_NAMES[int(code)]: int(count) for code, count in zip(codes, counts)})
    return bounds, usable, geom_types


def bbox_array(bounds: np.ndarray, usable: np.ndarray) -> pa.StructArray:
    children = [pa.array(bounds[:, i], mask=~usable, type=pa.float64()) for i in range(4)]
    return pa.StructArray.from_arrays(children, names=BBOX_FIELDS)


def layer_bounds(info: dict[str, Any]) -> list[float]:
    result = [float(v) for v in info["total_bounds"]]
    if not all(np.isfinite(result)):
        raise ValueError("Source layer has non-finite total bounds")
    return result


def ensure_clean_code() -> str:
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--", "datasets/lakeatlas"], cwd=REPO, text=True
    ).strip()
    if status:
        raise SystemExit("Commit the LakeATLAS workflow before building a release.")
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()


def build(source_cache: Path, output: Path) -> dict[str, Any]:
    pa.set_cpu_count(2)
    pa.set_io_thread_count(2)
    if output.exists():
        raise SystemExit("Use a new, empty versioned output directory; prior releases are immutable.")
    commit = ensure_clean_code()
    source = source_cache / SOURCE_NAME
    pinned = inspect_source(source, verify_crc=True)
    print(f"source verified; peak RSS={peak_rss_bytes():,} bytes", flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(output.parent).free < 40_000_000_000:
        raise RuntimeError("Less than 40 GB free on the shared machine; stop before writing output.")
    output.mkdir()
    (output / "lakeatlas").mkdir()
    (output / "lakeatlas" / "data").mkdir()
    shutil.copyfile(HERE / "dataset.yaml", output / "dataset.yaml")
    shutil.copyfile(source_cache / "LakeATLAS_Catalog_v10.pdf", output / "lakeatlas" / "LakeATLAS_Catalog_v10.pdf")
    shutil.copyfile(source_cache / "HydroATLAS_TechDoc_v10_1.pdf", output / "lakeatlas" / "HydroATLAS_TechDoc_v10_1.pdf")
    shutil.copyfile(HERE / "ATTRIBUTION.md", output / "ATTRIBUTION.md")
    shutil.copyfile(HERE / "README.md", output / "README.md")
    shutil.copyfile(HERE / "validation-plan.md", output / "validation-plan.md")
    evidence_dir = output / "evidence"
    evidence_dir.mkdir()
    for evidence_name in ["failed-build-first-attempt.json", "memory-profile-20261031.json"]:
        shutil.copyfile(HERE / "evidence" / evidence_name, evidence_dir / evidence_name)
    json_write(output / "source-manifest.json", pinned)

    source_info = {**pinned, "active_layer": None}
    assets: dict[str, dict[str, Any]] = {}
    for layer, expected in EXPECTED_LAYERS.items():
        source_info["active_layer"] = layer
        info = pyogrio.read_info(source_uri(source), layer=layer)
        bbox = layer_bounds(info)
        asset_name = "lakeatlas-polygons.parquet" if layer.endswith("_pol") else "lakeatlas-pour-points.parquet"
        asset_path = output / "lakeatlas" / "data" / asset_name
        rows = 0
        nulls: Counter[str] = Counter()
        layer_types: Counter[str] = Counter()
        pending_tables: list[pa.Table] = []
        pending_rows = 0
        next_progress = 100_000
        extent_min = np.array([np.inf, np.inf])
        extent_max = np.array([-np.inf, -np.inf])
        with pyogrio.open_arrow(source_uri(source), layer=layer, use_pyarrow=True, return_fids=True, batch_size=BATCH_SIZE) as (meta, reader):
            geometry_name = meta["geometry_name"]
            schema = output_schema(reader.schema, geometry_name, source_info, bbox)
            with pq.ParquetWriter(
                asset_path, schema, compression="zstd", compression_level=6,
                use_dictionary=True, write_statistics=True, version="2.6",
            ) as writer:
                print(f"opened writer for {layer}; peak RSS={peak_rss_bytes():,} bytes", flush=True)
                for batch in reader:
                    for offset in range(0, batch.num_rows, GEOMETRY_BATCH_SIZE):
                        feature_batch = batch.slice(offset, GEOMETRY_BATCH_SIZE)
                        table = native_table(feature_batch, geometry_name)
                        wkb = table["geometry"].chunk(0)
                        bounds, usable, geom_batch_types = bounds_for(wkb)
                        layer_types.update(geom_batch_types)
                        if usable.any():
                            extent_min = np.minimum(extent_min, bounds[usable, :2].min(axis=0))
                            extent_max = np.maximum(extent_max, bounds[usable, 2:].max(axis=0))
                        bbox_col = bbox_array(bounds, usable)
                        table = table.append_column("bbox", bbox_col).replace_schema_metadata(schema.metadata)
                        if table.schema != schema:
                            raise ValueError(f"Arrow schema changed during conversion for {layer}")
                        pending_tables.append(table)
                        pending_rows += feature_batch.num_rows
                        rows += feature_batch.num_rows
                        for field in feature_batch.schema:
                            nulls[field.name] += feature_batch.column(feature_batch.schema.get_field_index(field.name)).null_count
                        ids = table["Hylak_id"].chunk(0).to_numpy(zero_copy_only=False)
                        if ids.size and (ids < 0).any():
                            raise ValueError(f"Unexpected negative native Hylak_id in {layer}")
                        if pending_rows == ROW_GROUP_SIZE:
                            writer.write_table(pa.concat_tables(pending_tables), row_group_size=ROW_GROUP_SIZE)
                            pending_tables.clear()
                            pending_rows = 0
                        if rows >= next_progress:
                            print(f"{layer}: rows={rows:,}, peak RSS={peak_rss_bytes():,} bytes", flush=True)
                            next_progress += 100_000
                if pending_tables:
                    writer.write_table(pa.concat_tables(pending_tables), row_group_size=ROW_GROUP_SIZE)
                    pending_tables.clear()
                    pending_rows = 0
            print(f"closed writer for {layer}; peak RSS={peak_rss_bytes():,} bytes", flush=True)
        del writer, reader, meta, schema
        del batch, feature_batch, table, wkb, bounds, usable, geom_batch_types, bbox_col, ids
        pending_tables.clear()
        pa.default_memory_pool().release_unused()
        if set(layer_types) != {expected["geometry"]} or sum(layer_types.values()) != rows:
            raise ValueError(f"Actual geometry-type tally disagrees with layer/GeoParquet metadata for {layer}: {dict(layer_types)}")
        if rows != expected["rows"]:
            raise ValueError(f"Output count changed for {layer}: {rows}")
        output_extent = [float(extent_min[0]), float(extent_min[1]), float(extent_max[0]), float(extent_max[1])]
        if not all(np.isfinite(output_extent)):
            raise ValueError(f"Could not compute finite output extent for {layer}")
        # Producer layer bounds are used in GeoParquet metadata; confirm streamed WKB reports the same bounds.
        if not np.allclose(output_extent, bbox, rtol=0, atol=1e-12):
            raise ValueError(f"Streamed geometry bounds disagree with producer metadata for {layer}")
        pf = pq.ParquetFile(asset_path)
        print(f"opened Parquet metadata for {layer}; row_groups={pf.metadata.num_row_groups}, peak RSS={peak_rss_bytes():,} bytes", flush=True)
        geo = json.loads(pf.schema_arrow.metadata[b"geo"])
        if geo["columns"]["geometry"]["bbox"] != bbox:
            raise ValueError(f"GeoParquet bbox metadata not written for {layer}")
        assets[layer] = {
            "name": asset_name,
            "path": f"lakeatlas/data/{asset_name}",
            "size_bytes": asset_path.stat().st_size,
            "sha256": sha256(asset_path),
            "feature_count": rows,
            "extent": output_extent,
            "bbox": output_extent,
            "crs": "EPSG:4326",
            "geometry_type": expected["geometry"],
            "schema_fields": [f.name for f in pf.schema_arrow if f.name not in ("geometry", "bbox")],
            "null_counts": dict(sorted(nulls.items())),
            "geometry_types": dict(sorted(layer_types.items())),
            "row_groups": pf.metadata.num_row_groups,
            "row_group_size": ROW_GROUP_SIZE,
        }
        print(f"built {asset_name}: rows={rows:,}, bytes={asset_path.stat().st_size:,}, peak RSS={peak_rss_bytes():,} bytes", flush=True)
        del pf, geo, info
        pa.default_memory_pool().release_unused()
    peak_bytes = peak_rss_bytes()
    if peak_bytes >= 1_000_000_000:
        raise RuntimeError(f"Peak process memory exceeded the 1 GB limit: {peak_bytes:,} bytes")
    report = {
        "release": RELEASE_NAME,
        "peak_process_memory_bytes": peak_bytes,
        "created_from_commit": commit,
        "source_sha256": pinned["source_file"]["sha256"],
        "workflow_files": {name: sha256(HERE / name) for name in [
            "build.py", "source.py", "validate.py", "validate_worker.py", "test_faults.py", "pyproject.toml",
            "uv.lock", "dataset.yaml", "validation-plan.md", "ATTRIBUTION.md", "README.md",
            "evidence/failed-build-first-attempt.json", "evidence/memory-profile-20261031.json",
        ]},
        "tool_versions": {
            "python": sys.version.split()[0],
            "pyarrow": importlib.metadata.version("pyarrow"),
            "pyogrio": importlib.metadata.version("pyogrio"),
            "gdal": ".".join(map(str, pyogrio.__gdal_version__)),
            "shapely": shapely.__version__,
            "pyproj": pyproj.__version__,
        },
        "source_batch_size": BATCH_SIZE,
        "geometry_batch_size": GEOMETRY_BATCH_SIZE,
        "parquet_row_group_size": ROW_GROUP_SIZE,
        "layers": assets,
    }
    json_write(output / "build-manifest.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("acquire", help="download and verify pinned Figshare files")
    p.add_argument("--cache", type=Path, default=CACHE_DEFAULT)
    p = sub.add_parser("inspect", help="verify the source archive and print layer metadata")
    p.add_argument("--source-cache", type=Path, default=CACHE_DEFAULT)
    p.add_argument("--output", type=Path)
    p = sub.add_parser("build", help="stream both layers to a new GeoParquet release")
    p.add_argument("--source-cache", type=Path, default=CACHE_DEFAULT)
    p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "acquire":
        print(json.dumps(acquire(args.cache), indent=2))
    elif args.command == "inspect":
        report = inspect_source(args.source_cache / SOURCE_NAME)
        if args.output:
            json_write(args.output, report)
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        build(args.source_cache, args.output)


if __name__ == "__main__":
    main()
