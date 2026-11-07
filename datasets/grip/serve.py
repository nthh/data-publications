#!/usr/bin/env python3
"""Serve a local GRIP4 bundle with byte ranges and CORS for preview clients."""
from __future__ import annotations

import argparse
import functools
import http.server
from pathlib import Path
import re


class RangeHandler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".parquet": "application/vnd.apache.parquet",
        ".pmtiles": "application/vnd.pmtiles",
        ".json": "application/json",
        ".md": "text/markdown",
        ".svg": "image/svg+xml",
    }

    def log_message(self, *_args):
        pass

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Range, If-Match, If-Range")
        self.send_header("Access-Control-Expose-Headers", "Content-Length, Content-Range, Accept-Ranges, ETag")
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Range, If-Match, If-Range")
        self.end_headers()

    def send_head(self):
        path = Path(self.translate_path(self.path))
        if not path.is_file():
            self.send_error(404)
            return None
        total = path.stat().st_size
        range_header = self.headers.get("Range")
        start, end = 0, total - 1
        self._range = None
        if range_header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
            if not match or not any(match.groups()) or total == 0:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{total}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None
            left, right = match.groups()
            if left:
                start = int(left)
                end = min(int(right), total - 1) if right else total - 1
            else:
                suffix = int(right)
                if suffix <= 0:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{total}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return None
                start = max(0, total - suffix)
            if start > end or start >= total:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{total}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None
            self._range = (start, end)
        stream = path.open("rb")
        stream.seek(start)
        self.send_response(206 if range_header else 200)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Content-Length", str(max(0, end - start + 1)))
        if range_header:
            self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
        self.end_headers()
        return stream

    def copyfile(self, source, outputfile):
        if self._range is None:
            return super().copyfile(source, outputfile)
        remaining = self._range[1] - self._range[0] + 1
        while remaining > 0:
            data = source.read(min(remaining, 65536))
            if not data:
                break
            outputfile.write(data)
            remaining -= len(data)


def server(root: Path, port: int = 0):
    directory = str(Path(root).resolve())
    return http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(RangeHandler, directory=directory))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="prepared release root containing catalog.json")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    root = args.directory.resolve()
    if not (root / "catalog.json").is_file():
        parser.error(f"{root} does not contain catalog.json")
    with server(root, args.port) as httpd:
        print(f"http://127.0.0.1:{httpd.server_port}/catalog.json", flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
