#!/usr/bin/env python3
"""Independent, bounded-memory source and MVT oracle for GRWL width points.

This module deliberately does not import the overview producer. The full source
is projected with PROJ, externally sorted with DuckDB, and compared with every
selected sample. Every overview tile is then decoded and compared with buffered
copies derived independently from those samples.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import gzip
import hashlib
import json
import math
import mmap
from pathlib import Path
import shutil
import tempfile
import threading

import duckdb
import mapbox_vector_tile
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from pmtiles.reader import all_tiles
from pmtiles.tile import Compression, TileType, deserialize_header, zxy_to_tileid
from pyproj import Transformer
import shapely

ROOT = Path(__file__).resolve().parents[2]
CRITERIA = ROOT / "research/grwl-width-overview-20261106/criteria.json"
Q = 1 << 28
EXTENT = 4096
BUFFER = 32
BATCH = 32768
HALF_WORLD_M = math.pi * 6378137.0
WORLD_M = 2 * HALF_WORLD_M
MAX_LAT = math.degrees(math.atan(math.sinh(math.pi)))
FIELDS = ("cell", "feature_id", "width_m", "width_valid", "qx", "qy", "longitude", "latitude")
SAMPLE_SCHEMA = pa.schema([
    pa.field("cell", pa.uint64()), pa.field("feature_id", pa.uint64()),
    pa.field("width_m", pa.int64()), pa.field("width_valid", pa.bool_()),
    pa.field("qx", pa.uint32()), pa.field("qy", pa.uint32()),
    pa.field("longitude", pa.float64()), pa.field("latitude", pa.float64()),
])
OCCURRENCE_SCHEMA = pa.schema([
    pa.field("tileid", pa.uint64()), pa.field("feature_id", pa.uint64()),
    pa.field("width_m", pa.int64()), pa.field("width_valid", pa.bool_()),
    pa.field("x", pa.int32()), pa.field("y", pa.int32()),
])


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def source_anchors(wkb: list[bytes]) -> tuple[np.ndarray, np.ndarray]:
    """First coordinate in each source geometry, including multipart empties."""
    geometries = shapely.from_wkb(wkb)
    require(len(geometries) == len(wkb), "source geometry count changed")
    kind = shapely.get_type_id(geometries)
    require(bool(np.isin(kind, [1, 5]).all()), "source has non-LineString geometry")
    coordinates, owners = shapely.get_coordinates(geometries, return_index=True)
    first = np.searchsorted(owners, np.arange(len(wkb)))
    require(bool((first < len(owners)).all()) and bool(np.array_equal(owners[first], np.arange(len(wkb)))),
            "source contains an empty line geometry")
    anchors = coordinates[first, :2]
    require(bool(np.isfinite(anchors).all()), "nonfinite source anchor")
    lon, lat = anchors[:, 0], anchors[:, 1]
    require(bool(((lon >= -180) & (lon <= 180) & (lat >= -90) & (lat <= 90)).all()),
            "source anchor outside longitude/latitude bounds")
    return lon, lat


def project_q(lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """Use independent PROJ coordinates to place anchors on the 28-bit lattice."""
    clamped = np.clip(lat, -MAX_LAT, MAX_LAT)
    east, north = Transformer.from_crs(4326, 3857, always_xy=True).transform(lon, clamped)
    x = (east + HALF_WORLD_M) / WORLD_M
    y = (HALF_WORLD_M - north) / WORLD_M
    qx_unwrapped = np.clip(np.floor(x * Q + 0.5), 0, Q).astype(np.uint64)
    qy = np.clip(np.floor(y * Q + 0.5), 0, Q).astype(np.uint32)
    qx = (qx_unwrapped % Q).astype(np.uint32)
    dx = np.abs(qx_unwrapped.astype(np.float64) * WORLD_M / Q - x * WORLD_M)
    dy = np.abs(qy.astype(np.float64) * WORLD_M / Q - y * WORLD_M)
    return qx, qy, float(np.max(np.hypot(dx, dy), initial=0.0))


def cells(qx: np.ndarray, qy: np.ndarray, zoom: int) -> np.ndarray:
    shift = 28 - (10 + zoom)
    n = 1024 << zoom
    return (np.minimum(qy.astype(np.uint64), Q - 1) >> shift) * n + (qx.astype(np.uint64) >> shift)


def validate_sample(path: Path, zoom: int) -> int:
    require(path.is_file() and not path.is_symlink(), f"missing/unsafe sample {path}")
    parquet = pq.ParquetFile(path)
    require(parquet.schema_arrow.equals(SAMPLE_SCHEMA, check_metadata=False), f"sample schema differs at z{zoom}")
    previous = -1
    count = 0
    for batch in parquet.iter_batches(batch_size=BATCH, columns=FIELDS, use_threads=False):
        table = pa.Table.from_batches([batch])
        require(all(table[name].null_count == 0 for name in FIELDS if name != "width_m"),
                f"null required sample field at z{zoom}")
        cell = table["cell"].to_numpy()
        qx = table["qx"].to_numpy()
        qy = table["qy"].to_numpy()
        fid = table["feature_id"].to_numpy()
        valid = table["width_valid"].to_numpy()
        widths = table["width_m"].to_pylist()
        require(bool((cell[1:] > cell[:-1]).all()) and (len(cell) == 0 or int(cell[0]) > previous),
                f"sample cells are not strictly sorted at z{zoom}")
        require(bool(((fid > 0) & (fid <= (1 << 53) - 1)).all())
                and bool((qx < Q).all()) and bool((qy <= Q).all()),
                f"sample ID or q out of bounds at z{zoom}")
        require(bool(np.array_equal(cell, cells(qx, qy, zoom))), f"sample cell/q mismatch at z{zoom}")
        require(all(bool(v) == (w is not None and w > 0 and w != 1) for v, w in zip(valid, widths)),
                f"sample width validity mismatch at z{zoom}")
        lon = table["longitude"].to_numpy()
        lat = table["latitude"].to_numpy()
        require(bool(np.isfinite(lon).all()) and bool(np.isfinite(lat).all()), f"nonfinite sample anchor z{zoom}")
        expected_x, expected_y, error = project_q(lon, lat)
        require(bool(np.array_equal(qx, expected_x)) and bool(np.array_equal(qy, expected_y)) and error <= 0.3,
                f"sample anchor projection differs at z{zoom}")
        if len(cell):
            previous = int(cell[-1])
        count += len(cell)
    require(count > 0, f"empty sample z{zoom}")
    return count


def scope_for_manifest(source: Path, manifest: Path, criteria: dict) -> tuple[str, int, str, set[str]]:
    metadata = json.loads(manifest.read_text())
    source_hash = sha256(source)
    require(metadata.get("parquet_sha256") == source_hash, "source manifest SHA differs from source")
    rows = metadata.get("rows")
    require(type(rows) is int and rows > 0, "source manifest row count missing")
    tiles = metadata.get("tiles")
    require(isinstance(tiles, list), "source manifest tile list missing")
    names = [t.get("tile") if isinstance(t, dict) else t for t in tiles]
    require(all(isinstance(name, str) for name in names) and len(names) == len(set(names)),
            "source manifest tile names missing or duplicate")
    if source_hash == criteria["source"]["sha256"]:
        require(rows == criteria["source"]["rows"], "global source row count differs")
        return "global", rows, source_hash, set(names)
    for scope, key in (("pilot", "development_tiles"), ("heldout", "heldout_tiles")):
        if set(names) == set(criteria[key]) and len(names) == len(criteria[key]):
            return scope, rows, source_hash, set(names)
    raise ValueError("source scope is neither frozen global, pilot, nor heldout")


def resource_guard(task_root: Path, *, start: bool, criteria: dict) -> None:
    free = shutil.disk_usage(task_root).free
    floor = criteria["resources"]["minimum_start_free_gib" if start else "minimum_running_free_gib"] * (1 << 30)
    require(free >= floor, f"oracle disk free {free} below frozen floor {floor}")
    used = sum(path.stat().st_size for path in task_root.rglob("*") if path.is_file() and not path.is_symlink())
    maximum = criteria["resources"]["maximum_new_artifacts_gib"] * (1 << 30)
    require(used <= maximum, f"oracle task artifacts {used} exceed frozen ceiling {maximum}")


@contextmanager
def watch_resources(task_root: Path | None, criteria: dict, connection=None):
    """Check disk while synchronous DuckDB sorts or tile decoding are active."""
    if task_root is None:
        yield
        return
    stop = threading.Event()
    failures = []

    def monitor():
        while not stop.wait(2):
            try:
                resource_guard(task_root, start=False, criteria=criteria)
            except Exception as exc:
                failures.append(exc)
                if connection is not None:
                    connection.interrupt()
                return

    worker = threading.Thread(target=monitor, name="width-overview-resource-watch", daemon=True)
    worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join()
        if failures:
            raise failures[0]


def write_source_candidates(source: Path, path: Path, expected_rows: int,
                            tolerance_m: float, expected_tiles: set[str] | None = None,
                            guard=None) -> tuple[int, float]:
    parquet = pq.ParquetFile(source)
    require(parquet.metadata.num_rows == expected_rows, "source row count differs")
    required = {"feature_id", "width_m", "width_valid", "geometry"}
    if expected_tiles is not None:
        required.add("source_tile")
    require(required.issubset(parquet.schema_arrow.names), "source columns missing")
    count = 0
    largest_error = 0.0
    seen_tiles: set[str] = set()
    with pq.ParquetWriter(path, SAMPLE_SCHEMA, compression="zstd") as writer:
        for batch in parquet.iter_batches(batch_size=BATCH, columns=list(required), use_threads=False):
            table = pa.Table.from_batches([batch])
            lon, lat = source_anchors(table["geometry"].to_pylist())
            qx, qy, error = project_q(lon, lat)
            largest_error = max(largest_error, error)
            fid = table["feature_id"].to_numpy()
            widths = table["width_m"].to_pylist()
            valid = table["width_valid"].to_pylist()
            require(table["feature_id"].null_count == 0 and table["width_valid"].null_count == 0,
                    "source has null required ID or validity")
            if expected_tiles is not None:
                tile_names = set(table["source_tile"].to_pylist())
                require(tile_names <= expected_tiles, "source contains tile outside frozen regional scope")
                seen_tiles.update(tile_names)
            require(all(bool(v) == (w is not None and w > 0 and w != 1) for v, w in zip(valid, widths)),
                    "source width validity differs from sentinel rule")
            require(bool(((fid > 0) & (fid <= (1 << 53) - 1)).all()), "source feature ID is invalid")
            writer.write_table(pa.Table.from_arrays([
                pa.array(cells(qx, qy, 7), type=pa.uint64()), table["feature_id"].combine_chunks(),
                table["width_m"].combine_chunks(), table["width_valid"].combine_chunks(),
                pa.array(qx), pa.array(qy), pa.array(lon), pa.array(lat),
            ], schema=SAMPLE_SCHEMA))
            count += len(batch)
            if count % 1_000_000 < len(batch):
                print(json.dumps({"stage": "source", "records": count}), flush=True)
                if guard is not None:
                    guard()
    require(count == expected_rows, "source scan did not cover every record")
    if expected_tiles is not None:
        require(seen_tiles == expected_tiles, "regional source omits frozen tile")
    require(largest_error <= tolerance_m,
            "anchor lattice projection error exceeds gate")
    return count, largest_error


def external_winners(connection: duckdb.DuckDBPyConnection, input_path: Path, output_path: Path,
                     target_zoom: int = 7, guard=None) -> int:
    """External sort, then emit only the first priority row of each cell.

    DISTINCT ON and GROUP BY hold a global set of cells in DuckDB memory.
    The ordered stream needs only one input row group and one previous cell.
    """
    # Row-major cell IDs cannot be shifted by two: a 2x2 parent crosses row
    # boundaries. Derive the parent from its source lattice coordinate instead.
    shift = 28 - (10 + target_zoom)
    n = 1024 << target_zoom
    cell = f"(((LEAST(qy, {Q - 1}) >> {shift})::UBIGINT) * {n} + ((qx >> {shift})::UBIGINT))::UBIGINT"
    source = str(input_path).replace("'", "''")
    ordered_path = output_path.with_name(output_path.stem + "-ordered.parquet")
    require(not ordered_path.exists() and not output_path.exists(), "winner output already exists")
    target = str(ordered_path).replace("'", "''")
    connection.execute(f"""COPY (
        SELECT winner_cell AS cell, feature_id, width_m,
            width_valid, qx, qy, longitude, latitude
        FROM (SELECT {cell} AS winner_cell, feature_id, width_m, width_valid,
                     qx, qy, longitude, latitude FROM read_parquet('{source}'))
        ORDER BY winner_cell, width_valid DESC,
                 CASE WHEN width_valid THEN width_m ELSE NULL END DESC NULLS LAST,
                 feature_id ASC
    ) TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
    if guard is not None:
        guard()
    previous = -1
    selected = scanned = 0
    with pq.ParquetWriter(output_path, SAMPLE_SCHEMA, compression="zstd") as writer:
        for batch in pq.ParquetFile(ordered_path).iter_batches(batch_size=BATCH, columns=FIELDS, use_threads=False):
            table = pa.Table.from_batches([batch]).select(FIELDS).cast(SAMPLE_SCHEMA)
            indices = table["cell"].to_numpy()
            require(len(indices) > 0 and (indices[1:] >= indices[:-1]).all()
                    and int(indices[0]) >= previous, "external winner sort is not cell-ordered")
            first = np.flatnonzero(np.r_[True, indices[1:] != indices[:-1]])
            if int(indices[0]) == previous:
                first = first[1:]
            if len(first):
                writer.write_table(table.take(pa.array(first)), row_group_size=BATCH)
            selected += len(first)
            scanned += len(indices)
            previous = int(indices[-1])
            if guard is not None and scanned % 1_000_000 < len(indices):
                guard()
    ordered_path.unlink()
    require(selected > 0, "external winner sort produced no selected cells")
    return selected


def compare_tables(expected: Path, actual: Path, label: str) -> int:
    def rows(path: Path):
        pf = pq.ParquetFile(path)
        for batch in pf.iter_batches(batch_size=BATCH, columns=FIELDS, use_threads=False):
            for row in pa.Table.from_batches([batch]).to_pylist():
                yield tuple(row[name] for name in FIELDS)
    left, right = rows(expected), rows(actual)
    sentinel = object()
    count = 0
    while True:
        a, b = next(left, sentinel), next(right, sentinel)
        if a is sentinel and b is sentinel:
            return count
        require(a == b, f"{label} winner mismatch at row {count}: expected {a}, sample {b}")
        count += 1


def _occurrence_batch(tileid, fid, width, valid, x, y):
    return pa.Table.from_arrays([
        pa.array(tileid, type=pa.uint64()), pa.array(fid, type=pa.uint64()),
        pa.array(width, type=pa.int64()), pa.array(valid, type=pa.bool_()),
        pa.array(x, type=pa.int32()), pa.array(y, type=pa.int32()),
    ], schema=OCCURRENCE_SCHEMA)


def write_occurrences(samples: list[Path], output: Path, guard=None) -> int:
    count = 0
    with pq.ParquetWriter(output, OCCURRENCE_SCHEMA, compression="zstd") as writer:
        for zoom, path in enumerate(samples):
            tiles = 1 << zoom
            shift = 16 - zoom
            for batch in pq.ParquetFile(path).iter_batches(batch_size=BATCH, columns=FIELDS, use_threads=False):
                table = pa.Table.from_batches([batch])
                fid = table["feature_id"].to_numpy()
                qx, qy = table["qx"].to_numpy(), table["qy"].to_numpy()
                gx = ((qx.astype(np.uint64) + (1 << (shift - 1))) >> shift) % (EXTENT * tiles)
                gy = (qy.astype(np.uint64) + (1 << (shift - 1))) >> shift
                tx0 = gx // EXTENT
                ty0 = np.minimum(gy // EXTENT, tiles - 1)
                widths = table["width_m"].to_pylist()
                valid = table["width_valid"].to_pylist()
                for dx in (-1, 0, 1):
                    txraw = tx0.astype(np.int64) + dx
                    tx = txraw % tiles
                    lx = gx.astype(np.int64) - txraw * EXTENT
                    xok = (lx >= -BUFFER) & (lx <= EXTENT + BUFFER)
                    for dy in (-1, 0, 1):
                        ty = ty0.astype(np.int64) + dy
                        ly = gy.astype(np.int64) - ty * EXTENT
                        keep = np.flatnonzero(xok & (ty >= 0) & (ty < tiles)
                                              & (ly >= -BUFFER) & (ly <= EXTENT + BUFFER))
                        if not len(keep):
                            continue
                        # A z0 seam point has two distinct local placements
                        # (x=0 and x=4096) in the sole world tile.
                        ids = [zxy_to_tileid(zoom, int(tx[i]), int(ty[i])) for i in keep]
                        writer.write_table(_occurrence_batch(ids, fid[keep], [widths[i] for i in keep],
                                                             [valid[i] for i in keep], lx[keep], ly[keep]))
                        count += len(keep)
                        if count % 1_000_000 < len(keep) and guard is not None:
                            guard()
            if guard is not None:
                guard()
    return count


@contextmanager
def archive_tiles(path: Path):
    with path.open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as mapping:
        get = lambda offset, length: mapping[offset:offset + length]
        header = deserialize_header(get(0, 127))
        require(header["tile_type"] == TileType.MVT and header["tile_compression"] in (Compression.GZIP, Compression.NONE),
                "archive is not supported MVT")
        yield header, all_tiles(get)


def verify_tiles(archive: Path, expected: Path, criteria: dict, guard=None) -> dict:
    layer_name = criteria["overview"]["source_layer"]
    def expected_rows():
        for batch in pq.ParquetFile(expected).iter_batches(batch_size=BATCH, use_threads=False):
            for row in pa.Table.from_batches([batch]).to_pylist():
                yield row
    iterator = iter(expected_rows())
    next_row = next(iterator, None)
    by_zoom = {str(z): 0 for z in range(8)}
    points = 0
    maximum = 0
    with archive_tiles(archive) as (header, tiles):
        previous = -1
        total = 0
        for xyz, compressed in tiles:
            tileid = zxy_to_tileid(*xyz)
            require(tileid > previous, "archive tile coordinates duplicate or unordered")
            previous = tileid
            total += 1
            zoom = xyz[0]
            if zoom > 7:
                require(zoom <= 12, "archive has unexpected zoom")
                continue
            require(len(compressed) <= criteria["gates"]["maximum_compressed_overview_tile_bytes"],
                    f"overview tile exceeds byte gate: {xyz}")
            maximum = max(maximum, len(compressed))
            payload = gzip.decompress(compressed) if header["tile_compression"] == Compression.GZIP else compressed
            decoded = mapbox_vector_tile.decode(payload, default_options={"y_coord_down": True})
            require(set(decoded) == {layer_name}, f"unexpected overview layers at {xyz}")
            layer = decoded[layer_name]
            require(layer.get("extent") == EXTENT, f"overview extent differs at {xyz}")
            observed = {}
            for feature in layer["features"]:
                fid = feature.get("id")
                props = feature.get("properties", {})
                geometry = feature.get("geometry", {})
                require(type(fid) is int and geometry.get("type") == "Point", f"bad overview ID/geometry at {xyz}")
                require(set(props) == {"width_valid"} or set(props) == {"width_valid", "width_m"},
                        f"bad overview properties at {xyz}")
                require(type(props["width_valid"]) is bool and ("width_m" not in props or type(props["width_m"]) is int),
                        f"bad overview property types at {xyz}")
                x, y = geometry["coordinates"]
                key = (fid, x, y)
                require(key not in observed, f"duplicate overview point placement in tile {xyz}")
                observed[key] = (props.get("width_m"), props["width_valid"])
            expected_tile = {}
            while next_row is not None and next_row["tileid"] == tileid:
                key = (next_row["feature_id"], next_row["x"], next_row["y"])
                require(key not in expected_tile, f"oracle generated duplicate point placement at {xyz}")
                expected_tile[key] = (next_row["width_m"], next_row["width_valid"])
                next_row = next(iterator, None)
            require(bool(expected_tile), f"unexpected empty overview tile at {xyz}")
            require(observed == expected_tile, f"decoded overview tile differs from source-derived points at {xyz}")
            by_zoom[str(zoom)] += 1
            points += len(observed)
            if by_zoom[str(zoom)] % 100 == 0 and guard is not None:
                guard()
        require(total == header["addressed_tiles_count"], "archive tile directory count differs")
    require(next_row is None and all(by_zoom.values()), "missing expected overview tile or empty zoom")
    return {"tiles_by_zoom": by_zoom, "point_occurrences": points, "maximum_compressed_tile_bytes": maximum}


def verify(source: Path, source_manifest: Path, overview: Path, output: Path,
           task_root: Path, native_lock: Path) -> dict:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite immutable verifier receipt: {output}")
    result = {"schema_version": 1, "status": "running", "verifier_sha256": sha256(Path(__file__))}
    try:
        criteria = json.loads(CRITERIA.read_text())
        task_root.mkdir(parents=True, exist_ok=True)
        resource_guard(task_root, start=True, criteria=criteria)
        scope, expected_rows, source_hash, frozen_tiles = scope_for_manifest(source, source_manifest, criteria)
        archive = overview / "overview.pmtiles"
        samples = [overview / "samples" / f"z{z}.parquet" for z in range(8)]
        require(source.is_file() and source.stat().st_size > 0 and archive.is_file(), "source or archive missing")
        result.update(scope=scope, source_sha256=source_hash,
                      source_manifest_sha256=sha256(source_manifest), archive_sha256=sha256(archive),
                      archive_size_bytes=archive.stat().st_size, criteria_sha256=sha256(CRITERIA),
                      samples_sha256={str(z): sha256(p) for z, p in enumerate(samples)})
        build = json.loads((overview / "build.json").read_text())
        require(build.get("status") == "built_unvalidated" and build.get("source_sha256") == source_hash
                and build.get("source_manifest_sha256") == result["source_manifest_sha256"]
                and build.get("criteria_sha256") == result["criteria_sha256"]
                and build.get("rows") == expected_rows, "overview build receipt differs from source/criteria")
        artifacts = build.get("artifacts")
        require(isinstance(artifacts, dict), "overview build artifact inventory missing")
        for relative, identity in artifacts.items():
            path = overview / relative
            require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(overview.resolve()),
                    f"unsafe or missing overview artifact {relative}")
            require(identity.get("sha256") == sha256(path) and identity.get("size_bytes") == path.stat().st_size,
                    f"overview artifact identity differs: {relative}")
        require(artifacts.get("overview.pmtiles", {}).get("sha256") == result["archive_sha256"]
                and all(artifacts.get(f"samples/z{z}.parquet", {}).get("sha256") == result["samples_sha256"][str(z)]
                        for z in range(8)), "overview archive or samples absent from build inventory")
        sample_counts = {str(z): validate_sample(path, z) for z, path in enumerate(samples)}
        require([entry.get("selected_observations") for entry in build.get("per_zoom", [])]
                == [sample_counts[str(z)] for z in range(8)], "build selected counts differ from samples")
        require(native_lock.parent.is_dir(), "shared native lock parent is missing")
        with native_lock.open("a") as reservation:
            fcntl.flock(reservation, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with tempfile.TemporaryDirectory(prefix="width-overview-oracle-", dir=task_root) as temporary:
                source_rows, projection_error, occurrence_count, tiles = _verify_heavy(
                    source, samples, archive, sample_counts, expected_rows, criteria, Path(temporary),
                    frozen_tiles if scope != "global" else None, task_root)
            fcntl.flock(reservation, fcntl.LOCK_UN)
        resource_guard(task_root, start=False, criteria=criteria)
        require([entry.get("tiles") for entry in build["per_zoom"]] == [tiles["tiles_by_zoom"][str(z)] for z in range(8)],
                "build tile counts differ from decoded archive")
        require(sum(entry.get("encoded_occurrences_with_buffers", -1) for entry in build["per_zoom"])
                == occurrence_count, "build buffered occurrence count differs")
        result.update(status="passed", source_records=source_rows, maximum_projection_error_m=projection_error,
                      selected_by_zoom=sample_counts, expected_point_occurrences=occurrence_count, **tiles)
    except Exception as exc:
        result.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x") as stream:
            json.dump(result, stream, indent=2, sort_keys=True)
            stream.write("\n")
        raise
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return result


def _verify_heavy(source: Path, samples: list[Path], archive: Path, sample_counts: dict,
                  expected_rows: int, criteria: dict, temporary: Path,
                  frozen_tiles: set[str] | None = None, task_root: Path | None = None):
    temporary = Path(temporary)
    guard = (lambda: resource_guard(task_root, start=False, criteria=criteria)) if task_root else None
    candidates = temporary / "source-candidates.parquet"
    source_rows, projection_error = write_source_candidates(
        source, candidates, expected_rows, criteria["gates"]["independent_anchor_projection_tolerance_m"],
        frozen_tiles, guard)
    if guard:
        guard()
    connection = duckdb.connect(str(temporary / "sort.duckdb"))
    try:
        connection.execute("SET memory_limit='1GB'")
        connection.execute("SET threads=2")
        connection.execute("SET temp_directory=?", [str(temporary / "spill")])
        with watch_resources(task_root, criteria, connection):
            expected = temporary / "winners-z7.parquet"
            external_winners(connection, candidates, expected, guard=guard)
            if guard:
                guard()
            require(compare_tables(expected, samples[7], "z7 source") == sample_counts["7"], "z7 count differs")
            candidates.unlink()
            expected.unlink()
            for z in range(6, -1, -1):
                expected = temporary / f"winners-z{z}.parquet"
                external_winners(connection, samples[z + 1], expected, target_zoom=z, guard=guard)
                require(compare_tables(expected, samples[z], f"z{z} coarsening") == sample_counts[str(z)],
                        f"z{z} count differs")
                expected.unlink()
            occurrences = temporary / "occurrences.parquet"
            occurrence_count = write_occurrences(samples, occurrences, guard)
            ordered = temporary / "ordered-occurrences.parquet"
            src = str(occurrences).replace("'", "''")
            dst = str(ordered).replace("'", "''")
            connection.execute(f"COPY (SELECT * FROM read_parquet('{src}') ORDER BY tileid, feature_id) TO '{dst}' (FORMAT PARQUET, COMPRESSION ZSTD)")
            if guard:
                guard()
            occurrences.unlink()
            tiles = verify_tiles(archive, ordered, criteria, guard)
            require(tiles["point_occurrences"] == occurrence_count, "tile occurrence count differs")
            return source_rows, projection_error, occurrence_count, tiles
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--overview", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--task-root", type=Path, required=True)
    parser.add_argument("--native-lock", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.source, args.source_manifest, args.overview, args.output,
                            args.task_root, args.native_lock), sort_keys=True))


if __name__ == "__main__":
    main()
