from __future__ import annotations

import importlib.util
import http.client
from pathlib import Path
import sys
from urllib.parse import urlsplit

import pytest

PATH = Path(__file__).resolve().parents[1] / "scripts/source_publish/bounded_http.py"
SPEC = importlib.util.spec_from_file_location("bounded_http_tested", PATH)
assert SPEC and SPEC.loader
bounded = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bounded
SPEC.loader.exec_module(bounded)


class Response:
    def __init__(self, url, status, headers, body):
        self.url, self.status, self.headers, self.body = url, status, headers, body

    def geturl(self):
        return self.url

    def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class Opener:
    def __init__(self, *, redirect=False, wrong_range=False, wrong_mime=False):
        self.calls = []
        self.redirect, self.wrong_range, self.wrong_mime = redirect, wrong_range, wrong_mime

    def open(self, req, timeout=60):
        self.calls.append(req)
        url = req.full_url + ("?redirected=1" if self.redirect else "")
        content = "text/plain" if self.wrong_mime else "application/vnd.apache.parquet"
        headers = {"Content-Type": content, "Accept-Ranges": "bytes"}
        if req.method == "HEAD":
            headers["Content-Length"] = "200000000"
            return Response(url, 200, headers, b"")
        value = req.headers["Range"]
        start, end = map(int, value.removeprefix("bytes=").split("-"))
        length = end - start + 1
        headers.update({"Content-Length": str(length),
                        "Content-Range": f"bytes {start}-{end}/{199999999 if self.wrong_range else 200000000}"})
        return Response(url, 206, headers, b"x" * length)


def proxy(opener=None):
    url = "https://data.source.coop/nthh/lakeatlas/releases/v1/assets/lakes.parquet"
    server = bounded.BoundedSourceProxy({"assets/lakes.parquet": {
        "url": url, "size_bytes": 200000000, "content_type": "application/vnd.apache.parquet"}},
        product_id="lakeatlas", opener=opener or Opener())
    return server, next(iter(server.routes))


def test_metadata_and_exact_ranged_get_count_only_bodies():
    opener = Opener()
    server, route = proxy(opener)
    assert server.fetch(route, "HEAD")[0] == 200
    status, _, body = server.fetch(route, "GET", "bytes=7-9")
    assert status == 206 and body == b"xxx"
    asset = server.snapshot()["assets"]["assets/lakes.parquet"]
    assert asset["response_body_bytes"] == asset["reserved_bytes"] == 3
    assert asset["head_count"] == asset["get_count"] == 1


def test_loopback_serves_only_exact_bounded_routes():
    opener = Opener()
    server, route = proxy(opener)
    try:
        server.__enter__()
    except PermissionError:
        pytest.skip("sandbox refuses binding a loopback test server")
    try:
        parsed = urlsplit(server.url_for("assets/lakes.parquet"))
        connection = http.client.HTTPConnection("127.0.0.1", parsed.port)
        connection.request("HEAD", route)
        response = connection.getresponse()
        assert response.status == 200 and response.getheader("Content-Length") == "200000000"
        response.read()
        connection.request("GET", route, headers={"Range": "bytes=1-3"})
        response = connection.getresponse()
        assert response.status == 206 and response.read() == b"xxx"
        connection.request("GET", route)
        response = connection.getresponse()
        assert response.status == 502
        response.read()
        connection.close()
    finally:
        server.__exit__(None, None, None)
    assert len(opener.calls) == 2
    assert server.snapshot()["errors"]


@pytest.mark.parametrize("route,range_value", [
    ("/other", "bytes=0-1"), (None, None), (None, "bytes=0-"),
    (None, "bytes=0-67108864"), (None, "bytes=199999999-200000000"),
    (None, "bytes=0-1,3-4"),
])
def test_refuses_off_map_full_open_oversized_or_outside_get_before_network(route, range_value):
    opener = Opener()
    server, valid_route = proxy(opener)
    with pytest.raises(bounded.BoundedHTTPError):
        server.fetch(route or valid_route, "GET", range_value)
    assert not opener.calls


def test_total_asset_budget_refuses_third_request_before_network(monkeypatch):
    monkeypatch.setattr(bounded, "MAX_REQUEST_BYTES", 4)
    monkeypatch.setattr(bounded, "MAX_ASSET_BYTES", 8)
    opener = Opener()
    server, route = proxy(opener)
    server.fetch(route, "GET", "bytes=0-3")
    server.fetch(route, "GET", "bytes=4-7")
    with pytest.raises(bounded.BoundedHTTPError, match="reservation ceiling"):
        server.fetch(route, "GET", "bytes=0-0")
    assert len(opener.calls) == 2


@pytest.mark.parametrize("kwargs,phrase", [
    ({"redirect": True}, "redirect"),
    ({"wrong_range": True}, "range"),
    ({"wrong_mime": True}, "MIME"),
])
def test_upstream_identity_range_and_mime_must_match(kwargs, phrase):
    server, route = proxy(Opener(**kwargs))
    with pytest.raises(bounded.BoundedHTTPError, match=phrase):
        server.fetch(route, "GET", "bytes=0-2")
    assert server.snapshot()["errors"]


def test_rejects_off_host_asset_map():
    with pytest.raises(bounded.BoundedHTTPError, match="exact planned"):
        bounded.BoundedSourceProxy({"x.parquet": {"url": "https://evil.example/x.parquet",
            "size_bytes": 10, "content_type": "application/vnd.apache.parquet"}}, product_id="lakeatlas")
