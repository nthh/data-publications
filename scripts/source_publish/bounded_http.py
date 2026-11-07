"""Strict anonymous loopback transport for bounded DuckDB Source Parquet reads."""

from __future__ import annotations

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import re
import threading
from typing import Any
from urllib import parse, request


MAX_REQUEST_BYTES = 64 * 1024 * 1024
MAX_ASSET_BYTES = 128 * 1024 * 1024
MAX_LEDGER_EVENTS = 2048
RANGE_RE = re.compile(r"^bytes=(\d+)-(\d+)$")
SUFFIX_RE = re.compile(r"^bytes=-(\d+)$")


class BoundedHTTPError(ValueError):
    """Request or response violates the exact bounded transport contract."""


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise BoundedHTTPError("remote redirect refused")


def _headers(value: Any) -> dict[str, str]:
    return {str(key).lower(): str(item).strip() for key, item in value.items()}


def _range_interval(value: str | None, size: int) -> tuple[int, int, int]:
    if not isinstance(value, str) or "," in value:
        raise BoundedHTTPError("GET requires one bounded byte range")
    match = RANGE_RE.fullmatch(value)
    if match:
        start, end = map(int, match.groups())
    else:
        suffix = SUFFIX_RE.fullmatch(value)
        if suffix is None or int(suffix.group(1)) < 1:
            raise BoundedHTTPError("GET requires one bounded byte range")
        length = min(int(suffix.group(1)), size)
        start, end = size - length, size - 1
    if start < 0 or end < start or end >= size:
        raise BoundedHTTPError("GET range is outside planned object")
    length = end - start + 1
    if length > MAX_REQUEST_BYTES:
        raise BoundedHTTPError("GET range exceeds 64 MiB request ceiling")
    return start, end, length


class BoundedSourceProxy:
    """Map opaque loopback routes to exact planned Source Parquet objects only."""

    def __init__(self, assets: dict[str, dict[str, Any]], *, product_id: str,
                 opener: Any = None):
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", product_id):
            raise BoundedHTTPError("unsafe product ID")
        self.assets: dict[str, dict[str, Any]] = {}
        self.routes: dict[str, str] = {}
        for path, asset in assets.items():
            if not isinstance(path, str) or not isinstance(asset, dict):
                raise BoundedHTTPError("invalid exact Parquet asset map")
            url, size, mime = asset.get("url"), asset.get("size_bytes"), asset.get("content_type")
            parsed = parse.urlsplit(url) if isinstance(url, str) else None
            if (parsed is None or parsed.scheme != "https" or parsed.netloc != "data.source.coop"
                    or parsed.username or parsed.password or parsed.query or parsed.fragment
                    or not parsed.path.startswith(f"/nthh/{product_id}/releases/")
                    or not parsed.path.endswith(".parquet") or type(size) is not int or size <= 0
                    or not isinstance(mime, str) or mime.split(";", 1)[0].lower() != "application/vnd.apache.parquet"):
                raise BoundedHTTPError("proxy asset is outside exact planned Source Parquet URLs")
            route = "/asset/" + hashlib.sha256(url.encode()).hexdigest()[:24] + ".parquet"
            if route in self.routes or path in self.assets:
                raise BoundedHTTPError("duplicate proxy asset route")
            self.assets[path] = {"url": url, "size_bytes": size, "content_type": mime,
                                 "route": route, "reserved_bytes": 0, "response_body_bytes": 0,
                                 "get_count": 0, "head_count": 0}
            self.routes[route] = path
        if not self.assets:
            raise BoundedHTTPError("proxy requires exact planned Parquet assets")
        self._opener = opener or request.build_opener(_NoRedirect())
        self._lock = threading.Lock()
        self._events: list[dict[str, Any]] = []
        self._errors: list[str] = []
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def _record(self, event: dict[str, Any]) -> None:
        with self._lock:
            if len(self._events) < MAX_LEDGER_EVENTS:
                self._events.append(event)
            else:
                self._errors.append("proxy event ledger ceiling exceeded")

    def _reject(self, asset_path: str | None, method: str, range_value: str | None, message: str) -> None:
        event = {"asset_path": asset_path, "method": method, "range": range_value,
                 "status": "rejected", "error": message}
        self._record(event)
        with self._lock:
            self._errors.append(message)
        raise BoundedHTTPError(message)

    def _open(self, req: request.Request):
        opener = self._opener
        return opener.open(req, timeout=60) if hasattr(opener, "open") else opener(req, timeout=60)

    def fetch(self, route: str, method: str, range_value: str | None = None) -> tuple[int, dict[str, str], bytes]:
        path = self.routes.get(route)
        if path is None:
            self._reject(None, method, range_value, "off-map proxy route refused")
        assert path is not None
        with self._lock:
            ledger_full = len(self._events) >= MAX_LEDGER_EVENTS
        if ledger_full:
            self._reject(path, method, range_value, "proxy event ledger ceiling exceeded")
        asset = self.assets[path]
        size = asset["size_bytes"]
        if method not in {"GET", "HEAD"}:
            self._reject(path, method, range_value, "proxy permits only HEAD and bounded GET")
        if method == "HEAD":
            if range_value not in (None, "bytes=0-"):
                self._reject(path, method, range_value, "unsupported metadata HEAD range")
            interval = None
        else:
            try:
                interval = _range_interval(range_value, size)
            except BoundedHTTPError as exc:
                self._reject(path, method, range_value, str(exc))
            assert interval is not None
            with self._lock:
                if asset["reserved_bytes"] + interval[2] > MAX_ASSET_BYTES:
                    over_budget = True
                else:
                    over_budget = False
                    asset["reserved_bytes"] += interval[2]
            if over_budget:
                self._reject(path, method, range_value, "asset exceeds 128 MiB total reservation ceiling")
        upstream_headers = {"Accept-Encoding": "identity"}
        if range_value is not None:
            upstream_headers["Range"] = range_value
        req = request.Request(asset["url"], method=method, headers=upstream_headers)
        event = {"asset_path": path, "method": method, "range": range_value}
        try:
            with self._open(req) as response:
                status = response.status
                headers = _headers(response.headers)
                if response.geturl() != asset["url"]:
                    raise BoundedHTTPError("remote redirect or URL change refused")
                media = headers.get("content-type", "").split(";", 1)[0].lower()
                if media != asset["content_type"].split(";", 1)[0].lower():
                    raise BoundedHTTPError("remote MIME differs from exact plan")
                if headers.get("accept-ranges", "").lower() != "bytes":
                    raise BoundedHTTPError("remote does not advertise byte ranges")
                if method == "HEAD":
                    if headers.get("content-length") != str(size):
                        raise BoundedHTTPError("HEAD size differs from exact plan")
                    if status != 200 and not (range_value == "bytes=0-" and status == 206
                                              and headers.get("content-range") == f"bytes 0-{size - 1}/{size}"):
                        raise BoundedHTTPError("HEAD is not exact planned-object metadata")
                    body = b""
                else:
                    assert interval is not None
                    start, end, length = interval
                    if (status != 206 or headers.get("content-range") != f"bytes {start}-{end}/{size}"
                            or headers.get("content-length") != str(length)):
                        raise BoundedHTTPError("GET response range or length differs from request")
                    body = response.read(length)
                    with self._lock:
                        asset["response_body_bytes"] += len(body)
                        asset["get_count"] += 1
                        if asset["response_body_bytes"] > MAX_ASSET_BYTES:
                            raise BoundedHTTPError("asset exceeds 128 MiB response-body ceiling")
                    if len(body) != length:
                        raise BoundedHTTPError("short remote GET body")
            if method == "HEAD":
                with self._lock:
                    asset["head_count"] += 1
            event.update({"status": status, "body_bytes": len(body), "content_range": headers.get("content-range")})
            self._record(event)
            return status, headers, body
        except Exception as exc:
            message = str(exc)[:500] if isinstance(exc, BoundedHTTPError) else f"{type(exc).__name__}: {str(exc)[:400]}"
            self._reject(path, method, range_value, message)

    def url_for(self, path: str) -> str:
        if self._server is None or path not in self.assets:
            raise BoundedHTTPError("proxy is not started or asset is absent")
        return f"http://127.0.0.1:{self._server.server_port}{self.assets[path]['route']}"

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"per_request_ceiling_bytes": MAX_REQUEST_BYTES,
                    "per_asset_total_ceiling_bytes": MAX_ASSET_BYTES,
                    "assets": {path: {key: item[key] for key in ("url", "size_bytes", "content_type",
                        "reserved_bytes", "response_body_bytes", "get_count", "head_count")}
                        for path, item in self.assets.items()},
                    "events": list(self._events), "errors": list(self._errors)}

    def __enter__(self):
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_HEAD(self):
                self._serve("HEAD")

            def do_GET(self):
                self._serve("GET")

            def _serve(self, method: str):
                parsed = parse.urlsplit(self.path)
                if parsed.query or parsed.fragment or self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
                    try:
                        proxy._reject(None, method, None, "unsafe loopback request target refused")
                    except BoundedHTTPError:
                        pass
                    self.send_error(403)
                    return
                values = self.headers.get_all("Range") or []
                if len(values) > 1:
                    try:
                        proxy._reject(None, method, None, "multiple Range headers refused")
                    except BoundedHTTPError:
                        pass
                    self.send_error(403)
                    return
                try:
                    status, headers, body = proxy.fetch(parsed.path, method, values[0] if values else None)
                except BoundedHTTPError as exc:
                    message = str(exc).encode("utf-8")[:500]
                    self.send_response(502)
                    self.send_header("Content-Length", str(len(message)))
                    self.end_headers()
                    if method != "HEAD":
                        self.wfile.write(message)
                    return
                self.send_response(status)
                for name in ("content-type", "content-length", "content-range", "accept-ranges"):
                    if name in headers:
                        self.send_header(name.title(), headers[name])
                self.end_headers()
                if method == "GET":
                    self.wfile.write(body)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_args):
        assert self._server is not None and self._thread is not None
        self._server.shutdown()
        self._thread.join(timeout=5)
        self._server.server_close()
        self._server = None
        self._thread = None
