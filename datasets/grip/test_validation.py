#!/usr/bin/env python3
"""Fault-test exact source comparison and PMTiles geometry error contracts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import unittest

import numpy as np
import pyarrow as pa
import shapely

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from tiles import geometry_error
from validate import compare_columns


def _source_fixture() -> pa.Table:
    """Independent tiny source-shaped Arrow table with IDs, nulls, floats and WKB."""
    geometries = [
        shapely.LineString([(0.0, 0.0), (1.0, 1.0)]),
        shapely.LineString([(2.0, 1.0), (3.0, 2.0)]),
        shapely.LineString([(4.0, 2.0), (5.0, 3.0)]),
    ]
    return pa.table({
        "OBJECTID": pa.array([101, 102, 103], type=pa.int64()),
        "nullable_measure": pa.array([7, None, -2], type=pa.int32()),
        "float_measure": pa.array([0.125, -0.0, float("nan")], type=pa.float64()),
        "geometry": pa.array([shapely.to_wkb(g, byte_order=1) for g in geometries], type=pa.binary()),
    })


def _assert_rejected(expected: pa.Table, actual: pa.Table, message: str) -> str:
    try:
        compare_columns(expected, actual)
    except ValueError as exc:
        if message not in str(exc):
            raise AssertionError(f"Rejected for the wrong reason: {exc}") from exc
        return str(exc)
    raise AssertionError("Deliberate source mutation was accepted")


def _tile_line_from_local(z: int, x: int, y: int, points: list[tuple[float, float]], extent: int = 4096):
    """Invert Web Mercator tile coordinates to WGS84, then build a source line."""
    scale = 2**z
    coordinates = []
    for px, py in points:
        world_x = x + px / extent
        world_y = y + py / extent
        lon = world_x / scale * 360.0 - 180.0
        mercator_y = np.pi * (1 - 2 * world_y / scale)
        lat = np.degrees(np.arctan(np.sinh(mercator_y)))
        coordinates.append((float(lon), float(lat)))
    return shapely.LineString(coordinates)


def case_identical_table_passes() -> dict:
    table = _source_fixture()
    compared = compare_columns(table, table)
    if compared != table.num_rows * len(table.column_names):
        raise AssertionError("Comparison cell count is not rows × columns")
    return {"compared_cells": compared}


def case_lost_row_is_rejected() -> dict:
    expected = _source_fixture()
    actual = expected.slice(0, expected.num_rows - 1)
    error = _assert_rejected(expected, actual, "Lost or extra rows")
    return {"rejection": error}


def case_duplicate_identifier_is_rejected() -> dict:
    expected = _source_fixture()
    actual = expected.set_column(0, "OBJECTID", pa.array([101, 101, 103], type=pa.int64()))
    error = _assert_rejected(expected, actual, "Source values changed: OBJECTID")
    return {"rejection": error}


def case_changed_attribute_is_rejected() -> dict:
    expected = _source_fixture()
    actual = expected.set_column(1, "nullable_measure", pa.array([7, None, -3], type=pa.int32()))
    error = _assert_rejected(expected, actual, "Source values changed: nullable_measure")
    return {"rejection": error}


def case_null_to_zero_is_rejected() -> dict:
    expected = _source_fixture()
    actual = expected.set_column(1, "nullable_measure", pa.array([7, 0, -2], type=pa.int32()))
    error = _assert_rejected(expected, actual, "Source null mask changed: nullable_measure")
    return {"rejection": error}


def case_signed_zero_bit_change_is_rejected() -> dict:
    expected = _source_fixture()
    actual = expected.set_column(2, "float_measure", pa.array([0.125, 0.0, float("nan")], type=pa.float64()))
    error = _assert_rejected(expected, actual, "Source floating bits changed: float_measure")
    return {"rejection": error}


def case_one_ulp_float_change_is_rejected() -> dict:
    expected = _source_fixture()
    changed = np.nextafter(0.125, 1.0)
    actual = expected.set_column(2, "float_measure", pa.array([changed, -0.0, float("nan")], type=pa.float64()))
    error = _assert_rejected(expected, actual, "Source floating bits changed: float_measure")
    return {"rejection": error, "changed_value": repr(changed)}


def case_changed_wkb_geometry_is_rejected() -> dict:
    expected = _source_fixture()
    changed = shapely.LineString([(0.0, 0.0), (1.0, 1.0000001)])
    wkb = pa.array([expected["geometry"][0].as_py(), shapely.to_wkb(changed, byte_order=1), expected["geometry"][2].as_py()], type=pa.binary())
    actual = expected.set_column(3, "geometry", wkb)
    error = _assert_rejected(expected, actual, "Source values changed: geometry")
    return {"rejection": error}


def case_tile_quantization_within_four_units_passes() -> dict:
    z, x, y, extent = 3, 4, 4, 4096
    source = _tile_line_from_local(z, x, y, [(800.24, 900.2), (801.49, 902.62), (804.21, 904.31)], extent)
    quantized = shapely.LineString([(800, 900), (801, 903), (804, 904)])
    error = geometry_error(source, quantized, z, x, y, extent)
    if error > 4.0:
        raise AssertionError(f"Sub-unit tile quantization exceeded four tile units: {error}")
    return {"maximum_error_tile_units": error, "limit_tile_units": 4.0}


def case_translated_tile_line_exceeds_four_units() -> dict:
    z, x, y, extent = 3, 4, 4, 4096
    source = _tile_line_from_local(z, x, y, [(800.24, 900.2), (801.49, 902.62), (804.21, 904.31)], extent)
    translated = shapely.LineString([(810, 900), (811, 903), (814, 904)])
    error = geometry_error(source, translated, z, x, y, extent)
    if error <= 4.0:
        raise AssertionError(f"Translated tile line stayed within four tile units: {error}")
    return {"maximum_error_tile_units": error, "limit_tile_units": 4.0}


FAULT_CASES = (
    ("identical_table_passes", case_identical_table_passes),
    ("lost_row_rejected", case_lost_row_is_rejected),
    ("duplicate_identifier_rejected", case_duplicate_identifier_is_rejected),
    ("changed_attribute_rejected", case_changed_attribute_is_rejected),
    ("null_to_zero_rejected", case_null_to_zero_is_rejected),
    ("signed_zero_bit_change_rejected", case_signed_zero_bit_change_is_rejected),
    ("one_ulp_float_change_rejected", case_one_ulp_float_change_is_rejected),
    ("changed_wkb_geometry_rejected", case_changed_wkb_geometry_is_rejected),
    ("tile_quantization_within_four_units", case_tile_quantization_within_four_units_passes),
    ("translated_tile_line_exceeds_four_units", case_translated_tile_line_exceeds_four_units),
)


def run_fault_cases() -> dict:
    cases = []
    for name, function in FAULT_CASES:
        try:
            details = function()
            cases.append({"name": name, "status": "passed", **details})
        except Exception as exc:
            cases.append({"name": name, "status": "failed", "error": f"{type(exc).__name__}: {exc}"})
    return {
        "status": "passed" if all(case["status"] == "passed" for case in cases) else "failed",
        "case_count": len(cases),
        "cases": cases,
        "scope": "Independent small Arrow fixtures and synthetic tile-coordinate geometries; no source archive or GEE is read.",
    }


class ValidationFaultTests(unittest.TestCase):
    def _assert_case(self, name: str):
        function = dict(FAULT_CASES)[name]
        function()

    def test_identical_table_passes(self):
        self._assert_case("identical_table_passes")

    def test_lost_row_is_rejected(self):
        self._assert_case("lost_row_rejected")

    def test_duplicate_identifier_is_rejected(self):
        self._assert_case("duplicate_identifier_rejected")

    def test_changed_attribute_is_rejected(self):
        self._assert_case("changed_attribute_rejected")

    def test_null_to_zero_is_rejected(self):
        self._assert_case("null_to_zero_rejected")

    def test_signed_zero_bit_change_is_rejected(self):
        self._assert_case("signed_zero_bit_change_rejected")

    def test_one_ulp_float_change_is_rejected(self):
        self._assert_case("one_ulp_float_change_rejected")

    def test_changed_wkb_geometry_is_rejected(self):
        self._assert_case("changed_wkb_geometry_rejected")

    def test_tile_quantization_stays_within_four_units(self):
        self._assert_case("tile_quantization_within_four_units")

    def test_translated_tile_line_exceeds_four_units(self):
        self._assert_case("translated_tile_line_exceeds_four_units")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True, help="write per-case JSON fault-test report")
    args = parser.parse_args()
    report = run_fault_cases()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
