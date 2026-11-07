#!/usr/bin/env python3
"""Serve a prepared local release with byte ranges and CORS for validation/preview."""
from __future__ import annotations

import argparse
import functools
import http.server
from pathlib import Path
import re


class RangeHandler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".parquet": "application/vnd.apache.parquet", ".pmtiles": "application/vnd.pmtiles",
                      ".json": "application/json", ".md": "text/markdown"}

    def log_message(self, *args):
        pass

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Range, If-Match")
        self.send_header("Access-Control-Expose-Headers", "Content-Length, Content-Range, Accept-Ranges, ETag")
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.end_headers()

    def send_head(self):
        path = Path(self.translate_path(self.path))
        if not path.is_file():
            self.send_error(404)
            return None
        total = path.stat().st_size
        start, end = 0, total - 1
        self._range = None
        value = self.headers.get("Range")
        if value:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", value)
            if not match or not any(match.groups()):
                self.send_error(416)
                return None
            left, right = match.groups()
            if left:
                start = int(left)
                end = min(int(right), total-1) if right else total-1
            else:
                start = max(0, total-int(right))
            if start > end or start >= total:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{total}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None
            self._range = (start, end)
        stream = path.open("rb")
        stream.seek(start)
        self.send_response(206 if value else 200)
        self.send_header("Content-Type", self.guess_type(str(path)))
        self.send_header("Content-Length", str(end-start+1))
        if value:
            self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
        self.end_headers()
        return stream

    def copyfile(self, source, outputfile):
        if self._range is None:
            return super().copyfile(source, outputfile)
        remaining = self._range[1]-self._range[0]+1
        while remaining:
            data = source.read(min(remaining, 65536))
            if not data:
                break
            outputfile.write(data)
            remaining -= len(data)


def server(root, port=0):
    return http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(RangeHandler, directory=str(root)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    with server(args.directory.resolve(), args.port) as httpd:
        print(f"http://127.0.0.1:{httpd.server_port}/catalog.json", flush=True)
        httpd.serve_forever()


if __name__ == "__main__":
    main()
