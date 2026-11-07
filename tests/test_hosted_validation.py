from __future__ import annotations

from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlsplit

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/source_publish/validate_hosted.py"
SPEC = importlib.util.spec_from_file_location("validate_hosted", MODULE_PATH)
assert SPEC and SPEC.loader
hosted = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = hosted
SPEC.loader.exec_module(hosted)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def browser_request(url: str, data: bytes, content_type: str) -> dict:
    size = len(data)
    return {"url": url, "status_check": "passed", "status": 206,
            "range": f"bytes=0-{size - 1}", "content_range": f"bytes 0-{size - 1}/{size}",
            "content_length": size, "body_bytes": size, "body_sha256": sha(data),
            "planned_sha256": sha(data), "content_type": content_type,
            "cors": "*", "expose_headers": "Content-Range, Content-Length, Accept-Ranges"}


class Response:
    def __init__(self, status: int, headers: dict[str, str], body: bytes, url: str):
        self.status = status
        self.headers = headers
        self._body = body
        self._url = url

    def read(self, size: int = -1) -> bytes:
        return self._body if size < 0 else self._body[:size]

    def geturl(self) -> str:
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class MockOpener:
    def __init__(self, objects: dict[str, bytes], *, bad_range: bool = False,
                 bad_cors: bool = False, wildcard_cors: bool = False):
        self.objects = objects
        self.bad_range = bad_range
        self.bad_cors = bad_cors
        self.wildcard_cors = wildcard_cors
        self.calls = []

    def __call__(self, req, timeout=60):
        self.calls.append(req)
        url = req.full_url
        path = urlsplit(url).path
        body = self.objects[path]
        content_types = {".parquet": "application/vnd.apache.parquet", ".pmtiles": "application/vnd.pmtiles",
                         ".json": "application/json", ".md": "text/markdown"}
        suffix = Path(path).suffix
        headers = {"Content-Type": content_types.get(suffix, "application/octet-stream")}
        if req.method == "OPTIONS":
            headers.update({"Access-Control-Allow-Origin": "*",
                            "Access-Control-Allow-Methods": "GET, OPTIONS",
                            "Access-Control-Allow-Headers": "*" if self.wildcard_cors else "Range"})
            return Response(204, headers, b"", url)
        if "Range" in req.headers:
            match = re.fullmatch(r"bytes=(\d+)-(\d+)", req.headers["Range"])
            assert match
            start, end = map(int, match.groups())
            part = body[start:end + 1]
            headers.update({"Content-Range": f"bytes {start}-{end}/{len(body)}",
                            "Content-Length": str(len(part)), "Accept-Ranges": "bytes",
                            "Access-Control-Allow-Origin": "https://wrong.example" if self.bad_cors else "*",
                            "Access-Control-Expose-Headers": "*" if self.wildcard_cors
                            else "Content-Range, Content-Length, Accept-Ranges"})
            if self.bad_range:
                headers["Content-Range"] = f"bytes {start}-{end}/{len(body) + 1}"
            return Response(206, headers, part, url)
        headers["Content-Length"] = str(len(body))
        return Response(200, headers, body, url)


class FakeDuckDB:
    def execute(self, sql, params=None):
        if sql == "LOAD httpfs":
            return self
        if sql.startswith("SELECT num_rows FROM parquet_file_metadata"):
            self.footer_result = (1,)
            return self
        if sql.startswith("SELECT CAST("):
            self.id_rows = [(str(value), 1) for value in params[1:]]
            return self
        assert "LIMIT 1001" in sql
        self.current = params[0]
        return self

    def fetchall(self):
        if hasattr(self, "id_rows"):
            rows = self.id_rows
            del self.id_rows
            return rows
        return [(1, b"geometry", "value")]

    def fetchone(self):
        return self.footer_result

    def close(self):
        pass


class LocalParquetDuckDBAdapter:
    """Run real local Parquet SQL while bypassing only unused httpfs loading."""

    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, params=None):
        if sql == "LOAD httpfs":
            return self
        if params and any(isinstance(value, str) and value.startswith(("http://", "https://"))
                          for value in params):
            raise AssertionError("local Parquet fixture attempted a remote DuckDB read")
        self.connection.execute(sql, params)
        return self

    def fetchall(self):
        return self.connection.fetchall()

    def fetchone(self):
        return self.connection.fetchone()

    def close(self):
        self.connection.close()


def local_parquet_connect(tmp_path):
    """Use an empty extension directory and disable DuckDB extension downloads."""
    duckdb = pytest.importorskip("duckdb")
    extension_dir = tmp_path / "duckdb-extensions-empty"
    extension_dir.mkdir(exist_ok=True)

    def connect(**kwargs):
        connection = duckdb.connect(**kwargs, config={
            "extension_directory": str(extension_dir),
            "autoload_known_extensions": "false",
            "autoinstall_known_extensions": "false",
        })
        return LocalParquetDuckDBAdapter(connection)

    return connect


def fixture(tmp_path: Path):
    package = tmp_path / "package"
    display = tmp_path / "display"
    package.mkdir()
    display.mkdir()
    parquet = b"tiny parquet stand-in"
    pmtiles = b"tiny pmtiles stand-in"
    package_manifest = b'{"package":"hydrolakes"}\n'
    display_manifest = (json.dumps({"display": "d1", "assets": [{"id": "lake-layer",
        "path": "tiles.pmtiles", "style_path": "styles/style.json",
        "sha256": sha(pmtiles), "size_bytes": len(pmtiles)}]}).encode() + b"\n")
    catalog = b'{"links":[{"rel":"child","href":"collection.json"}]}\n'
    readme = b"HydroLAKES test product.\n"
    style = b'{"sources":{"tiles":{"url":"pmtiles://../tiles.pmtiles"}}}\n'
    collection = (b'{"type":"Collection","assets":{"data":{"href":"rows.parquet"},'
                  b'"visual":{"href":"/nthh/hydrolakes/display/d1/tiles.pmtiles"}}}\n')
    (package / "rows.parquet").write_bytes(parquet)
    (package / "collection.json").write_bytes(collection)
    (package / "catalog.json").write_bytes(catalog)
    (package / "README.md").write_bytes(readme)
    (package / "manifest.json").write_bytes(package_manifest)
    (display / "tiles.pmtiles").write_bytes(pmtiles)
    (display / "manifest.json").write_bytes(display_manifest)
    (display / "styles").mkdir()
    (display / "styles/style.json").write_bytes(style)
    rows = [
        {"bucket": "nthh", "endpoint": hosted.DATA_ORIGIN,
         "object_key": "hydrolakes/releases/v1/rows.parquet",
         "s3_uri_proposed": "s3://nthh/hydrolakes/releases/v1/rows.parquet",
         "source": {"kind": "package", "dataset_id": "hydrolakes", "path": "rows.parquet"},
         "size_bytes": len(parquet), "sha256": sha(parquet), "content_type": "application/vnd.apache.parquet"},
        {"bucket": "nthh", "endpoint": hosted.DATA_ORIGIN,
         "object_key": "hydrolakes/releases/v1/collection.json",
         "s3_uri_proposed": "s3://nthh/hydrolakes/releases/v1/collection.json",
         "source": {"kind": "package", "dataset_id": "hydrolakes", "path": "collection.json"},
         "size_bytes": len(collection), "sha256": sha(collection), "content_type": "application/json"},
        {"bucket": "nthh", "endpoint": hosted.DATA_ORIGIN,
         "object_key": "hydrolakes/releases/v1/catalog.json",
         "s3_uri_proposed": "s3://nthh/hydrolakes/releases/v1/catalog.json",
         "source": {"kind": "package", "dataset_id": "hydrolakes", "path": "catalog.json"},
         "size_bytes": len(catalog), "sha256": sha(catalog), "content_type": "application/json"},
        {"bucket": "nthh", "endpoint": hosted.DATA_ORIGIN,
         "object_key": "hydrolakes/releases/v1/README.md",
         "s3_uri_proposed": "s3://nthh/hydrolakes/releases/v1/README.md",
         "source": {"kind": "package", "dataset_id": "hydrolakes", "path": "README.md"},
         "size_bytes": len(readme), "sha256": sha(readme), "content_type": "text/markdown"},
        {"bucket": "nthh", "endpoint": hosted.DATA_ORIGIN,
         "object_key": "hydrolakes/releases/v1/manifest.json",
         "s3_uri_proposed": "s3://nthh/hydrolakes/releases/v1/manifest.json",
         "source": {"kind": "package", "dataset_id": "hydrolakes", "path": "manifest.json"},
         "size_bytes": len(package_manifest), "sha256": sha(package_manifest), "content_type": "application/json"},
        {"bucket": "nthh", "endpoint": hosted.DATA_ORIGIN,
         "object_key": "hydrolakes/display/d1/tiles.pmtiles",
         "s3_uri_proposed": "s3://nthh/hydrolakes/display/d1/tiles.pmtiles",
         "source": {"kind": "display_package", "dataset_id": "hydrolakes", "path": "tiles.pmtiles"},
         "size_bytes": len(pmtiles), "sha256": sha(pmtiles), "content_type": "application/vnd.pmtiles"},
        {"bucket": "nthh", "endpoint": hosted.DATA_ORIGIN,
         "object_key": "hydrolakes/display/d1/manifest.json",
         "s3_uri_proposed": "s3://nthh/hydrolakes/display/d1/manifest.json",
         "source": {"kind": "display_package", "dataset_id": "hydrolakes", "path": "manifest.json"},
         "size_bytes": len(display_manifest), "sha256": sha(display_manifest), "content_type": "application/json"},
        {"bucket": "nthh", "endpoint": hosted.DATA_ORIGIN,
         "object_key": "hydrolakes/display/d1/styles/style.json",
         "s3_uri_proposed": "s3://nthh/hydrolakes/display/d1/styles/style.json",
         "source": {"kind": "display_package", "dataset_id": "hydrolakes", "path": "styles/style.json"},
         "size_bytes": len(style), "sha256": sha(style), "content_type": "application/json"},
    ]
    for row in rows:
        row["mutable"] = False
    plan = {"schema_version": 1, "plan_type": "source_coop_immutable_exact_file_plan",
            "products": [{"dataset_id": "hydrolakes", "product_id": "hydrolakes", "owner": "nthh",
                          "bucket": "nthh", "endpoint": hosted.DATA_ORIGIN, "release": "v1",
                          "display_publication": {"release": "d1", "manifest_sha256": sha(display_manifest),
                                                  "assets": [{"id": "lake-layer", "href": "display/d1/tiles.pmtiles",
                                                              "sha256": sha(pmtiles), "size_bytes": len(pmtiles)}]}}],
            "files": rows, "mutable_metadata": [], "file_count": len(rows),
            "total_bytes": sum(row["size_bytes"] for row in rows)}
    plan_path = tmp_path / "plan.json"
    plan_bytes = json.dumps(plan).encode()
    plan_path.write_bytes(plan_bytes)
    plan_sha = sha(plan_bytes)
    receipt = tmp_path / "receipt"
    records = receipt / "objects"
    records.mkdir(parents=True)
    (receipt / "summary.json").write_text(json.dumps({"schema_version": 1, "plan_sha256": plan_sha,
        "mode": "execute", "status": "complete", "failed": 0,
        "completed": len(rows), "object_count": len(rows)}))
    for index, row in enumerate(rows):
        key = row["object_key"]
        (records / f"{index:04d}.json").write_text(json.dumps({
            "schema_version": 1, "plan_sha256": plan_sha, "bucket": "nthh", "object_key": key,
            "expected_sha256": row["sha256"], "expected_size_bytes": row["size_bytes"],
            "mutable": bool(row.get("mutable")), "remote_sha256": row["sha256"],
            "status": "uploaded_verified"}))
    controls = tmp_path / "controls.json"
    controls.write_text(json.dumps({"schema_version": 1, "dataset_id": "hydrolakes",
        "plan_sha256": plan_sha, "release": "v1", "queries": [
        {"name": "fixed ids", "path": "rows.parquet", "id_column": "FID", "ids": [1],
         "selection": {"row_count": 1}}]}))
    browser = tmp_path / "browser.json"
    browser_controls = tmp_path / "browser-controls.json"
    screenshot = tmp_path / "review.png"
    screenshot.write_bytes(b"screenshot")
    browser_objects = {f"https://data.source.coop/nthh/{row['object_key']}": {
        "sha256": row["sha256"], "size_bytes": row["size_bytes"], "content_type": row["content_type"]}
        for row in rows}
    browser_controls.write_text(json.dumps({"schema_version": 1, "plan_sha256": plan_sha,
        "viewer_config_sha256": "c" * 64, "objects": browser_objects,
        "cases": [{"id": "lake", "dataset_id": "hydrolakes", "layer_id": "lake-layer",
                   "region": "north_america"}]}))
    browser_controls_sha = sha(browser_controls.read_bytes())
    browser.write_text(json.dumps({"schema_version": 1, "status": "partial", "selected_dataset_id": "hydrolakes",
        "expected_case_count": 1, "browser_cases_sha256": browser_controls_sha,
        "plan_sha256": plan_sha, "viewer_config_sha256": "c" * 64,
        "viewer_build_sha256": "d" * 64,
        "transfer_ceiling_bytes_per_case": 128 * 1024 * 1024,
        "transfer_ceiling_bytes_total": 1024 * 1024 * 1024,
        "total_transferred_bytes": len(pmtiles) + len(parquet),
        "cases": [{"id": "lake", "dataset_id": "hydrolakes", "layer_id": "lake-layer",
                   "region": "north_america", "status": "passed",
                   "display_object_url": "https://data.source.coop/nthh/hydrolakes/display/d1/tiles.pmtiles",
                   "display_sha256": sha(pmtiles),
                   "analytic_object_url": "https://data.source.coop/nthh/hydrolakes/releases/v1/rows.parquet",
                   "analytic_sha256": sha(parquet),
                   "transferred_bytes": len(pmtiles) + len(parquet),
                   "requests": [
                       browser_request("https://data.source.coop/nthh/hydrolakes/display/d1/tiles.pmtiles", pmtiles, "application/vnd.pmtiles"),
                       browser_request("https://data.source.coop/nthh/hydrolakes/releases/v1/rows.parquet", parquet, "application/vnd.apache.parquet")]}],
        "datasets": [{"dataset_id": "hydrolakes", "product_id": "hydrolakes", "release": "v1",
            "display_release": "d1", "status": "passed", "checked_at": "2026-11-06T12:00:00Z",
            "screenshots": [str(screenshot)], "case_ids": ["lake"], "plan_sha256": plan_sha,
            "browser_cases_sha256": browser_controls_sha,
            "planned_object_prefixes": ["hydrolakes/releases/v1/", "hydrolakes/display/d1/"],
            "planned_object_url_prefixes": ["https://data.source.coop/nthh/hydrolakes/releases/v1/",
                                            "https://data.source.coop/nthh/hydrolakes/display/d1/"],
            "tested_object_urls": ["https://data.source.coop/nthh/hydrolakes/display/d1/tiles.pmtiles",
                                   "https://data.source.coop/nthh/hydrolakes/releases/v1/rows.parquet"],
            "viewer_config_sha256": "c" * 64, "viewer_build_sha256": "d" * 64}]}))
    remote_objects = {"/nthh/hydrolakes/releases/v1/rows.parquet": parquet,
                      "/nthh/hydrolakes/releases/v1/collection.json": collection,
                      "/nthh/hydrolakes/releases/v1/catalog.json": catalog,
                      "/nthh/hydrolakes/releases/v1/README.md": readme,
                      "/nthh/hydrolakes/releases/v1/manifest.json": package_manifest,
                      "/nthh/hydrolakes/display/d1/tiles.pmtiles": pmtiles,
                      "/nthh/hydrolakes/display/d1/manifest.json": display_manifest,
                      "/nthh/hydrolakes/display/d1/styles/style.json": style}
    return package, display, plan_path, receipt, controls, browser, browser_controls, browser_controls_sha, sha(package_manifest), remote_objects


def run(tmp_path: Path, *, bad_range=False, bad_cors=False, wildcard_cors=False, browser=True):
    package, display, plan, receipt, controls, browser_path, browser_controls, browser_controls_sha, package_manifest_sha, objects = fixture(tmp_path)
    output = tmp_path / "report.json"
    opener = MockOpener(objects, bad_range=bad_range, bad_cors=bad_cors, wildcard_cors=wildcard_cors)
    report = hosted.validate(plan_path=plan, dataset_id="hydrolakes", receipt_path=receipt,
        package_root=package, display_root=display, controls_path=controls, output_path=output,
        package_manifest_sha256=package_manifest_sha, controls_sha256=sha(controls.read_bytes()),
        browser_evidence_path=browser_path if browser else None,
        browser_controls_path=browser_controls if browser else None,
        browser_controls_sha256=browser_controls_sha if browser else None,
        opener=opener, duckdb_connect=lambda **kwargs: FakeDuckDB())
    return report, output, opener


def test_report_passes_only_with_range_cors_receipt_subset_and_browser_evidence(tmp_path):
    report, output, opener = run(tmp_path)
    assert report["status"] == "passed"
    assert all(report["checks"][name] == "passed" for name in hosted.REQUIRED_CHECKS)
    assert report["package_manifest_sha256"] == report["evidence"]["package_manifest"]["sha256"]
    assert report["display_manifest_sha256"] == report["evidence"]["display_manifest"]["sha256"]
    assert report["evidence"]["subset_queries"][0]["rows"] == 1
    assert output.exists()
    assert any(req.method == "OPTIONS" for req in opener.calls)
    assert len(report["evidence"]["range_samples"]) == 2


def _prior_proof_fixture(tmp_path):
    _, _, plan, receipt, *_ = fixture(tmp_path)
    plan_sha = sha(plan.read_bytes())
    entries = hosted.upload.load_plan(plan, "hydrolakes", include_readme=False)[1]
    current = receipt / "objects/0000.json"
    child = json.loads(current.read_text())
    prior = tmp_path / "prior"
    (prior / "objects").mkdir(parents=True)
    old_summary = {"schema_version": 1, "mode": "execute", "status": "failed",
                   "plan_sha256": plan_sha, "object_count": len(entries),
                   "include_readme": False, "failed": 1, "completed": 1}
    (prior / "summary.json").write_text(json.dumps(old_summary))
    index = next(i for i, row in enumerate(entries) if row["object_key"] == child["object_key"])
    name = f"{index:04d}-{sha(child['object_key'].encode())[:16]}.json"
    old_path = prior / "objects" / name
    old_path.write_text(json.dumps(child))
    proof = {"summary_sha256": sha((prior / "summary.json").read_bytes()),
             "record_sha256": sha(old_path.read_bytes()), "record_name": name,
             "prior_status": "uploaded_verified", "plan_sha256": plan_sha,
             "expected_sha256": child["expected_sha256"],
             "expected_size_bytes": child["expected_size_bytes"],
             "remote_sha256": child["remote_sha256"]}
    entry = next(row for row in entries if row["object_key"] == child["object_key"])
    child.update({"status": "verified_prior_attempt", "prior_proof": proof,
                  "remote_sha256_scope": "prior_attempt_full_remote_readback", "bytes_transferred": 0,
                  "current_head": {"checked_at": datetime.now(timezone.utc).isoformat(),
                                   "http_status": 200, "size_bytes": entry["size_bytes"],
                                   "content_type": entry["content_type"]}})
    current.write_text(json.dumps(child))
    return receipt, prior, plan_sha, entries, current, old_path


def test_verified_prior_attempt_requires_original_byte_proof_and_current_head(tmp_path):
    receipt, prior, plan_sha, entries, current, old_path = _prior_proof_fixture(tmp_path)
    records = hosted._receipt_records(receipt, plan_sha, entries, [prior])
    assert sum(row["status"] == "verified_prior_attempt" for row in records.values()) == 1
    with pytest.raises(hosted.HostedValidationError, match="prior full-byte proof"):
        hosted._receipt_records(receipt, plan_sha, entries)
    old_path.write_text(old_path.read_text() + " ")
    with pytest.raises(hosted.HostedValidationError, match="record bytes differ"):
        hosted._receipt_records(receipt, plan_sha, entries, [prior])


@pytest.mark.parametrize("change", ["wrong_sha", "wrong_head", "missing_date", "wrong_scope"])
def test_verified_prior_attempt_rejects_forged_child_proof(tmp_path, change):
    receipt, prior, plan_sha, entries, current, _ = _prior_proof_fixture(tmp_path)
    row = json.loads(current.read_text())
    if change == "wrong_sha":
        row["prior_proof"]["record_sha256"] = "0" * 64
    elif change == "wrong_head":
        row["current_head"]["size_bytes"] += 1
    elif change == "missing_date":
        row["current_head"]["checked_at"] = "2026-11-06T12:00:00"
    else:
        row["remote_sha256_scope"] = "current_head"
    current.write_text(json.dumps(row))
    with pytest.raises(hosted.HostedValidationError):
        hosted._receipt_records(receipt, plan_sha, entries, [prior])


def _multipart_parent_fixture(tmp_path, *, parent_state="abort_failed"):
    receipt, prior, plan_sha, entries, _, _ = _prior_proof_fixture(tmp_path)
    target_index = 1
    entry = entries[target_index]
    old_name = f"{target_index:04d}-{sha(entry['object_key'].encode())[:16]}.json"
    old_path = prior / "objects" / old_name
    old = {"schema_version": 1, "plan_sha256": plan_sha, "bucket": "nthh",
           "object_key": entry["object_key"], "expected_sha256": entry["sha256"],
           "expected_size_bytes": entry["size_bytes"], "mutable": False,
           "remote_sha256": None, "status": "failed",
           "multipart": {"state": parent_state, "upload_id": "original-owned-id", "parts": []}}
    old_path.write_text(json.dumps(old))
    summary_path = receipt / "summary.json"
    summary = json.loads(summary_path.read_text())
    summary.update({"resume_mode": "existing_multipart", "resumed_multipart": 1,
                    "multipart_resume_parent_summary_sha256": sha((prior / "summary.json").read_bytes())})
    summary_path.write_text(json.dumps(summary))
    target_path = receipt / "objects" / f"{target_index:04d}.json"
    target = json.loads(target_path.read_text())
    target.update({"bytes_transferred": entry["size_bytes"],
                   "remote_sha256_scope": "current_attempt_full_remote_readback",
                   "multipart": {"state": "completed", "upload_id": "original-owned-id", "parts": []},
                   "multipart_resume": {"mode": "existing_multipart",
                                         "summary_sha256": sha((prior / "summary.json").read_bytes()),
                                         "record_sha256": sha(old_path.read_bytes()),
                                         "record_name": old_name}})
    target_path.write_text(json.dumps(target))
    return receipt, prior, plan_sha, entries, target_path, old_path


def _multipart_parent_pins(prior, old_path):
    return {"expected_multipart_parent_summary_sha256": sha((prior / "summary.json").read_bytes()),
            "expected_multipart_parent_record_sha256": sha(old_path.read_bytes())}


@pytest.mark.parametrize("parent_state", ["open", "abort_failed"])
def test_multipart_resume_hosted_receipt_binds_original_failed_parent(tmp_path, parent_state):
    receipt, prior, plan_sha, entries, target_path, old_path = _multipart_parent_fixture(
        tmp_path, parent_state=parent_state)
    records = hosted._receipt_records(receipt, plan_sha, entries, [prior],
                                      **_multipart_parent_pins(prior, old_path))
    target = records[entries[1]["object_key"]]
    assert target["status"] == "uploaded_verified"
    assert target["multipart_resume"]["record_sha256"] == sha(old_path.read_bytes())
    assert target["multipart"]["upload_id"] == json.loads(old_path.read_text())["multipart"]["upload_id"]


@pytest.mark.parametrize("change", ["missing_parent", "changed_parent_bytes", "wrong_parent_record_sha",
                                    "wrong_parent_summary_sha", "wrong_parent_key", "wrong_parent_size",
                                    "wrong_parent_state", "wrong_upload_id", "unfinished_target",
                                    "wrong_remote_scope", "wrong_summary_count", "missing_resume_record"])
def test_multipart_resume_hosted_receipt_rejects_broken_parent_chain(tmp_path, change):
    receipt, prior, plan_sha, entries, target_path, old_path = _multipart_parent_fixture(tmp_path)
    pins = _multipart_parent_pins(prior, old_path)
    summary_path = receipt / "summary.json"
    summary = json.loads(summary_path.read_text())
    target = json.loads(target_path.read_text())
    old = json.loads(old_path.read_text())
    if change == "missing_parent":
        old_path.unlink()
    elif change == "changed_parent_bytes":
        old_path.write_text(old_path.read_text() + " ")
    elif change == "wrong_parent_record_sha":
        target["multipart_resume"]["record_sha256"] = "0" * 64
    elif change == "wrong_parent_summary_sha":
        target["multipart_resume"]["summary_sha256"] = "0" * 64
    elif change == "wrong_parent_key":
        old["object_key"] = "other/key"
        old_path.write_text(json.dumps(old))
        target["multipart_resume"]["record_sha256"] = sha(old_path.read_bytes())
    elif change == "wrong_parent_size":
        old["expected_size_bytes"] += 1
        old_path.write_text(json.dumps(old))
        target["multipart_resume"]["record_sha256"] = sha(old_path.read_bytes())
    elif change == "wrong_parent_state":
        old["multipart"]["state"] = "completed"
        old_path.write_text(json.dumps(old))
        target["multipart_resume"]["record_sha256"] = sha(old_path.read_bytes())
    elif change == "wrong_upload_id":
        target["multipart"]["upload_id"] = "other-id"
    elif change == "unfinished_target":
        target["multipart"]["state"] = "open"
    elif change == "wrong_remote_scope":
        target["remote_sha256_scope"] = "prior_attempt_full_remote_readback"
    elif change == "wrong_summary_count":
        summary["resumed_multipart"] = 2
    else:
        target.pop("multipart_resume")
    target_path.write_text(json.dumps(target))
    summary_path.write_text(json.dumps(summary))
    with pytest.raises(hosted.HostedValidationError, match="multipart"):
        hosted._receipt_records(receipt, plan_sha, entries, [prior], **pins)


def test_multipart_resume_reused_byte_proofs_share_target_parent(tmp_path):
    import shutil
    receipt, prior, plan_sha, entries, _, old_path = _multipart_parent_fixture(tmp_path)
    pins = _multipart_parent_pins(prior, old_path)
    other = tmp_path / "other-prior"
    shutil.copytree(prior, other)
    (other / "summary.json").write_text((other / "summary.json").read_text() + " ")
    child_path = next(path for path in (receipt / "objects").glob("*.json")
                      if "prior_proof" in json.loads(path.read_text()))
    child = json.loads(child_path.read_text())
    child["prior_proof"]["summary_sha256"] = sha((other / "summary.json").read_bytes())
    child_path.write_text(json.dumps(child))
    with pytest.raises(hosted.HostedValidationError, match="prior full-byte proof"):
        hosted._receipt_records(receipt, plan_sha, entries, [prior, other], **pins)


@pytest.mark.parametrize("provided", [(), ("summary",), ("record",), ("summary", "record")])
def test_multipart_parent_requires_exact_paired_frozen_digests(tmp_path, provided):
    receipt, prior, plan_sha, entries, _, old_path = _multipart_parent_fixture(tmp_path)
    original = _multipart_parent_pins(prior, old_path)
    pins = {}
    if "summary" in provided:
        pins["expected_multipart_parent_summary_sha256"] = (
            "0" * 64 if len(provided) == 2 else original["expected_multipart_parent_summary_sha256"])
    if "record" in provided:
        pins["expected_multipart_parent_record_sha256"] = (
            "0" * 64 if len(provided) == 2 else original["expected_multipart_parent_record_sha256"])
    with pytest.raises(hosted.HostedValidationError, match="multipart"):
        hosted._receipt_records(receipt, plan_sha, entries, [prior], **pins)


@pytest.mark.parametrize("wrong", ["summary", "record"])
def test_multipart_parent_refuses_either_wrong_independent_digest(tmp_path, wrong):
    receipt, prior, plan_sha, entries, _, old_path = _multipart_parent_fixture(tmp_path)
    pins = _multipart_parent_pins(prior, old_path)
    pins[f"expected_multipart_parent_{wrong}_sha256"] = "0" * 64
    with pytest.raises(hosted.HostedValidationError, match="multipart"):
        hosted._receipt_records(receipt, plan_sha, entries, [prior], **pins)


def test_multipart_parent_refuses_coherent_alternate_receipt_with_original_pins(tmp_path):
    receipt, prior, plan_sha, entries, target_path, old_path = _multipart_parent_fixture(tmp_path)
    frozen_pins = _multipart_parent_pins(prior, old_path)
    parent_summary_path = prior / "summary.json"
    parent_summary = json.loads(parent_summary_path.read_text())
    parent_summary["coherent_alternate_note"] = "different parent bytes"
    parent_summary_path.write_text(json.dumps(parent_summary))
    old = json.loads(old_path.read_text())
    old["coherent_alternate_note"] = "different failed record bytes"
    old_path.write_text(json.dumps(old))
    alternate_summary_sha = sha(parent_summary_path.read_bytes())
    alternate_record_sha = sha(old_path.read_bytes())
    summary_path = receipt / "summary.json"
    summary = json.loads(summary_path.read_text())
    summary["multipart_resume_parent_summary_sha256"] = alternate_summary_sha
    summary_path.write_text(json.dumps(summary))
    target = json.loads(target_path.read_text())
    target["multipart_resume"]["summary_sha256"] = alternate_summary_sha
    target["multipart_resume"]["record_sha256"] = alternate_record_sha
    target_path.write_text(json.dumps(target))
    for path in (receipt / "objects").glob("*.json"):
        child = json.loads(path.read_text())
        if child.get("prior_proof"):
            child["prior_proof"]["summary_sha256"] = alternate_summary_sha
            path.write_text(json.dumps(child))
    assert hosted._receipt_records(receipt, plan_sha, entries, [prior],
                                   **_multipart_parent_pins(prior, old_path))
    with pytest.raises(hosted.HostedValidationError, match="frozen parent"):
        hosted._receipt_records(receipt, plan_sha, entries, [prior], **frozen_pins)


def test_normal_receipts_reject_unrelated_multipart_pins(tmp_path):
    _, _, plan, receipt, *_ = fixture(tmp_path)
    plan_sha, entries = hosted.upload.load_plan(plan, "hydrolakes", include_readme=False)
    with pytest.raises(hosted.HostedValidationError, match="normal receipt"):
        hosted._receipt_records(receipt, plan_sha, entries,
            expected_multipart_parent_summary_sha256="a" * 64,
            expected_multipart_parent_record_sha256="b" * 64)


def test_multipart_parent_evidence_records_frozen_hashes_and_record_name(tmp_path):
    receipt, prior, _, entries, _, old_path = _multipart_parent_fixture(tmp_path)
    package, display = tmp_path / "package", tmp_path / "display"
    controls = tmp_path / "controls.json"
    browser = tmp_path / "browser.json"
    browser_controls = tmp_path / "browser-controls.json"
    sources = hosted.upload.resolve_sources(entries, {"hydrolakes": package},
                                            {"hydrolakes": display}, tmp_path)
    objects = {f"/nthh/{entry['object_key']}": path.read_bytes() for entry, path in sources}
    pins = _multipart_parent_pins(prior, old_path)
    report = hosted.validate(
        plan_path=tmp_path / "plan.json", dataset_id="hydrolakes", receipt_path=receipt,
        package_root=package, display_root=display, controls_path=controls,
        output_path=tmp_path / "multipart-report.json",
        package_manifest_sha256=sha((package / "manifest.json").read_bytes()),
        controls_sha256=sha(controls.read_bytes()), prior_receipt_paths=[prior],
        browser_evidence_path=browser, browser_controls_path=browser_controls,
        browser_controls_sha256=sha(browser_controls.read_bytes()),
        opener=MockOpener(objects), duckdb_connect=lambda **kwargs: FakeDuckDB(), **pins)
    assert report["status"] == "passed"
    parent = report["evidence"]["multipart_resume_parent"]
    assert parent == {"object_key": entries[1]["object_key"],
                      "summary_sha256": pins["expected_multipart_parent_summary_sha256"],
                      "record_name": old_path.name,
                      "record_sha256": pins["expected_multipart_parent_record_sha256"],
                      "remote_sha256_scope": "current_attempt_full_remote_readback"}


def _multipart_cli_args(tmp_path, receipt, prior):
    package, display = tmp_path / "package", tmp_path / "display"
    controls = tmp_path / "controls.json"
    return ["--plan", str(tmp_path / "plan.json"), "--dataset", "hydrolakes",
            "--receipt", str(receipt), "--package", str(package),
            "--display-package", str(display),
            "--package-manifest-sha256", sha((package / "manifest.json").read_bytes()),
            "--query-controls", str(controls), "--controls-sha256", sha(controls.read_bytes()),
            "--prior-receipt", str(prior), "--output", str(tmp_path / "cli-report.json")]


@pytest.mark.parametrize("provided", [(), ("summary",), ("record",)])
def test_multipart_cli_refuses_missing_or_partial_parent_pins(tmp_path, monkeypatch, capsys, provided):
    receipt, prior, _, _, _, old_path = _multipart_parent_fixture(tmp_path)
    pins = _multipart_parent_pins(prior, old_path)
    args = _multipart_cli_args(tmp_path, receipt, prior)
    if "summary" in provided:
        args += ["--expected-multipart-parent-summary-sha256",
                 pins["expected_multipart_parent_summary_sha256"]]
    if "record" in provided:
        args += ["--expected-multipart-parent-record-sha256",
                 pins["expected_multipart_parent_record_sha256"]]
    original_validate = hosted.validate

    def offline_validate(**kwargs):
        kwargs["opener"] = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("CLI test must not make a network request"))
        return original_validate(**kwargs)

    monkeypatch.setattr(hosted, "validate", offline_validate)
    assert hosted.main(args) == 1
    assert "multipart parent" in capsys.readouterr().err
    assert not (tmp_path / "cli-report.json").exists()


def test_multipart_cli_forwards_both_parent_pins(tmp_path, monkeypatch):
    receipt, prior, _, _, _, old_path = _multipart_parent_fixture(tmp_path)
    pins = _multipart_parent_pins(prior, old_path)
    args = _multipart_cli_args(tmp_path, receipt, prior)
    args += ["--expected-multipart-parent-summary-sha256",
             pins["expected_multipart_parent_summary_sha256"],
             "--expected-multipart-parent-record-sha256",
             pins["expected_multipart_parent_record_sha256"]]
    received = {}

    def capture_validate(**kwargs):
        received.update(kwargs)
        return {"dataset_id": "hydrolakes", "status": "failed", "checks": {}, "failures": []}

    monkeypatch.setattr(hosted, "validate", capture_validate)
    assert hosted.main(args) == 1
    assert received["expected_multipart_parent_summary_sha256"] == pins[
        "expected_multipart_parent_summary_sha256"]
    assert received["expected_multipart_parent_record_sha256"] == pins[
        "expected_multipart_parent_record_sha256"]


def _spatial_fixture(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    parquet = tmp_path / "rows.parquet"
    bbox_type = pa.struct([("xmin", pa.float64()), ("ymin", pa.float64()),
                           ("xmax", pa.float64()), ("ymax", pa.float64())])
    table = pa.table({"FID": pa.array([7], type=pa.int64()),
                      "bbox": pa.array([{"xmin": 1., "ymin": 2., "xmax": 3., "ymax": 4.}], type=bbox_type),
                      "geometry": pa.array([b"wkb"], type=pa.binary())})
    pq.write_table(table, parquet)
    entry = {"source": {"path": "rows.parquet"}, "sha256": sha(parquet.read_bytes()),
             "size_bytes": parquet.stat().st_size, "content_type": "application/vnd.apache.parquet"}
    query = {"name": "one", "path": "rows.parquet", "id_column": "FID", "ids": [7],
             "selection": {"row_count": 1}}
    hint = {"name": "one", "path": "rows.parquet", "id_column": "FID", "ids": [7],
            "covering_bbox_status": "validated", "covering_bbox_column": "bbox",
            "covering_bbox_fields": {key: f"bbox.{key}" for key in ("xmin", "ymin", "xmax", "ymax")},
            "parquet_object_sha256": entry["sha256"], "parquet_object_size_bytes": entry["size_bytes"],
            "selected_ids": [{"id": 7, "local_id_match_count": 1,
                              "covering_encloses_source_wkb": True,
                              "covering_bbox": {"minx": 1., "miny": 2., "maxx": 3., "maxy": 4.},
                              "center": {"x": 2., "y": 3.}}]}
    hints = {"schema_version": 1, "kind": "local_spatial_query_supplement",
             "original_query_controls_sha256": "a" * 64,
             "immutable_upload_plan_sha256": "b" * 64,
             "datasets": {"hydrolakes": {"queries": [hint]}}}
    path = tmp_path / "hints.json"
    path.write_text(json.dumps(hints))
    return parquet, entry, query, hint, hints, path


def test_spatial_hint_binds_frozen_id_and_unchanged_local_bbox(tmp_path):
    parquet, entry, query, hint, hints, path = _spatial_fixture(tmp_path)
    mapping, _ = hosted._load_spatial_hints(path, sha(path.read_bytes()), dataset_id="hydrolakes",
        controls_sha="a" * 64, plan_sha="b" * 64, queries=[query],
        parquet_entries=[(entry, parquet, "https://data.source.coop/nthh/hydrolakes/releases/v1/rows.parquet")])
    rows = hosted._duckdb_compare([query], {"rows.parquet": parquet}, {"rows.parquet": str(parquet)},
                                  spatial_hints=mapping, connect=local_parquet_connect(tmp_path))
    assert rows[0]["rows"] == 1 and rows[0]["spatial_hint"]["local_bbox_verified"]
    hint["selected_ids"][0]["covering_bbox"]["minx"] = 0.
    hint["selected_ids"][0]["center"]["x"] = 1.5
    path.write_text(json.dumps(hints))
    mapping, _ = hosted._load_spatial_hints(path, sha(path.read_bytes()), dataset_id="hydrolakes",
        controls_sha="a" * 64, plan_sha="b" * 64, queries=[query],
        parquet_entries=[(entry, parquet, "https://data.source.coop/nthh/hydrolakes/releases/v1/rows.parquet")])
    with pytest.raises(hosted.HostedValidationError, match="bbox changed"):
        hosted._duckdb_compare([query], {"rows.parquet": parquet}, {"rows.parquet": str(parquet)},
                               spatial_hints=mapping, connect=local_parquet_connect(tmp_path))


@pytest.mark.parametrize("remote_change,phrase", [
    ("filtered_bbox", "spatial predicate omitted"),
    ("different_geometry", "subset differs"),
])
def test_spatial_comparison_requires_each_selected_row_and_exact_all_columns(tmp_path, remote_change, phrase):
    import pyarrow as pa
    import pyarrow.parquet as pq
    parquet, entry, query, hint, hints, path = _spatial_fixture(tmp_path)
    mapping, _ = hosted._load_spatial_hints(path, sha(path.read_bytes()), dataset_id="hydrolakes",
        controls_sha="a" * 64, plan_sha="b" * 64, queries=[query],
        parquet_entries=[(entry, parquet, "https://data.source.coop/nthh/hydrolakes/releases/v1/rows.parquet")])
    remote = tmp_path / "remote.parquet"
    original = pq.read_table(parquet)
    if remote_change == "filtered_bbox":
        replacement = pa.array([{"xmin": 10., "ymin": 20., "xmax": 12., "ymax": 22.}],
                               type=original.schema.field("bbox").type)
        changed = original.set_column(1, "bbox", replacement)
    else:
        changed = original.set_column(2, "geometry", pa.array([b"changed WKB"]))
    pq.write_table(changed, remote)
    with pytest.raises(hosted.HostedValidationError, match=phrase):
        hosted._duckdb_compare([query], {"rows.parquet": parquet}, {"rows.parquet": str(remote)},
                               spatial_hints=mapping, connect=local_parquet_connect(tmp_path))


@pytest.mark.parametrize("change", ["id", "sha", "controls", "missing"])
def test_spatial_hint_rejects_changed_identity_or_missing_id(tmp_path, change):
    parquet, entry, query, hint, hints, path = _spatial_fixture(tmp_path)
    if change == "id":
        hint["ids"] = [8]
    elif change == "sha":
        hint["parquet_object_sha256"] = "0" * 64
    elif change == "controls":
        hints["original_query_controls_sha256"] = "0" * 64
    else:
        hint["selected_ids"] = []
    path.write_text(json.dumps(hints))
    with pytest.raises(hosted.HostedValidationError):
        hosted._load_spatial_hints(path, sha(path.read_bytes()), dataset_id="hydrolakes",
            controls_sha="a" * 64, plan_sha="b" * 64, queries=[query],
            parquet_entries=[(entry, parquet, "https://data.source.coop/nthh/hydrolakes/releases/v1/rows.parquet")])


def test_anonymous_cors_wildcards_satisfy_range_preflight_and_exposure(tmp_path):
    report, _, _ = run(tmp_path, wildcard_cors=True)
    assert report["status"] == "passed"
    assert report["checks"]["cors"] == "passed"


@pytest.mark.parametrize("kwargs,phrase", [
    ({"bad_range": True}, "ranged GET"),
    ({"bad_cors": True}, "CORS ranged GET"),
])
def test_actual_hosted_failures_are_reported(tmp_path, kwargs, phrase):
    report, _, _ = run(tmp_path, **kwargs)
    assert report["status"] == "failed"
    assert report["failures"] and phrase in report["failures"][0]


def test_browser_render_remains_unrun_without_external_evidence(tmp_path):
    report, _, _ = run(tmp_path, browser=False)
    assert report["status"] == "failed"
    assert report["checks"]["browser_render"] == "not_run"


def test_bad_full_remote_receipt_hash_is_rejected_before_network(tmp_path):
    package, display, plan, receipt, controls, browser, browser_controls, browser_controls_sha, package_manifest_sha, objects = fixture(tmp_path)
    record = next((receipt / "objects").glob("*.json"))
    data = json.loads(record.read_text())
    data["remote_sha256"] = "0" * 64
    record.write_text(json.dumps(data))
    with pytest.raises(hosted.HostedValidationError, match="full remote checksum proof"):
        hosted.validate(plan_path=plan, dataset_id="hydrolakes", receipt_path=receipt,
            package_root=package, display_root=display, controls_path=controls,
            output_path=tmp_path / "report.json", package_manifest_sha256=package_manifest_sha,
            controls_sha256=sha(controls.read_bytes()),
            browser_evidence_path=browser, opener=MockOpener(objects),
            browser_controls_path=browser_controls, browser_controls_sha256=browser_controls_sha,
            duckdb_connect=lambda **kwargs: FakeDuckDB())


def test_fixed_query_controls_limit_ids_and_bind_dataset(tmp_path):
    controls = tmp_path / "controls.json"
    controls.write_text(json.dumps({"schema_version": 1, "dataset_id": "hydrolakes",
        "plan_sha256": "a" * 64, "release": "v1", "queries": [
        {"name": "too many", "path": "rows.parquet", "id_column": "FID", "ids": [1, 2, 3, 4],
         "selection": {"row_count": 1}}]}))
    with pytest.raises(hosted.HostedValidationError, match="1-3 fixed IDs"):
        hosted._load_query_controls(controls, "hydrolakes", release="v1", plan_sha="a" * 64,
            expected_sha256=sha(controls.read_bytes()), expected_parquet_paths={"rows.parquet"})


def test_query_controls_require_exact_parquet_inventory_and_binding(tmp_path):
    controls = tmp_path / "controls.json"
    controls.write_text(json.dumps({"schema_version": 1, "dataset_id": "hydrolakes",
        "plan_sha256": "a" * 64, "release": "wrong", "queries": [
        {"name": "only one", "path": "rows.parquet", "id_column": "FID", "ids": [1],
         "selection": {"row_count": 1}}]}))
    with pytest.raises(hosted.HostedValidationError, match="another package release"):
        hosted._load_query_controls(controls, "hydrolakes", release="v1", plan_sha="a" * 64,
            expected_sha256=sha(controls.read_bytes()), expected_parquet_paths={"rows.parquet"})
    controls_data = json.loads(controls.read_text())
    controls_data["release"] = "v1"
    controls.write_text(json.dumps(controls_data))
    with pytest.raises(hosted.HostedValidationError, match="exactly cover every analytic Parquet"):
        hosted._load_query_controls(controls, "hydrolakes", release="v1", plan_sha="a" * 64,
            expected_sha256=sha(controls.read_bytes()),
            expected_parquet_paths={"rows.parquet", "another-layer.parquet"})


def test_package_manifest_must_match_local_bytes_and_plan_pin(tmp_path):
    package, display, plan, receipt, controls, browser, browser_controls, browser_controls_sha, package_sha, objects = fixture(tmp_path)
    (package / "manifest.json").write_text('{"tampered":true}')
    with pytest.raises(hosted.HostedValidationError, match="manifest local bytes"):
        hosted.validate(plan_path=plan, dataset_id="hydrolakes", receipt_path=receipt,
            package_root=package, display_root=display, controls_path=controls,
            output_path=tmp_path / "report.json", package_manifest_sha256=package_sha,
            controls_sha256=sha(controls.read_bytes()), opener=MockOpener(objects),
            duckdb_connect=lambda **kwargs: FakeDuckDB())


def test_browser_evidence_must_match_frozen_cases_and_pmtiles_inventory(tmp_path):
    package, display, plan, receipt, controls, browser, browser_controls, browser_controls_sha, package_sha, objects = fixture(tmp_path)
    data = json.loads(browser.read_text())
    data["datasets"][0]["case_ids"] = ["arbitrary-case"]
    browser.write_text(json.dumps(data))
    plan_data = json.loads(plan.read_text())
    product = plan_data["products"][0]
    plan_sha = sha(plan.read_bytes())
    planned_assets = {f"https://data.source.coop/nthh/{row['object_key']}": {
        "sha256": row["sha256"], "size_bytes": row["size_bytes"], "content_type": row["content_type"]}
        for row in plan_data["files"]}
    with pytest.raises(hosted.HostedValidationError, match="incomplete or bound"):
        hosted._browser_record(browser, dataset_id="hydrolakes", product=product, plan_sha=plan_sha,
            planned_urls=set(planned_assets), controls_path=browser_controls,
            controls_sha256=browser_controls_sha, planned_assets=planned_assets)


def test_browser_accepts_planned_analytic_request_without_provenance_pmtiles_request(tmp_path):
    package, display, plan, receipt, controls, browser, browser_controls, _, _, objects = fixture(tmp_path)
    plan_data = json.loads(plan.read_text())
    product = plan_data["products"][0]
    plan_sha = sha(plan.read_bytes())
    planned_assets = {f"https://data.source.coop/nthh/{row['object_key']}": {
        "sha256": row["sha256"], "size_bytes": row["size_bytes"], "content_type": row["content_type"]}
        for row in plan_data["files"]}
    provenance = "https://data.source.coop/nthh/hydrolakes/display/d1/reports/provenance.pmtiles"
    planned_assets[provenance] = {"sha256": "a" * 64, "size_bytes": 10,
                                  "content_type": "application/vnd.pmtiles"}
    frozen = json.loads(browser_controls.read_text())
    frozen["objects"][provenance] = planned_assets[provenance]
    browser_controls.write_text(json.dumps(frozen))
    frozen_sha = sha(browser_controls.read_bytes())
    evidence = json.loads(browser.read_text())
    evidence["browser_cases_sha256"] = frozen_sha
    evidence["datasets"][0]["browser_cases_sha256"] = frozen_sha
    browser.write_text(json.dumps(evidence))
    row = hosted._browser_record(browser, dataset_id="hydrolakes", product=product, plan_sha=plan_sha,
        planned_urls=set(planned_assets), controls_path=browser_controls,
        controls_sha256=frozen_sha, planned_assets=planned_assets)
    assert provenance not in row["tested_object_urls"]
    assert "https://data.source.coop/nthh/hydrolakes/releases/v1/rows.parquet" in row["tested_object_urls"]


def test_browser_missing_display_request_is_refused(tmp_path):
    package, display, plan, receipt, controls, browser, browser_controls, frozen_sha, _, objects = fixture(tmp_path)
    plan_data = json.loads(plan.read_text())
    planned_assets = {f"https://data.source.coop/nthh/{row['object_key']}": {
        "sha256": row["sha256"], "size_bytes": row["size_bytes"], "content_type": row["content_type"]}
        for row in plan_data["files"]}
    evidence = json.loads(browser.read_text())
    analytic = "https://data.source.coop/nthh/hydrolakes/releases/v1/rows.parquet"
    evidence["cases"][0]["requests"] = [{"url": analytic, "status_check": "passed"}]
    evidence["datasets"][0]["tested_object_urls"] = [analytic]
    browser.write_text(json.dumps(evidence))
    with pytest.raises(hosted.HostedValidationError, match="did not request its required hosted assets"):
        hosted._browser_record(browser, dataset_id="hydrolakes", product=plan_data["products"][0],
            plan_sha=sha(plan.read_bytes()), planned_urls=set(planned_assets),
            controls_path=browser_controls, controls_sha256=frozen_sha, planned_assets=planned_assets)


def test_browser_cannot_relabel_regional_case_to_avoid_analytic_lookup(tmp_path):
    _, _, plan, _, _, browser, browser_controls, frozen_sha, _, _ = fixture(tmp_path)
    plan_data = json.loads(plan.read_text())
    planned_assets = {f"https://data.source.coop/nthh/{row['object_key']}": {
        "sha256": row["sha256"], "size_bytes": row["size_bytes"], "content_type": row["content_type"]}
        for row in plan_data["files"]}
    evidence = json.loads(browser.read_text())
    evidence["cases"][0]["region"] = "global"
    browser.write_text(json.dumps(evidence))
    with pytest.raises(hosted.HostedValidationError, match="case view differs"):
        hosted._browser_record(browser, dataset_id="hydrolakes", product=plan_data["products"][0],
            plan_sha=sha(plan.read_bytes()), planned_urls=set(planned_assets),
            controls_path=browser_controls, controls_sha256=frozen_sha, planned_assets=planned_assets)


def test_duckdb_footer_count_is_per_file_with_multiple_columns_and_row_groups(tmp_path):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    parquet = tmp_path / "multi-column.parquet"
    table = pa.table({"id": [1, 2, 3, 4], "value": ["a", "b", "c", "d"],
                      "geometry": [b"g1", b"g2", b"g3", b"g4"]})
    pq.write_table(table, parquet, row_group_size=2)
    query = {"name": "multi-column", "path": "multi-column.parquet", "id_column": "id",
             "ids": [1, 4], "selection": {"row_count": 4}}
    results = hosted._duckdb_compare([query], {query["path"]: parquet},
        {query["path"]: str(parquet)}, connect=local_parquet_connect(tmp_path))
    assert results[0]["footer_rows"] == 4
    assert results[0]["rows"] == 2
    assert results[0]["id_multiplicity"] == {"1": 1, "4": 1}


def _multi_id_parquet(tmp_path, name, ids, *, values=None, geometries=None):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    path = tmp_path / name
    values = values if values is not None else [f"value-{index}" for index in range(len(ids))]
    geometries = geometries if geometries is not None else [f"wkb-{index}".encode() for index in range(len(ids))]
    pq.write_table(pa.table({"feature_id": pa.array(ids, type=pa.int64()),
                             "attribute": values, "geometry": geometries}), path, row_group_size=2)
    return path


def test_duckdb_exact_equality_queries_cover_all_frozen_ids_and_match_in_multiset(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    ids = [145242909048833, 151225798516737, 206669531324417]
    parquet = _multi_id_parquet(tmp_path, "rows.parquet", [ids[0], ids[0], ids[1], 10, ids[2]])
    query = {"name": "grwl", "path": "rows.parquet", "id_column": "feature_id",
             "ids": ids, "selection": {"row_count": 5}}
    statements = []
    base_connect = local_parquet_connect(tmp_path)

    def recording_connect(**kwargs):
        adapter = base_connect(**kwargs)
        original_execute = adapter.execute

        def execute(sql, params=None):
            statements.append((sql, params))
            return original_execute(sql, params)

        adapter.execute = execute
        return adapter

    result = hosted._duckdb_compare([query], {"rows.parquet": parquet},
                                    {"rows.parquet": str(parquet)}, connect=recording_connect)[0]
    assert result["id_multiplicity"] == {str(ids[0]): 2, str(ids[1]): 1, str(ids[2]): 1}
    assert result["rows"] == 4
    row_queries = [(sql, params) for sql, params in statements
                   if sql.startswith("SELECT * FROM read_parquet")]
    count_queries = [(sql, params) for sql, params in statements
                     if "count(*) FROM read_parquet" in sql]
    assert len(row_queries) == len(count_queries) == 2 * len(ids)
    for queries in (row_queries, count_queries):
        assert {params[1] for _, params in queries} == {str(value) for value in ids}
        assert all('"feature_id" = ?' in sql and " IN (" not in sql for sql, _ in queries)

    con = duckdb.connect(config={"autoload_known_extensions": "false",
                                 "autoinstall_known_extensions": "false"})
    try:
        old_rows = con.execute("SELECT * FROM read_parquet(?) WHERE feature_id IN (?, ?, ?)",
                               [str(parquet), *ids]).fetchall()
    finally:
        con.close()
    old_multiset = Counter(hosted._normalize_row(row) for row in old_rows)
    assert result["result_sha256"] == sha("\n".join(sorted(old_multiset.elements())).encode())


@pytest.mark.parametrize("change,phrase", [
    ("missing_id", "IDs are missing"),
    ("attribute", "subset differs"),
    ("geometry", "subset differs"),
])
def test_duckdb_exact_equality_rejects_missing_id_or_changed_full_row(tmp_path, change, phrase):
    ids = [145242909048833, 151225798516737, 206669531324417]
    local = _multi_id_parquet(tmp_path, "local.parquet", ids)
    remote_ids = ids[:2] + [8] if change == "missing_id" else ids
    values = ["value-0", "changed", "value-2"] if change == "attribute" else None
    geometries = [b"wkb-0", b"changed", b"wkb-2"] if change == "geometry" else None
    remote = _multi_id_parquet(tmp_path, "remote.parquet", remote_ids,
                               values=values, geometries=geometries)
    query = {"name": "grwl", "path": "rows.parquet", "id_column": "feature_id",
             "ids": ids, "selection": {"row_count": 3}}
    with pytest.raises(hosted.HostedValidationError, match=phrase):
        hosted._duckdb_compare([query], {"rows.parquet": local}, {"rows.parquet": str(remote)},
                               connect=local_parquet_connect(tmp_path))


def test_duckdb_exact_equality_total_cap_is_across_ids(tmp_path):
    ids = [145242909048833, 151225798516737]
    parquet = _multi_id_parquet(tmp_path, "many.parquet", [ids[0]] * 501 + [ids[1]] * 501)
    query = {"name": "grwl", "path": "rows.parquet", "id_column": "feature_id",
             "ids": ids, "selection": {"row_count": 1002}}
    with pytest.raises(hosted.HostedValidationError, match="1000-row comparison cap"):
        hosted._duckdb_compare([query], {"rows.parquet": parquet},
                               {"rows.parquet": str(parquet)}, connect=local_parquet_connect(tmp_path))


def test_duckdb_exact_equality_rejects_duplicate_frozen_id(tmp_path):
    parquet = _multi_id_parquet(tmp_path, "rows.parquet", [7])
    query = {"name": "one", "path": "rows.parquet", "id_column": "feature_id",
             "ids": [7, 7], "selection": {"row_count": 1}}
    with pytest.raises(hosted.HostedValidationError, match="must be distinct"):
        hosted._duckdb_compare([query], {"rows.parquet": parquet},
                               {"rows.parquet": str(parquet)}, connect=local_parquet_connect(tmp_path))


@pytest.mark.parametrize("id_type,values,selected,expected", [
    ("int64", [1, 2], 1, 1),
    ("string", ["001", "1"], "001", 1),
])
def test_duckdb_exact_equality_preserves_numeric_and_string_id_identity(
        tmp_path, id_type, values, selected, expected):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    parquet = tmp_path / "rows.parquet"
    pq.write_table(pa.table({"feature_id": pa.array(values, type=getattr(pa, id_type)()),
                             "geometry": [b"first", b"second"]}), parquet)
    query = {"name": "ids", "path": "rows.parquet", "id_column": "feature_id",
             "ids": [selected], "selection": {"row_count": 2}}
    result = hosted._duckdb_compare([query], {"rows.parquet": parquet},
                                    {"rows.parquet": str(parquet)},
                                    connect=local_parquet_connect(tmp_path))[0]
    assert result["id_multiplicity"] == {str(selected): expected}
    assert result["rows"] == expected


def test_duckdb_exact_equality_rejects_duplicate_outside_spatial_bbox(tmp_path):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    bbox_type = pa.struct([("xmin", pa.float64()), ("ymin", pa.float64()),
                           ("xmax", pa.float64()), ("ymax", pa.float64())])
    parquet = tmp_path / "rows.parquet"
    pq.write_table(pa.table({"FID": pa.array([7, 7], type=pa.int64()),
                             "bbox": pa.array([{"xmin": 1., "ymin": 2., "xmax": 3., "ymax": 4.},
                                               {"xmin": 10., "ymin": 20., "xmax": 12., "ymax": 22.}],
                                              type=bbox_type),
                             "geometry": [b"first", b"second"]}), parquet)
    query = {"name": "one", "path": "rows.parquet", "id_column": "FID", "ids": [7],
             "selection": {"row_count": 2}}
    hint = {"selected_ids": [{"id": 7, "covering_bbox": {"minx": 1., "miny": 2.,
                                                     "maxx": 3., "maxy": 4.},
                              "center": {"x": 2., "y": 3.}}]}
    with pytest.raises(hosted.HostedValidationError, match="local spatial hint ID multiplicity"):
        hosted._duckdb_compare([query], {"rows.parquet": parquet},
                               {"rows.parquet": str(parquet)}, spatial_hints={"one": hint},
                               connect=local_parquet_connect(tmp_path))
