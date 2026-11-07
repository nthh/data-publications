"""Small read-only HTTP origins for the local direct-browser release viewer.

The runtime manifest is trusted as the result of preparation, including its SHA-256
values. This process checks the recorded file identity and size on every request; it
does not re-hash potentially multi-gigabyte objects at startup or per request.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import socket
import stat
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


_DIGEST = re.compile(r"^[0-9a-fA-F]{64}$")
_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
_HIDDEN_KEYS = re.compile(r"(?:secret|credential|password|token|api[_-]?key|local[_-]?path|filesystem[_-]?path)", re.I)
_CHUNK = 256 * 1024


class ManifestError(ValueError):
    pass


def _file_identity(path: Path) -> tuple[int, int, int]:
    """Return size, mtime_ns, inode while rejecting symlinks in every component."""
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        try:
            if stat.S_ISLNK(current.lstat().st_mode):
                # macOS exposes its standard temporary roots through these fixed
                # aliases. They are OS path prefixes, not user supplied links.
                target = current.resolve(strict=True)
                if not ((current == Path("/var") and target == Path("/private/var")) or
                        (current == Path("/tmp") and target == Path("/private/tmp"))):
                    raise ManifestError(f"symlink is not allowed: {current}")
        except FileNotFoundError as exc:
            raise ManifestError(f"mapped file does not exist: {absolute}") from exc
    info = absolute.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ManifestError(f"mapped path is not a regular file: {absolute}")
    return info.st_size, info.st_mtime_ns, info.st_ino


def _safe_route(route: object) -> str:
    if not isinstance(route, str) or not route.startswith("/") or route == "/":
        raise ManifestError("object route must be an absolute URL path")
    if any(c in route for c in ("%", "\\", "\x00", "?", "#")):
        raise ManifestError(f"suspicious object route: {route!r}")
    if any(piece in ("", ".", "..") for piece in route.split("/")[1:]):
        raise ManifestError(f"suspicious object route: {route!r}")
    if not route.startswith("/nthh/"):
        raise ManifestError(f"object route is outside /nthh/: {route!r}")
    return route


def load_manifest(path: str | os.PathLike[str]) -> tuple[dict[str, dict], dict]:
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ManifestError(f"duplicate runtime manifest key: {key}")
            result[key] = value
        return result
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique_pairs)
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read runtime manifest: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ManifestError("runtime manifest schema_version must be 1")
    entries = raw.get("objects")
    viewer = raw.get("viewer", {})
    if not isinstance(entries, dict) or not isinstance(viewer, dict):
        raise ManifestError("runtime manifest objects and viewer must be objects")
    objects: dict[str, dict] = {}
    for route, item in entries.items():
        route = _safe_route(route)
        if route in objects:
            raise ManifestError(f"duplicate object route: {route}")
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ManifestError(f"invalid object mapping for {route}")
        size = item.get("size_bytes")
        digest = item.get("sha256")
        content_type = item.get("content_type")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ManifestError(f"invalid size_bytes for {route}")
        if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
            raise ManifestError(f"invalid sha256 for {route}")
        if not isinstance(content_type, str) or not content_type or "\r" in content_type or "\n" in content_type:
            raise ManifestError(f"invalid content_type for {route}")
        file_path = Path(item["path"])
        if not file_path.is_absolute():
            raise ManifestError(f"object path must be absolute for {route}")
        identity = _file_identity(file_path)
        if identity[0] != size:
            raise ManifestError(f"object size does not match manifest for {route}")
        objects[route] = {"path": file_path, "size": size, "sha256": digest.lower(),
                          "etag": f'"{digest.lower()}"', "content_type": content_type,
                          "identity": identity}
    return objects, viewer


def _public_config(viewer: dict, object_origin: str) -> dict:
    def clean(value):
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items()
                    if isinstance(k, str) and not _HIDDEN_KEYS.search(k)
                    and k.lower() not in {"path", "file", "filename", "local_file"}}
        if isinstance(value, list):
            return [clean(v) for v in value]
        if isinstance(value, str) and value.startswith("/") and not value.startswith("/nthh/"):
            return "[redacted]"
        return value
    result = clean(viewer)
    result["object_origin"] = object_origin
    return result


def _new_log(path: str | os.PathLike[str] | None):
    if path is None:
        return None
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags, 0o600)
    return os.fdopen(fd, "a", encoding="utf-8", buffering=1)


class _LogWriter:
    def __init__(self, stream):
        self.stream = stream
        self.lock = threading.Lock()

    def write(self, record: dict):
        if self.stream is None:
            return
        with self.lock:
            self.stream.write(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")
            self.stream.flush()

    def close(self):
        if self.stream is not None:
            with self.lock:
                if not self.stream.closed:
                    self.stream.close()


class _HTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def server_close(self):
        super().server_close()
        writer = getattr(self, "request_log", None)
        if writer is not None:
            writer.close()


class _IPv6HTTPServer(_HTTPServer):
    address_family = socket.AF_INET6


class ObjectHandler(BaseHTTPRequestHandler):
    server_version = "FoliaObject/1"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def send_error(self, code, message=None, explain=None):
        body = (f"{code} {message or self.responses.get(code, ('Error',))[0]}\n").encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Range, If-Range")
        self.send_header("Access-Control-Expose-Headers", "Content-Length, Content-Range, Accept-Ranges, ETag")
        self.send_header("Timing-Allow-Origin", "*")

    def _respond(self, method: str):
        started = time.monotonic()
        parsed = urlsplit(self.path)
        route = parsed.path
        entry = self.server.objects.get(route) if not any(c in route for c in ("%", "\\", "\x00")) else None
        status, sent, interval = 404, 0, None
        range_header = self.headers.get("Range")
        try:
            if method not in ("GET", "HEAD", "OPTIONS"):
                status = 405
                self.send_response(status)
                self._cors()
                self.send_header("Allow", "GET, HEAD, OPTIONS")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if entry is None:
                self.send_error(404)
                return
            if method == "OPTIONS":
                status = 204
                self.send_response(status)
                self._cors()
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            try:
                if _file_identity(entry["path"]) != entry["identity"]:
                    raise OSError("mapped file changed after manifest load")
                source = entry["path"].open("rb")
                opened = os.fstat(source.fileno())
                if (opened.st_size, opened.st_mtime_ns, opened.st_ino) != entry["identity"]:
                    source.close()
                    raise OSError("mapped file changed after manifest load")
            except (OSError, ManifestError):
                status = 500
                self.send_error(status, "Mapped object changed")
                return
            size = entry["size"]
            start, end = 0, size - 1
            status = 200
            if range_header and (not self.headers.get("If-Range") or self.headers.get("If-Range") == entry["etag"]):
                match = _RANGE.fullmatch(range_header.strip())
                if not match or "," in range_header or size == 0:
                    status = 416
                else:
                    first, last = match.groups()
                    if not first and not last:
                        status = 416
                    elif first:
                        start = int(first)
                        end = min(int(last), size - 1) if last else size - 1
                        if start >= size or end < start:
                            status = 416
                    else:
                        suffix = int(last)
                        if suffix <= 0:
                            status = 416
                        else:
                            start, end = max(0, size - suffix), size - 1
                if status == 416:
                    source.close()
                    self.send_response(status)
                    self._cors()
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                status = 206
                interval = [start, end]
            length = max(0, end - start + 1)
            self.send_response(status)
            self._cors()
            self.send_header("Content-Type", entry["content_type"])
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("ETag", entry["etag"])
            self.send_header("Content-Length", str(length))
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            if method == "GET" and length:
                with source:
                    source.seek(start)
                    remaining = length
                    while remaining:
                        block = source.read(min(_CHUNK, remaining))
                        if not block:
                            raise OSError("mapped object ended during response")
                        self.wfile.write(block)
                        sent += len(block)
                        remaining -= len(block)
            else:
                source.close()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except OSError:
            if not self.wfile.closed:
                pass
        finally:
            self.server.request_log.write({
                "status": status, "origin": self.server.origin, "route": route,
                "requested_range": range_header, "bytes_sent": sent,
                "range": interval, "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            })

    do_GET = lambda self: self._respond("GET")
    do_HEAD = lambda self: self._respond("HEAD")
    do_OPTIONS = lambda self: self._respond("OPTIONS")


class UIHandler(BaseHTTPRequestHandler):
    server_version = "FoliaViewer/1"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _respond(self, method):
        parsed = urlsplit(self.path)
        route = parsed.path
        if method not in ("GET", "HEAD", "OPTIONS"):
            self.send_error(405)
            return
        if method == "OPTIONS":
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if route == "/viewer-config.json":
            body = self.server.config_bytes
            content_type = "application/json; charset=utf-8"
        else:
            if any(c in route for c in ("%", "\\", "\x00")) or any(p in (".", "..") for p in route.split("/")):
                self.send_error(404)
                return
            relative = "index.html" if route == "/" else route.lstrip("/")
            candidate = (self.server.ui_root / relative).resolve(strict=False)
            try:
                candidate.relative_to(self.server.ui_root)
                rel_parts = Path(relative).parts
                probe = self.server.ui_root
                for part in rel_parts:
                    probe = probe / part
                    if stat.S_ISLNK(probe.lstat().st_mode):
                        raise FileNotFoundError
                info = candidate.stat()
                if not stat.S_ISREG(info.st_mode):
                    raise FileNotFoundError
            except (ValueError, OSError):
                self.send_error(404)
                return
            content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
            try:
                body = candidate.read_bytes()
            except OSError:
                self.send_error(404)
                return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if method == "GET":
            self.wfile.write(body)

    do_GET = lambda self: self._respond("GET")
    do_HEAD = lambda self: self._respond("HEAD")
    do_OPTIONS = lambda self: self._respond("OPTIONS")


def create_servers(manifest: str | os.PathLike[str], ui_root: str | os.PathLike[str],
                   host: str = "127.0.0.1", ui_port: int = 8910, object_port: int = 8911,
                   log: str | os.PathLike[str] | None = None):
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise ValueError("host must be loopback")
    objects, viewer = load_manifest(manifest)
    root = Path(ui_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("ui-root must be a directory")
    # Reject symlinks anywhere under the served tree; only built static files are exposed.
    for candidate in root.rglob("*"):
        if stat.S_ISLNK(candidate.lstat().st_mode):
            raise ValueError(f"symlink in UI root: {candidate}")
    stream = _new_log(log)
    writer = _LogWriter(stream)
    server_type = _IPv6HTTPServer if host == "::1" else _HTTPServer
    object_server = server_type((host, object_port), ObjectHandler)
    actual_host, actual_port = object_server.server_address[:2]
    object_origin = f"http://[{actual_host}]:{actual_port}" if ":" in actual_host else f"http://{actual_host}:{actual_port}"
    object_server.objects = objects
    object_server.origin = object_origin
    object_server.request_log = writer
    ui_server = server_type((host, ui_port), UIHandler)
    ui_server.ui_root = root
    ui_server.config_bytes = json.dumps(_public_config(viewer, object_origin), separators=(",", ":")).encode()
    ui_server.request_log = writer
    return ui_server, object_server


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--ui-root", required=True)
    parser.add_argument("--ui-port", type=int, default=8910)
    parser.add_argument("--object-port", type=int, default=8911)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--log", help="new JSONL object request log; existing files are refused")
    args = parser.parse_args(argv)
    ui, objects = create_servers(args.manifest, args.ui_root, args.host, args.ui_port, args.object_port, args.log)
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (ui, objects)]
    for thread in threads:
        thread.start()
    print(f"UI: http://{ui.server_address[0]}:{ui.server_address[1]}/")
    print(f"Objects: {objects.origin}")
    try:
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        ui.shutdown(); objects.shutdown()
        ui.server_close(); objects.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
