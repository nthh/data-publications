#!/usr/bin/env python3
"""Bounded TIFF metadata/range probe for JRC GSW v1.5 Occurrence tiles.

Reads the previously captured complete CloudFerro inventory, probes at most
eight named tiles, and never downloads full objects. Every HTTP body byte read
is accounted against --max-response-bytes; a server ignoring Range is stopped
without consuming its body and recorded as a failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests

BASE = "https://s3.waw4-1.cloudferro.com/swift/v1/global-surface-water/"
DEFAULT_TILES = [
    "occurrence_110W_40N_v1_5_2024.tif",  # North America, data-rich
    "occurrence_20E_10N_v1_5_2024.tif",   # Africa, data-rich
    "occurrence_70E_30N_v1_5_2024.tif",   # Asia, data-rich
    "occurrence_130E_30S_v1_5_2024.tif",  # Australia, data-rich
    "occurrence_0E_0N_v1_5_2024.tif",     # Gulf of Guinea/Atlantic coast
    "occurrence_160W_30S_v1_5_2024.tif",  # sparse ocean zone
    "occurrence_0E_80N_v1_5_2024.tif",    # high latitude sparse zone
    "occurrence_80W_50N_v1_5_2024.tif",   # higher latitude North America
]
TAG_NAMES = {
    256: "ImageWidth", 257: "ImageLength", 258: "BitsPerSample",
    259: "Compression", 262: "PhotometricInterpretation", 277: "SamplesPerPixel",
    322: "TileWidth", 323: "TileLength", 324: "TileOffsets", 325: "TileByteCounts",
    330: "SubIFDs", 33550: "ModelPixelScaleTag", 33922: "ModelTiepointTag",
    34735: "GeoKeyDirectoryTag", 42112: "GDAL_METADATA", 42113: "GDAL_NODATA",
}


class Budget:
    def __init__(self, cap: int):
        self.cap = cap
        self.used = 0

    def read(self, url: str, start: int, length: int, timeout: tuple[float, float]) -> tuple[bytes, dict]:
        if self.used + length > self.cap:
            raise RuntimeError(f"budget would exceed: used={self.used} request={length} cap={self.cap}")
        end = start + length - 1
        row: dict = {"range_requested": f"bytes={start}-{end}", "requested_bytes": length}
        data = bytearray()
        try:
            with requests.get(url, headers={"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"},
                              stream=True, timeout=timeout) as r:
                row.update(status=r.status_code, content_range=r.headers.get("Content-Range"),
                           content_length=r.headers.get("Content-Length"),
                           content_type=r.headers.get("Content-Type"),
                           etag=r.headers.get("ETag"), last_modified=r.headers.get("Last-Modified"))
                expected_prefix = f"bytes {start}-{end}/"
                if r.status_code != 206 or not r.headers.get("Content-Range", "").startswith(expected_prefix):
                    # Close without consuming a body if a server ignores/misstates Range.
                    row.update(response_bytes_read=0, response_sha256=hashlib.sha256(b"").hexdigest(),
                               range_honored=False, complete_requested_range=False,
                               error="server did not return the requested HTTP 206 range; response body not read")
                    return b"", row
                for chunk in r.iter_content(chunk_size=min(4096, length)):
                    if not chunk:
                        continue
                    # Do not read past the range length or aggregate cap.
                    room = min(length - len(data), self.cap - self.used)
                    if room <= 0:
                        break
                    accepted = chunk[:room]
                    data.extend(accepted)
                    self.used += len(accepted)
                    if len(data) >= length:
                        break
                row["response_bytes_read"] = len(data)
                row["response_sha256"] = hashlib.sha256(data).hexdigest()
                row["range_honored"] = (r.status_code == 206 and
                                          r.headers.get("Content-Range", "").startswith(f"bytes {start}-"))
                row["complete_requested_range"] = len(data) == length and row["range_honored"]
                return bytes(data), row
        except Exception as e:
            row.update(error=f"{type(e).__name__}: {e}", response_bytes_read=len(data))
            return b"", row


def decode_header(b: bytes) -> tuple[str, bool, int, str]:
    if len(b) < 16:
        raise ValueError("short TIFF header")
    order = b[:2]
    if order == b"II": endian = "<"
    elif order == b"MM": endian = ">"
    else: raise ValueError(f"invalid byte order {order!r}")
    magic = struct.unpack(endian + "H", b[2:4])[0]
    if magic == 42:
        return endian, False, struct.unpack(endian + "I", b[4:8])[0], "classic TIFF"
    if magic == 43:
        offsize, zero = struct.unpack(endian + "HH", b[4:8])
        if offsize != 8 or zero != 0:
            raise ValueError(f"unsupported BigTIFF header offset size={offsize}, zero={zero}")
        return endian, True, struct.unpack(endian + "Q", b[8:16])[0], "BigTIFF"
    raise ValueError(f"unknown TIFF magic {magic}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", type=Path, default=Path("research/chirps-priorities-20261030/evidence/jrc-v15-aggregated-list.json"))
    ap.add_argument("--output", type=Path, default=Path("research/hydro-releases-20261031/jrc/occurrence-range-probes.json"))
    ap.add_argument("--tile", action="append", help="Exact basename; may be repeated (maximum 8)")
    ap.add_argument("--max-response-bytes", type=int, default=4 * 1024 * 1024)
    ap.add_argument("--per-tile-bytes", type=int, default=512 * 1024)
    ap.add_argument("--connect-timeout", type=float, default=8)
    ap.add_argument("--read-timeout", type=float, default=12)
    args = ap.parse_args()
    if args.output.exists(): ap.error("refusing to overwrite prior probe evidence; choose a new --output path")
    if min(args.max_response_bytes, args.per_tile_bytes, args.connect_timeout, args.read_timeout) <= 0:
        ap.error("byte budgets and timeouts must be positive")
    names = args.tile or DEFAULT_TILES
    if len(names) > 8: ap.error("at most 8 tiles may be probed")
    if args.max_response_bytes > 8 * 1024 * 1024: ap.error("aggregate cap cannot exceed 8 MiB")
    if args.per_tile_bytes > 1024 * 1024: ap.error("per-tile cap cannot exceed 1 MiB")
    inv = json.loads(args.inventory.read_text())
    by_base = {Path(x["name"]).name: x for x in inv["body"] if "/occurrence/" in x["name"]}
    missing = [x for x in names if x not in by_base]
    if missing: ap.error(f"tiles absent from pinned inventory: {missing}")

    budget = Budget(args.max_response_bytes)
    records = []
    for base in names:
        obj = by_base[base]
        url = BASE + quote(obj["name"], safe="/")
        rec: dict = {"basename": base, "source_name": obj["name"], "inventory_bytes": obj["bytes"],
                     "inventory_hash": obj["hash"], "inventory_last_modified": obj["last_modified"],
                     "url": url, "requests": [], "tiff": {}}
        remaining = args.per_tile_bytes

        def get(start: int, length: int, label: str):
            nonlocal remaining
            n = min(length, remaining, budget.cap - budget.used)
            if n <= 0:
                rec["requests"].append({"label": label, "skipped": "byte budget exhausted"})
                return b""
            body, row = budget.read(url, start, n, (args.connect_timeout, args.read_timeout))
            row["label"] = label
            rec["requests"].append(row)
            remaining -= row.get("response_bytes_read", 0)
            return body

        hdr = get(0, 16, "TIFF header")
        try:
            endian, big, ifd_off, flavor = decode_header(hdr)
            rec["tiff"].update(byte_order="little" if endian == "<" else "big", format=flavor,
                                first_ifd_offset=ifd_off)
            # Read the IFD count first, then a bounded prefix of entries.
            cnt_size = 8 if big else 2
            cnt_b = get(ifd_off, cnt_size, "first IFD entry count")
            if len(cnt_b) == cnt_size and rec["requests"][-1].get("complete_requested_range"):
                count = struct.unpack(endian + ("Q" if big else "H"), cnt_b)[0]
                entry_size = 20 if big else 12
                count_size = 8 if big else 2
                next_size = 8 if big else 4
                wanted = min(count * entry_size + next_size, remaining, 256 * 1024)
                entries_b = get(ifd_off + cnt_size, wanted, "bounded IFD entries")
                parsed = []
                nentries = min(count, len(entries_b) // entry_size)
                for i in range(nentries):
                    ent = entries_b[i * entry_size:(i + 1) * entry_size]
                    if big:
                        tag, typ, n = struct.unpack(endian + "HHQ", ent[:12])
                        value_field = ent[12:20]
                    else:
                        tag, typ, n = struct.unpack(endian + "HHI", ent[:8])
                        value_field = ent[8:12]
                    value = int.from_bytes(value_field, "little" if endian == "<" else "big")
                    parsed.append({"tag": tag, "name": TAG_NAMES.get(tag, f"Tag{tag}"),
                                   "type": typ, "count": n, "inline_value_or_offset": value})
                nextptr = int.from_bytes(entries_b[count * entry_size:count * entry_size + next_size],
                                         "little" if endian == "<" else "big") if len(entries_b) >= count * entry_size + next_size else None
                rec["tiff"].update(first_ifd_entry_count=count, ifd_entries_parsed=len(parsed),
                                    ifd_entries=parsed,
                                    entries_complete=(len(parsed) == count and len(entries_b) >= count * entry_size + next_size),
                                    ifd_structural_prefix_sha256=hashlib.sha256(entries_b).hexdigest(),
                                    first_ifd_next_offset=nextptr)
                rec["tiff"]["has_tile_tags_in_parsed_entries"] = any(x["tag"] in (322,323,324,325) for x in parsed)
                rec["tiff"]["has_subifd_tag_in_parsed_entries"] = any(x["tag"] == 330 for x in parsed)

                # Walk linked image directories (the common TIFF overview form)
                # and inspect complete tile-offset arrays. Pixel payloads are never read.
                base_node = {"ifd_offset": ifd_off, "entry_count": count, "entries_complete": True,
                             "next_ifd_offset": nextptr, "image_width": None, "image_length": None,
                             "tile_width": None, "tile_length": None, "tile_offsets_count": None,
                             "tile_offsets_array_offset": None, "tile_offsets_min": None,
                             "tile_offsets_max": None, "tile_offsets_monotonic": None}
                base_by_tag = {e["tag"]: e for e in parsed}
                for tag, name in ((256,"image_width"),(257,"image_length"),(322,"tile_width"),(323,"tile_length")):
                    if tag in base_by_tag: base_node[name] = base_by_tag[tag]["inline_value_or_offset"]
                base_to = base_by_tag.get(324)
                if base_to:
                    num = base_to["count"]; off = base_to["inline_value_or_offset"]
                    base_node["tile_offsets_count"] = num
                    if base_to["type"] == 4 and num == 1:
                        # For a one-element TIFF array, the LONG value is inline.
                        base_node["tile_offsets_min"] = off
                        base_node["tile_offsets_max"] = off
                        base_node["tile_offsets_array_offset"] = None
                        base_node["tile_offsets_monotonic"] = True
                    elif base_to["type"] == 4 and num * 4 <= remaining:
                        raw = get(off, num * 4, "base IFD TileOffsets array")
                        if len(raw) == num * 4 and rec["requests"][-1].get("complete_requested_range"):
                            vals = list(struct.unpack(endian + f"{num}I", raw))
                            base_node["tile_offsets_array_offset"] = off
                            base_node["tile_offsets_min"] = min(vals) if vals else None
                            base_node["tile_offsets_max"] = max(vals) if vals else None
                            base_node["tile_offsets_monotonic"] = all(a <= b for a,b in zip(vals, vals[1:]))
                chain = [base_node]
                ptr, seen = nextptr, {ifd_off}
                ifd_count_size, ifd_entry_size, ifd_next_size = cnt_size, entry_size, next_size
                for level in range(1, 12):
                    if not ptr or ptr in seen or remaining < ifd_count_size:
                        break
                    seen.add(ptr)
                    cb = get(ptr, ifd_count_size, f"overview IFD {level} entry count")
                    if len(cb) != ifd_count_size or not rec["requests"][-1].get("complete_requested_range"):
                        break
                    c = struct.unpack(endian + ("Q" if big else "H"), cb)[0]
                    nbytes = min(c * ifd_entry_size + ifd_next_size, remaining, 128 * 1024)
                    eb = get(ptr + ifd_count_size, nbytes, f"overview IFD {level} bounded entries")
                    if len(eb) < c * ifd_entry_size + ifd_next_size:
                        chain.append({"ifd_offset": ptr, "entry_count": c, "entries_complete": False})
                        break
                    es = []
                    for i in range(c):
                        ent = eb[i * ifd_entry_size:(i + 1) * ifd_entry_size]
                        if big:
                            tag, typ, n = struct.unpack(endian + "HHQ", ent[:12]); vf = ent[12:20]
                        else:
                            tag, typ, n = struct.unpack(endian + "HHI", ent[:8]); vf = ent[8:12]
                        val = int.from_bytes(vf, "little" if endian == "<" else "big")
                        es.append({"tag": tag, "name": TAG_NAMES.get(tag, f"Tag{tag}"),
                                   "type": typ, "count": n, "inline_value_or_offset": val})
                    nxt = int.from_bytes(eb[c * ifd_entry_size:c * ifd_entry_size + ifd_next_size],
                                         "little" if endian == "<" else "big")
                    node = {"ifd_offset": ptr, "entry_count": c, "entries_complete": True,
                            "next_ifd_offset": nxt, "image_width": None, "image_length": None,
                            "tile_width": None, "tile_length": None, "tile_offsets_count": None,
                            "tile_offsets_array_offset": None, "tile_offsets_min": None,
                            "tile_offsets_max": None, "tile_offsets_monotonic": None}
                    by_tag = {e["tag"]: e for e in es}
                    for tag, name in ((256,"image_width"),(257,"image_length"),(322,"tile_width"),(323,"tile_length")):
                        if tag in by_tag: node[name] = by_tag[tag]["inline_value_or_offset"]
                    to = by_tag.get(324)
                    if to:
                        num = to["count"]; off = to["inline_value_or_offset"]
                        node["tile_offsets_count"] = num
                        # TIFF LONG arrays are 4-byte elements; bound total array read.
                        if to["type"] == 4 and num == 1:
                            node["tile_offsets_min"] = off
                            node["tile_offsets_max"] = off
                            node["tile_offsets_array_offset"] = None
                            node["tile_offsets_monotonic"] = True
                        elif to["type"] == 4 and num * 4 <= remaining:
                            raw = get(off, num * 4, f"overview IFD {level} TileOffsets array")
                            if len(raw) == num * 4 and rec["requests"][-1].get("complete_requested_range"):
                                vals = list(struct.unpack(endian + f"{num}I", raw))
                                node["tile_offsets_array_offset"] = off
                                node["tile_offsets_min"] = min(vals) if vals else None
                                node["tile_offsets_max"] = max(vals) if vals else None
                                node["tile_offsets_monotonic"] = all(a <= b for a,b in zip(vals, vals[1:]))
                    chain.append(node)
                    ptr = nxt
                rec["tiff"]["ifd_chain"] = chain
                rec["tiff"]["ifd_chain_complete"] = bool(chain and chain[-1].get("next_ifd_offset") == 0)
                # This is a sample-level layout signal, not a complete COG validator.
                dims = [(x.get("image_width"), x.get("image_length")) for x in chain]
                levels_descend = all(dims[i][0] > dims[i+1][0] and dims[i][1] > dims[i+1][1]
                                     for i in range(len(dims)-1) if None not in dims[i] + dims[i+1])
                data_ranges = [(x.get("tile_offsets_min"), x.get("tile_offsets_max")) for x in chain]
                # IFD chain is full resolution then descending overviews, while
                # COG payload order is smallest overview to full resolution.
                overview_before_base = (len(data_ranges) > 1 and
                    all(a[0] is not None and a[1] is not None for a in data_ranges) and
                    all(data_ranges[i+1][1] < data_ranges[i][0] for i in range(len(data_ranges)-1)))
                rec["tiff"]["sample_layout_signals"] = {
                    "complete_ifd_chain": rec["tiff"]["ifd_chain_complete"],
                    "dimensions_decrease_through_chain": levels_descend,
                    "tile_offsets_ascending_within_each_ifd": all(x.get("tile_offsets_monotonic") for x in chain),
                    "overview_payloads_precede_base_payloads": overview_before_base,
                    "probable_cog_layout": bool(rec["tiff"]["ifd_chain_complete"] and levels_descend and
                        all(x.get("tile_offsets_monotonic") for x in chain) and overview_before_base),
                    "warning": "Layout signals are sampled TIFF structure checks, not full COG conformance certification."}
            else:
                rec["tiff"]["ifd_probe_incomplete"] = True
        except Exception as e:
            rec["tiff"]["parse_error"] = f"{type(e).__name__}: {e}"
        records.append(rec)

    passed = all(r["tiff"].get("sample_layout_signals", {}).get("probable_cog_layout", False) and
                 all(q.get("complete_requested_range", False) for q in r["requests"]) for r in records)
    doc = {"status": "passed_sample_qualification" if passed else "failed_sample_qualification",
           "probe_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "source_inventory_path": str(args.inventory),
           "source_inventory_sha256": hashlib.sha256(args.inventory.read_bytes()).hexdigest(),
           "inventory_response_sha256": inv.get("response_sha256"),
           "aggregate_response_byte_cap": args.max_response_bytes,
           "aggregate_response_bytes_read": budget.used,
           "max_tiles": 8, "per_tile_response_byte_cap": args.per_tile_bytes,
           "timeout_seconds": {"connect": args.connect_timeout, "read": args.read_timeout},
           "scope_warning": "Sample only; does not certify all 504 objects or COG conformance.",
           "tiles": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as report:
        report.write(json.dumps(doc, indent=2) + "\n")
    print(json.dumps({k: doc[k] for k in ("captured_at_utc", "aggregate_response_bytes_read", "aggregate_response_byte_cap", "source_inventory_sha256")}, indent=2))
    for r in records:
        print(r["basename"], "bytes", r["inventory_bytes"], "probe", r["tiff"].get("format"),
              "range206", all(q.get("range_honored", False) for q in r["requests"] if "requested_bytes" in q),
              "parsed", len(r["tiff"].get("ifd_entries", [])), "tags",
              [x["name"] for x in r["tiff"].get("ifd_entries", []) if x["tag"] in TAG_NAMES])
    return 0 if passed else 1

if __name__ == "__main__":
    raise SystemExit(main())
