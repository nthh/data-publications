"""Offline credential and redirect checks for the Source API companion."""
from contextlib import contextmanager
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from urllib import request
from urllib.response import addinfourl
from email.message import Message

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/source_publish"))
import common


def cached_entry(token="old-refresh"):
    return {"refresh": {"refresh_token": token, "client_id": "source-client",
                        "token_endpoint": common.TOKEN_ENDPOINT,
                        "proxy_url": "https://data.source.coop"}}


class SourceApiCredentialTests(unittest.TestCase):
    def test_rotated_token_is_persisted_before_access_is_returned(self):
        entry = cached_entry()
        events = []

        def save(value):
            events.append(("save", value["refresh"]["refresh_token"]))

        with mock.patch.object(common, "_open_token_request", return_value=BytesIO(
            b'{"refresh_token":"new-refresh","access_token":"new-access"}')) as opened:
            access = common._refresh(entry, save, common.TOKEN_ENDPOINT)
        self.assertEqual(access, "new-access")
        self.assertEqual(events, [("save", "new-refresh")])
        self.assertEqual(opened.call_args.args[0].full_url, common.TOKEN_ENDPOINT)
        self.assertIn(b"old-refresh", opened.call_args.args[0].data)

    def test_failed_rotation_persistence_is_redacted_and_not_retried(self):
        entry = cached_entry("SECRET-REFRESH")

        def fail(_):
            raise common.AuthenticationError("Could not persist the rotated Source credential.")

        with mock.patch.object(common, "_open_token_request", return_value=BytesIO(
            b'{"refresh_token":"ROTATED-SECRET","access_token":"new-access"}')) as opened:
            with self.assertRaises(common.AuthenticationError) as caught:
                common._refresh(entry, fail, common.TOKEN_ENDPOINT)
        self.assertEqual(opened.call_count, 1)
        self.assertNotIn("SECRET", str(caught.exception))

    def test_atomic_fallback_save_and_failure_preserves_old_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "_default.json"
            path.write_text(json.dumps(cached_entry()), encoding="utf-8")
            common._save_fallback_cache(path, cached_entry("new-refresh"))
            self.assertEqual(json.loads(path.read_text())["refresh"]["refresh_token"], "new-refresh")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with mock.patch.object(common.os, "replace", side_effect=OSError("SECRET-IO")):
                with self.assertRaises(common.AuthenticationError) as caught:
                    common._save_fallback_cache(path, cached_entry("later-refresh"))
            self.assertNotIn("SECRET", str(caught.exception))
            self.assertEqual(json.loads(path.read_text())["refresh"]["refresh_token"], "new-refresh")
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()), ["_default.json"])

    def test_discovery_rejects_arbitrary_host_and_path_without_refresh(self):
        for endpoint in ("https://evil.invalid/oauth2/token",
                         "https://auth.source.coop/other/token",
                         "https://auth.source.coop:443/oauth2/token",
                         "https://auth.source.coop/oauth2/token?next=evil"):
            with self.subTest(endpoint=endpoint), tempfile.TemporaryDirectory() as folder:
                body = BytesIO(json.dumps({"token_endpoint": endpoint}).encode())
                with mock.patch.object(common.Path, "home", return_value=Path(folder)), \
                     mock.patch.object(common.request, "urlopen", return_value=body), \
                     mock.patch.object(common, "source_cache") as cache, \
                     mock.patch.object(common, "_open_token_request") as token_post:
                    with self.assertRaisesRegex(common.AuthenticationError, "Unsafe OAuth"):
                        common.oauth_access_token()
                cache.assert_not_called()
                token_post.assert_not_called()

    def test_redirect_never_reposts_refresh_grant(self):
        visited = []

        class RedirectingTransport(request.HTTPSHandler):
            def https_open(self, req):
                visited.append(req.full_url)
                headers = Message()
                headers["Location"] = "https://evil.invalid/oauth2/token"
                return addinfourl(BytesIO(b""), headers, req.full_url, 307)

        opener = request.build_opener(common._NoRedirect(), RedirectingTransport())
        with mock.patch.object(common.request, "build_opener", return_value=opener):
            with self.assertRaisesRegex(common.AuthenticationError, "refresh failed") as caught:
                common._refresh(cached_entry("SECRET-REFRESH"), lambda _: self.fail("saved on redirect"), common.TOKEN_ENDPOINT)
        self.assertEqual(visited, [common.TOKEN_ENDPOINT])
        self.assertNotIn("SECRET", str(caught.exception))

    def test_missing_lock_directory_does_not_hide_existing_login(self):
        with tempfile.TemporaryDirectory() as folder:
            entry = cached_entry()
            saved = []

            @contextmanager
            def fake_cache():
                yield entry, lambda value: saved.append(value["refresh"]["refresh_token"])

            discovery = BytesIO(json.dumps({"token_endpoint": common.TOKEN_ENDPOINT}).encode())
            with mock.patch.object(common.Path, "home", return_value=Path(folder)), \
                 mock.patch.object(common.request, "urlopen", return_value=discovery), \
                 mock.patch.object(common, "source_cache", side_effect=fake_cache), \
                 mock.patch.object(common, "_open_token_request", return_value=BytesIO(
                     b'{"refresh_token":"new-refresh","access_token":"new-access"}')):
                self.assertEqual(common.oauth_access_token(), "new-access")
            self.assertEqual(saved, ["new-refresh"])
            self.assertTrue((Path(folder) / "Library/Caches/source-coop/credentials/_default.lock").is_file())


if __name__ == "__main__":
    unittest.main()
