"""Pin the Arrow-decoded File Geodatabase field schema to inspection evidence."""
from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa

HERE = Path(__file__).resolve().parent
LOCK = json.loads((HERE / "source-inspection.json").read_text())
GEOMETRY = LOCK["layers"][0]["geometry_name"]


def verify_source_schema(schema: pa.Schema) -> None:
    observed = []
    for field in schema:
        observed.append(
            {
                "name": field.name,
                "type": "MultiLineString" if field.name == GEOMETRY else str(field.type),
                "nullable": field.nullable,
                "description": next(item["description"] for item in LOCK["field_dictionary"] if item["name"] == field.name),
                "unit": next(item["unit"] for item in LOCK["field_dictionary"] if item["name"] == field.name),
                "source_field_metadata": {k.decode(): v.decode() for k, v in (field.metadata or {}).items()},
            }
        )
    expected = LOCK["field_dictionary"]
    if observed != expected:
        raise ValueError("Current Arrow source field order/types/nullability/metadata differs from pinned inspection")
