"""Locate the single canonical record for an ID across discovery and build roots."""
from __future__ import annotations

from pathlib import Path
import re

RECORD_ROOTS = ("candidates", "datasets")


def _area(root: Path, name: str) -> Path:
    area = root / name
    if root.is_symlink() or area.is_symlink():
        raise ValueError(f"Symlink record root is not allowed: {area}")
    return area


def _record_file(path: Path) -> bool:
    if path.parent.is_symlink() or path.is_symlink():
        raise ValueError(f"Symlink record path is not allowed: {path}")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", path.parent.name):
        raise ValueError(f"Invalid dataset ID: {path.parent.name}")
    return path.is_file()


def record_paths(root: Path) -> list[Path]:
    """Discover both roots in ID order; copying instead of moving is an error."""
    found = {}
    for name in RECORD_ROOTS:
        for path in sorted(_area(root, name).glob("*/dataset.yaml")):
            if not _record_file(path):
                raise ValueError(f"Canonical record must be a regular file: {path}")
            record_id = path.parent.name
            if record_id in found:
                raise ValueError(f"Duplicate dataset ID across record roots: {record_id}")
            found[record_id] = path
    return [found[key] for key in sorted(found)]


def record_path(root: Path, record_id: str) -> Path:
    """Resolve an existing record without guessing its lifecycle location."""
    if not isinstance(record_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", record_id):
        raise ValueError(f"Invalid dataset ID: {record_id!r}")
    matches = []
    for name in RECORD_ROOTS:
        path = _area(root, name) / record_id / "dataset.yaml"
        if _record_file(path):
            matches.append(path)
    if len(matches) > 1:
        raise ValueError(f"Duplicate dataset ID across record roots: {record_id}")
    if not matches:
        raise ValueError(f"Missing canonical record: {record_id}")
    return matches[0]
