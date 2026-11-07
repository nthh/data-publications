import hashlib
import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

from scripts.cloud_viewer.serve import ManifestError, create_servers


class CloudViewerServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = self.root / "private" / "fixture.bin"
        self.data.parent.mkdir()
        self.data.write_bytes(b"0123456789abcdefghijklmnopqrstuvwxyz")
        self.ui = self.root / "built"
        self.ui.mkdir()
        (self.ui / "index.html").write_text("viewer", encoding="utf-8")
        self.log = self.root / "requests.jsonl"
        self.manifest_path = self.root / "runtime.json"
        self.write_manifest()
        self.ui_server, self.object_server = create_servers(
            self.manifest_path, self.ui, ui_port=0, object_port=0, log=self.log)
        self.threads = []
        for server in (self.ui_server, self.object_server):
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.threads.append(thread)

    def tearDown(self):
        for server in (self.ui_server, self.object_server):
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join(timeout=2)
        self.temp.cleanup()

    def write_manifest(self, **changes):
        entry = {"path": str(self.data), "size_bytes": self.data.stat().st_size,
                 "sha256": hashlib.sha256(self.data.read_bytes()).hexdigest(),
                 "content_type": "application/octet-stream"}
        entry.update(changes)
        manifest = {"schema_version": 1, "objects": {"/nthh/demo/releases/r1/file.bin": entry},
                    "viewer": {"title": "Demo", "path": str(self.data), "token": "secret-token"}}
        self.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def request(self, method="GET", path="/nthh/demo/releases/r1/file.bin", headers=None, ui=False):
        server = self.ui_server if ui else self.object_server
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=4)
        conn.request(method, path, headers=headers or {})
        response = conn.getresponse()
        body = response.read()
        result = response.status, dict(response.getheaders()), body
        conn.close()
        return result

    def test_ranges_open_suffix_and_headers(self):
        status, headers, body = self.request(headers={"Range": "bytes=3-7"})
        self.assertEqual((status, body), (206, b"34567"))
        self.assertEqual(headers["Content-Range"], "bytes 3-7/36")
        self.assertEqual(headers["Content-Length"], "5")
        self.assertEqual(headers["Accept-Ranges"], "bytes")
        self.assertEqual(headers["ETag"], '"' + hashlib.sha256(self.data.read_bytes()).hexdigest() + '"')
        self.assertEqual(headers["Access-Control-Allow-Origin"], "*")
        self.assertEqual(headers["Access-Control-Expose-Headers"], "Content-Length, Content-Range, Accept-Ranges, ETag")
        self.assertEqual(headers["Timing-Allow-Origin"], "*")
        self.assertEqual(self.request(headers={"Range": "bytes=30-"})[2], b"uvwxyz")
        self.assertEqual(self.request(headers={"Range": "bytes=-4"})[2], b"wxyz")

    def test_unsatisfiable_and_malformed_ranges(self):
        for value in ("bytes=99-", "bytes=5-2", "bytes=-0", "bytes=1-2,4-5", "items=1-2"):
            status, headers, _ = self.request(headers={"Range": value})
            self.assertEqual(status, 416, value)
            self.assertEqual(headers["Content-Range"], "bytes */36")

    def test_head_options_and_if_range(self):
        status, headers, body = self.request("HEAD", headers={"Range": "bytes=2-4"})
        self.assertEqual((status, body), (206, b""))
        self.assertEqual(headers["Content-Length"], "3")
        self.assertEqual(self.request("OPTIONS")[0], 204)
        self.assertEqual(self.request(headers={"Range": "bytes=2-4", "If-Range": '"wrong"'})[0], 200)
        digest = hashlib.sha256(self.data.read_bytes()).hexdigest()
        self.assertEqual(self.request(headers={"Range": "bytes=2-4", "If-Range": f'"{digest}"'})[2], b"234")

    def test_path_traversal_encoded_and_unmapped_are_not_served(self):
        for path in ("/nthh/../private/fixture.bin", "/nthh/%2e%2e/private/fixture.bin",
                     "/nthh/%252e%252e/private/fixture.bin", "/nthh\\private\\fixture.bin",
                     "/private/fixture.bin"):
            self.assertEqual(self.request(path=path)[0], 404, path)

    def test_symlinks_are_rejected_for_object_and_ui(self):
        link = self.root / "linked.bin"
        link.symlink_to(self.data)
        with self.assertRaises(ManifestError):
            self.write_manifest(path=str(link))
            # Runtime identity validation happens when constructing a new server.
            create_servers(self.manifest_path, self.ui, ui_port=0, object_port=0)
        (self.ui / "secret-link").symlink_to(self.data)
        with self.assertRaises(ValueError):
            create_servers(self.manifest_path, self.ui, ui_port=0, object_port=0)

    def test_manifest_rejects_bad_metadata_and_suspicious_routes(self):
        cases = ({"size_bytes": 1}, {"sha256": "no-digest"})
        for changes in cases:
            with self.subTest(changes=changes):
                self.write_manifest(**changes)
                with self.assertRaises(ManifestError):
                    create_servers(self.manifest_path, self.ui, ui_port=0, object_port=0)
        entry = {"path": str(self.data), "size_bytes": self.data.stat().st_size,
                 "sha256": "0" * 64, "content_type": "application/octet-stream"}
        for route in ("/nthh/../private/file", "/nthh/%2e%2e/private/file", "/other/file"):
            with self.subTest(route=route):
                self.manifest_path.write_text(json.dumps({"schema_version": 1, "objects": {route: entry}, "viewer": {}}))
                with self.assertRaises(ManifestError):
                    create_servers(self.manifest_path, self.ui, ui_port=0, object_port=0)
        self.manifest_path.write_text(
            '{"schema_version":1,"objects":{"/nthh/a":{"path":"x"},"/nthh/a":{"path":"y"}},"viewer":{}}')
        with self.assertRaises(ManifestError):
            create_servers(self.manifest_path, self.ui, ui_port=0, object_port=0)

    def test_changed_file_fails_closed(self):
        self.data.write_bytes(b"X" * self.data.stat().st_size)
        status, _, body = self.request()
        self.assertEqual(status, 500)
        self.assertNotIn(b"X", body)

    def test_ui_config_does_not_disclose_local_path_or_credentials(self):
        status, headers, body = self.request(path="/viewer-config.json", ui=True)
        config = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(config["object_origin"], self.object_server.origin)
        self.assertNotIn(str(self.data), body.decode())
        self.assertNotIn("secret-token", body.decode())
        self.assertEqual(self.request(path="/", ui=True)[2], b"viewer")
        (self.ui / "escape").symlink_to(self.data)
        self.assertEqual(self.request(path="/escape", ui=True)[0], 404)

    def test_request_log_records_transfers_without_file_paths(self):
        self.request(headers={"Range": "bytes=0-2"})
        self.request("HEAD")
        records = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual(records[0]["bytes_sent"], 3)
        self.assertEqual(records[0]["range"], [0, 2])
        self.assertEqual(records[1]["bytes_sent"], 0)
        self.assertNotIn(str(self.data), self.log.read_text())


if __name__ == "__main__":
    unittest.main()
