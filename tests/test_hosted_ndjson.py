from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/source_publish/validate_hosted.py"
SPEC = importlib.util.spec_from_file_location("validate_hosted_ndjson", MODULE_PATH)
assert SPEC and SPEC.loader
hosted = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = hosted
SPEC.loader.exec_module(hosted)

URL = "https://data.source.coop/nthh/grwl-raw/audit.jsonl"


class Response:
    status = 200

    def __init__(self, body: bytes, content_type: str, url: str = URL):
        self._body = body
        self.headers = {"Content-Type": content_type}
        self._url = url

    def read(self, size: int = -1) -> bytes:
        return self._body if size < 0 else self._body[:size]

    def geturl(self) -> str:
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def check(tmp_path: Path, local: bytes, remote: bytes | None = None,
          content_type: str = "application/x-ndjson") -> dict:
    path = tmp_path / "audit.jsonl"
    path.write_bytes(local)
    response = Response(local if remote is None else remote, content_type)
    return hosted._metadata_check(
        URL, path, len(local), hashlib.sha256(local).hexdigest(),
        "application/x-ndjson", opener=lambda req, timeout=60: response,
    )


def test_multiple_ndjson_records_are_parsed_but_not_treated_as_stac_json(tmp_path):
    data = b'{"event":"start"}\n{"event":"complete"}\n'
    result = check(tmp_path, data)
    assert result["ndjson_records"] == [{"event": "start"}, {"event": "complete"}]
    assert result["ndjson_record_count"] == 2
    assert result["json"] is None


@pytest.mark.parametrize("data", [b"", b"\n\r\n  \n"])
def test_empty_ndjson_and_blank_lines_are_accepted(tmp_path, data):
    result = check(tmp_path, data)
    assert result["ndjson_records"] == []
    assert result["ndjson_record_count"] == 0


def test_invalid_second_ndjson_record_is_rejected(tmp_path):
    with pytest.raises(hosted.HostedValidationError, match="line 2"):
        check(tmp_path, b'{"event":"start"}\n{not-json}\n')


def test_invalid_utf8_ndjson_is_rejected(tmp_path):
    with pytest.raises(hosted.HostedValidationError, match="invalid NDJSON"):
        check(tmp_path, b'{"event":"start"}\n\xff\n')


def test_multiline_application_json_remains_one_json_document(tmp_path):
    data = b'{\n  "type": "Collection",\n  "links": []\n}\n'
    path = tmp_path / "collection.json"
    path.write_bytes(data)
    response = Response(data, "application/json; charset=utf-8")
    result = hosted._metadata_check(
        URL, path, len(data), hashlib.sha256(data).hexdigest(), "application/json",
        opener=lambda req, timeout=60: response,
    )
    assert result["json"] == {"type": "Collection", "links": []}
    assert result["ndjson_records"] is None
    assert result["ndjson_record_count"] is None


def test_multiple_json_documents_are_rejected(tmp_path):
    data = b'{"record":1}\n{"record":2}\n'
    path = tmp_path / "records.json"
    path.write_bytes(data)
    response = Response(data, "application/json")
    with pytest.raises(hosted.HostedValidationError, match="invalid JSON"):
        hosted._metadata_check(
            URL, path, len(data), hashlib.sha256(data).hexdigest(), "application/json",
            opener=lambda req, timeout=60: response,
        )


def test_wrong_content_type_is_rejected(tmp_path):
    with pytest.raises(hosted.HostedValidationError, match="Content-Type differs"):
        check(tmp_path, b'{"event":"start"}\n', content_type="application/json")


def test_remote_bytes_that_do_not_match_local_hash_are_rejected(tmp_path):
    with pytest.raises(hosted.HostedValidationError, match="bytes differ"):
        check(tmp_path, b'{"event":"start"}\n', remote=b'{"event":"stArt"}\n')


def test_structured_json_media_type_keeps_single_document_validation(tmp_path):
    data = b'{"type":"FeatureCollection","features":[]}'
    path = tmp_path / "collection.geojson"
    path.write_bytes(data)
    result = hosted._metadata_check(
        URL, path, len(data), hashlib.sha256(data).hexdigest(), "application/geo+json",
        opener=lambda req, timeout=60: Response(data, "application/geo+json"),
    )
    assert result["json"]["type"] == "FeatureCollection"
