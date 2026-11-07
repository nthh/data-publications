#!/usr/bin/env python3
"""Bounded public TIFF-header probe; this is not a complete COG validator.

Reads at most 64 KiB, even if HTTP Range is ignored. No pixels are decoded.
Only the first IFD is inspected. Supports classic TIFF and BigTIFF headers.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import struct
import urllib.parse
import urllib.request

LIMIT = 65536


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    args = parser.parse_args()
    if urllib.parse.urlsplit(args.url).scheme != "https":
        raise SystemExit("Use a public HTTPS TIFF URL.")
    result = {"url": args.url, "observed_at": datetime.now(timezone.utc).isoformat(), "read_limit_bytes": LIMIT}
    request = urllib.request.Request(args.url, headers={"Range": f"bytes=0-{LIMIT-1}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        result.update(http_status=response.status, content_range=response.headers.get("Content-Range"))
        body = response.read(LIMIT)
    result.update(prefix_bytes=len(body), prefix_sha256=hashlib.sha256(body).hexdigest())
    result["gdal_layout_marker_present"] = b"LAYOUT=IFDS_BEFORE_DATA" in body
    try:
        if body[:2] not in (b"II", b"MM"):
            raise ValueError("Not a TIFF byte-order marker")
        endian = "<" if body[:2] == b"II" else ">"
        magic = struct.unpack_from(endian + "H", body, 2)[0]
        result["tiff_magic"] = magic
        if magic == 42:
            offset = struct.unpack_from(endian + "I", body, 4)[0]
            count_size, count_format, entry_size = 2, "H", 12
        elif magic == 43:
            if struct.unpack_from(endian + "HH", body, 4) != (8, 0):
                raise ValueError("Unsupported BigTIFF offset encoding")
            offset = struct.unpack_from(endian + "Q", body, 8)[0]
            count_size, count_format, entry_size = 8, "Q", 20
        else:
            raise ValueError("Unsupported TIFF magic")
        count = struct.unpack_from(endian + count_format, body, offset)[0]
        end = offset + count_size + count * entry_size
        if end > len(body):
            raise ValueError("First IFD extends beyond bounded header")
        tags = [struct.unpack_from(endian + "H", body, p)[0] for p in range(offset + count_size, end, entry_size)]
        result["first_ifd_tags"] = tags
        result["first_ifd_layout"] = (
            "tiled" if all(t in tags for t in (322, 323, 324, 325)) else
            "striped" if all(t in tags for t in (273, 278, 279)) else "unresolved"
        )
    except (ValueError, struct.error) as error:
        result["inspection_incomplete"] = str(error)
    result["scope"] = "One bounded TIFF prefix and first IFD only; no overviews, pixel reads, performance, or full-archive COG validation."
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
