#!/usr/bin/env python3
"""Acquire the locked current Figshare v1 File Geodatabase without extraction."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import urllib.request
from pathlib import Path

ARTICLE_ID = 7688801
FILE_ID = 15090536
ARTICLE_VERSION = 1
SOURCE_URL = f"https://ndownloader.figshare.com/files/{FILE_ID}"
API_URL = f"https://api.figshare.com/v2/articles/{ARTICLE_ID}"
SOURCE_NAME = "Mapping_the_worlds_free-flowing_rivers_Data_Geodatabase.zip"
FIGSHARE_NAME = "Mapping the worlds free-flowing rivers_Data_Geodatabase.zip"
SIZE = 954710486
MD5 = "2df6c603904f61f5dc482d3f9873900f"
SHA256 = "e45aa83a60e91840ddf6cc0820a4c32f44edf7a0318c78b62980fa9e44d6e31a"


def hash_file(path: Path) -> tuple[int, str, str]:
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            size += len(block)
            md5.update(block)
            sha256.update(block)
    return size, md5.hexdigest(), sha256.hexdigest()


def verify_metadata(metadata: dict) -> dict:
    if metadata.get("id") != ARTICLE_ID or metadata.get("version") != ARTICLE_VERSION:
        raise ValueError("Current Figshare article version differs from the v1 source lock; review the new version before acquiring")
    if metadata.get("doi") != "10.6084/m9.figshare.7688801.v1":
        raise ValueError("Unexpected Figshare DOI")
    if metadata.get("license", {}).get("name") != "CC BY 4.0":
        raise ValueError("Unexpected Figshare data license")
    files = [item for item in metadata.get("files", []) if item.get("id") == FILE_ID]
    if len(files) != 1:
        raise ValueError(f"Expected exactly one locked file id {FILE_ID}")
    item = files[0]
    expected = (FIGSHARE_NAME, SIZE, MD5)
    observed = (item.get("name"), item.get("size"), item.get("computed_md5"))
    if observed != expected:
        raise ValueError(f"Figshare file metadata differs from source lock: {observed!r}")
    if item.get("download_url") != SOURCE_URL or item.get("is_link_only"):
        raise ValueError("Unexpected Figshare download URL or linked-file status")
    return item


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".local/free-flowing-rivers") / SOURCE_NAME)
    parser.add_argument("--metadata-output", type=Path, default=Path(".local/free-flowing-rivers/article.json"))
    args = parser.parse_args()
    metadata_bytes = urllib.request.urlopen(API_URL, timeout=60).read()
    metadata = json.loads(metadata_bytes)
    verify_metadata(metadata)
    args.metadata_output.parent.mkdir(parents=True, exist_ok=True)
    args.metadata_output.write_bytes(metadata_bytes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        if hash_file(args.output) != (SIZE, MD5, SHA256):
            raise SystemExit("Existing source path has different bytes; refusing to overwrite it")
        print(f"Pinned source already present: {args.output}")
        return

    fd, temporary = tempfile.mkstemp(prefix=SOURCE_NAME + ".", suffix=".partial", dir=args.output.parent)
    os.close(fd)
    temporary_path = Path(temporary)
    try:
        request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "Folia local dataset acquisition"})
        with urllib.request.urlopen(request, timeout=180) as response, temporary_path.open("wb") as out:
            md5 = hashlib.md5()
            sha256 = hashlib.sha256()
            size = 0
            while block := response.read(8 * 1024 * 1024):
                out.write(block)
                size += len(block)
                md5.update(block)
                sha256.update(block)
        if (size, md5.hexdigest(), sha256.hexdigest()) != (SIZE, MD5, SHA256):
            raise SystemExit("Downloaded Figshare archive does not match locked size/MD5/SHA-256")
        temporary_path.replace(args.output)
    finally:
        temporary_path.unlink(missing_ok=True)
    print(f"Acquired verified source ({SIZE} bytes): {args.output}")


if __name__ == "__main__":
    main()
