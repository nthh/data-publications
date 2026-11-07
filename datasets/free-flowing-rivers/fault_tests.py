#!/usr/bin/env python3
"""Prove that the source-fidelity comparator rejects representative mutations."""
from __future__ import annotations

import argparse
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pyogrio

from validate import compare, source_vfs, LOCK, LAYER, GEOMETRY


def expect_rejected(name: str, source: pa.RecordBatch, changed: pa.RecordBatch, reason: str) -> None:
    try:
        compare(source, changed, 1)
    except ValueError as error:
        if reason not in str(error):
            raise AssertionError(f"{name} failed for wrong reason: {error}") from error
    else:
        raise AssertionError(f"{name} mutation was accepted")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--release", type=Path, required=True)
    args = parser.parse_args()
    parquet = args.release / "free-flowing-rivers/free-flowing-rivers-figshare-v1.parquet"
    with pyogrio.open_arrow(source_vfs(args.source), layer=LAYER, return_fids=True, batch_size=2, use_pyarrow=True) as (_, reader):
        source = next(reader)
    # Read only the first two rows so each injected defect stays within bounded memory.
    output = next(pq.ParquetFile(parquet).iter_batches(batch_size=2))
    compare(source, output, 1)

    expect_rejected("row removal", source, output.slice(0, 1), "row count changed")
    duplicate = output.take(pa.array([0, 0]))
    expect_rejected("row duplication", source, duplicate, "source field")

    field = "GOID"
    col_idx = output.schema.get_field_index(field)
    changed_values = pa.array([999999999, output.column(field)[1].as_py()], type=output.column(field).type)
    changed = output.set_column(col_idx, output.schema.field(field), changed_values)
    expect_rejected("attribute change", source, changed, f"source field {field}")

    null_values = pa.array([None, output.column(field)[1].as_py()], type=output.column(field).type)
    changed = output.set_column(col_idx, output.schema.field(field), null_values)
    expect_rejected("null mutation", source, changed, f"source field {field}")

    geom_idx = output.schema.get_field_index(GEOMETRY)
    geometries = output.column(GEOMETRY).to_pylist()
    first = bytearray(geometries[0])
    first[-1] ^= 1
    geometries[0] = bytes(first)
    changed = output.set_column(geom_idx, output.schema.field(GEOMETRY), pa.array(geometries, type=pa.binary()))
    expect_rejected("geometry WKB mutation", source, changed, "geometry WKB differs")
    print("5 mutation cases rejected for their intended reason")


if __name__ == "__main__":
    main()
