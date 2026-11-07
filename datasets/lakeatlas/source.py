"""Pinned LakeATLAS v1.0 source acquisition and inspection helpers."""
from __future__ import annotations

import hashlib
import json
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

ARTICLE_ID = 19312001
SOURCE_ARCHIVE = "LakeATLAS_Data_v10.gdb.zip"
FILES = {
    "LakeATLAS_Data_v10.gdb.zip": {
        "id": 35959544,
        "size": 1_530_962_499,
        "md5": "952e0724afc96d3a5899f08935d4a094",
    },
    "LakeATLAS_Catalog_v10.pdf": {
        "id": 35959535,
        "size": 54_055_742,
        "md5": "dfb3501640ed034360486a8304d00d8b",
    },
    "HydroATLAS_TechDoc_v10_1.pdf": {
        "id": 35959532,
        "size": 3_656_999,
        "md5": "f37085c99a987752a37d8327c0a96922",
    },
}
EXPECTED_LAYERS = {
    "LakeATLAS_v10_pol": {"geometry": "MultiPolygon", "rows": 1_427_688, "fields": 307, "fid_field": "OBJECTID"},
    "LakeATLAS_v10_pnt": {"geometry": "Point", "rows": 1_427_688, "fields": 305, "fid_field": "OBJECTID"},
}


def digest(path: Path, algorithm: str) -> str:
    h = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verified_file(path: Path, spec: dict[str, Any]) -> dict[str, Any]:
    if path.stat().st_size != spec["size"]:
        raise ValueError(f"Unexpected source size for {path.name}: {path.stat().st_size}")
    md5 = digest(path, "md5")
    if md5 != spec["md5"]:
        raise ValueError(f"Figshare MD5 mismatch for {path.name}: {md5}")
    return {"size_bytes": path.stat().st_size, "md5": md5, "sha256": digest(path, "sha256")}


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".partial")
    request = urllib.request.Request(url, headers={"User-Agent": "Folia LakeATLAS local release builder"})
    with urllib.request.urlopen(request, timeout=60) as response, partial.open("wb") as out:
        while block := response.read(8 * 1024 * 1024):
            out.write(block)
        out.flush()
    partial.replace(destination)


def acquire(cache: Path) -> dict[str, Any]:
    """Acquire current Figshare record files, requiring this exact immutable v1 article."""
    cache.mkdir(parents=True, exist_ok=True)
    api_url = f"https://api.figshare.com/v2/articles/{ARTICLE_ID}"
    request = urllib.request.Request(api_url, headers={"User-Agent": "Folia LakeATLAS local release builder"})
    with urllib.request.urlopen(request, timeout=60) as response:
        article = json.load(response)
    if article.get("id") != ARTICLE_ID or article.get("version") != 1:
        raise ValueError("Figshare article identity/version differs from the pinned LakeATLAS v1.0 record")
    if article.get("doi") != "10.6084/m9.figshare.19312001.v1":
        raise ValueError("Unexpected Figshare DOI")
    license_name = (article.get("license") or {}).get("name")
    if license_name != "CC BY 4.0":
        raise ValueError(f"Unexpected Figshare license: {license_name}")
    remote = {item["name"]: item for item in article.get("files", [])}
    for name, spec in FILES.items():
        if name not in remote:
            raise ValueError(f"Pinned Figshare file absent: {name}")
        item = remote[name]
        if item["id"] != spec["id"] or item["size"] != spec["size"] or item["computed_md5"] != spec["md5"]:
            raise ValueError(f"Figshare file metadata changed: {name}")
        dest = cache / name
        if not dest.exists() or verified_file(dest, spec)["md5"] != spec["md5"]:
            download(item["download_url"], dest)
        verified_file(dest, spec)
    (cache / "figshare-article.json").write_text(
        json.dumps(article, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return {"article_id": ARTICLE_ID, "doi": article["doi"], "version": article["version"], "files": {
        name: verified_file(cache / name, spec) for name, spec in FILES.items()
    }}


def zip_inventory(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        members = [
            {"name": item.filename, "compressed_bytes": item.compress_size,
             "uncompressed_bytes": item.file_size, "crc32": f"{item.CRC:08x}"}
            for item in archive.infolist()
        ]
        total_uncompressed = sum(m["uncompressed_bytes"] for m in members)
        total_compressed = sum(m["compressed_bytes"] for m in members)
        bad = archive.testzip()
    if bad is not None:
        raise ValueError(f"ZIP CRC check failed at {bad}")
    return {"members": members, "total_compressed_bytes": total_compressed,
            "total_uncompressed_bytes": total_uncompressed}
