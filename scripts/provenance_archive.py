"""Hash-bound archive for reproducible access to historical Git file blobs."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Iterable

ARCHIVE_REL = Path("research/history-portability-20261106")
INDEX_NAME = "index.json"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_repo_path(path: str) -> str:
    if not isinstance(path, str) or "\\" in path:
        raise ValueError("Invalid repository path")
    p = PurePosixPath(path)
    if p.is_absolute() or not p.parts or ".." in p.parts or "." in p.parts:
        raise ValueError("Unsafe repository path")
    return p.as_posix()


def _archive_entries(root: Path) -> list[dict]:
    index_path = root / ARCHIVE_REL / INDEX_NAME
    if not index_path.is_file():
        return []
    index = json.loads(index_path.read_text())
    if index.get("schema_version") != 1 or not isinstance(index.get("files"), list):
        raise ValueError("Invalid provenance archive index")
    return index["files"]


def _matching_entry(root: Path, commit: str, path: str, expected_sha256: str | None) -> dict | None:
    matches = [entry for entry in _archive_entries(root)
               if entry.get("git_revision") == commit and entry.get("path") == path]
    if expected_sha256 is not None:
        matches = [entry for entry in matches if entry.get("sha256") == expected_sha256]
    if len(matches) > 1:
        hashes = {entry.get("sha256") for entry in matches}
        if len(hashes) != 1:
            raise ValueError(f"Ambiguous provenance archive binding: {commit}:{path}")
        return matches[0]
    return matches[0] if matches else None


def _read_snapshot(root: Path, entry: dict, commit: str, path: str) -> bytes:
    if entry.get("git_revision") != commit or entry.get("path") != path:
        raise ValueError("Provenance snapshot is bound to a different commit/path")
    digest = entry.get("sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Invalid provenance snapshot digest")
    if entry.get("blob") != f"blobs/{digest}":
        raise ValueError("Invalid provenance snapshot path")
    archive = (root / ARCHIVE_REL).resolve()
    blob = (archive / entry["blob"]).resolve()
    if not blob.is_relative_to(archive) or not blob.is_file():
        raise ValueError("Provenance snapshot is missing or unsafe")
    data = blob.read_bytes()
    if len(data) != entry.get("bytes") or sha256(data) != digest:
        raise ValueError("Provenance snapshot failed its size or SHA-256 check")
    return data


def resolve_blob(root: str | Path, commit: str, path: str,
                 expected_sha256: str | None = None) -> bytes:
    """Return exact commit:path bytes, using an indexed snapshot only if Git lacks commit.

    If Git contains the commit, its object is authoritative: missing paths and hash
    mismatches fail instead of being hidden by the portable archive.
    """
    root = Path(root).resolve()
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Invalid historical Git revision")
    path = safe_repo_path(path)
    if expected_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("Invalid expected SHA-256")

    entry = _matching_entry(root, commit, path, expected_sha256)
    commit_exists = subprocess.run(["git", "cat-file", "-e", f"{commit}^{{commit}}"],
                                   cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if commit_exists:
        result = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=root,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        if result.returncode:
            raise ValueError(f"Historical Git path is unavailable: {commit}:{path}")
        data = result.stdout
        actual = sha256(data)
        if expected_sha256 is not None and actual != expected_sha256:
            raise ValueError("Historical Git blob does not match expected SHA-256")
        if entry is not None and actual != entry.get("sha256"):
            raise ValueError("Available Git blob conflicts with archived snapshot")
        return data

    if entry is None:
        raise ValueError(f"No hash-bound historical snapshot for {commit}:{path}")
    data = _read_snapshot(root, entry, commit, path)
    if expected_sha256 is not None and sha256(data) != expected_sha256:
        raise ValueError("Historical snapshot does not match expected SHA-256")
    return data


def export_archive(root: str | Path, bindings: Iterable[tuple[str, str]]) -> dict:
    """Export exact commit/path pairs to the portable archive; never exports working files."""
    root = Path(root).resolve()
    entries_by_key: dict[tuple[str, str], dict] = {}
    blobs: dict[str, bytes] = {}
    for commit, raw_path in bindings:
        path = safe_repo_path(raw_path)
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("Invalid historical Git revision")
        result = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=root,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        if result.returncode:
            raise ValueError(f"Cannot export historical Git path {commit}:{path}")
        data = result.stdout
        digest = sha256(data)
        key = (commit, path)
        record = {"git_revision": commit, "path": path, "sha256": digest,
                  "bytes": len(data), "blob": f"blobs/{digest}"}
        previous = entries_by_key.get(key)
        if previous is not None and previous != record:
            raise ValueError(f"Conflicting historical Git binding {commit}:{path}")
        entries_by_key[key] = record
        blobs[digest] = data

    archive = root / ARCHIVE_REL
    blob_dir = archive / "blobs"
    blob_dir.mkdir(parents=True, exist_ok=True)
    for digest, data in blobs.items():
        target = blob_dir / digest
        if target.exists() and target.read_bytes() != data:
            raise ValueError(f"Content-addressed blob collision: {digest}")
        target.write_bytes(data)
    index = {"schema_version": 1, "files": sorted(entries_by_key.values(),
             key=lambda e: (e["git_revision"], e["path"]))}
    (archive / INDEX_NAME).write_text(json.dumps(index, indent=2) + "\n")
    return {"entries": len(index["files"]), "unique_blobs": len(blobs),
            "bytes": sum(len(data) for data in blobs.values())}
