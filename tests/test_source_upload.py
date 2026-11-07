"""Offline fault checks for the exact-plan Source Cooperative uploader."""
from __future__ import annotations

from io import BytesIO
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/source_publish/upload.py"
SPEC = importlib.util.spec_from_file_location("source_upload", MODULE_PATH)
assert SPEC and SPEC.loader
upload = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = upload
SPEC.loader.exec_module(upload)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fixture_plan(content: bytes = b"package", *, mutable: bool = False) -> dict:
    product = {"dataset_id": "hydrolakes", "product_id": "hydrolakes", "owner": "nthh",
               "bucket": "nthh", "endpoint": upload.ENDPOINT, "release": "v1"}
    key = "hydrolakes/releases/v1/asset.txt"
    file = {"bucket": "nthh", "endpoint": upload.ENDPOINT, "object_key": key,
            "s3_uri_proposed": "s3://nthh/" + key, "source": {"kind": "package", "dataset_id": "hydrolakes", "path": "asset.txt"},
            "size_bytes": len(content), "sha256": digest(content), "content_type": "text/plain"}
    readmes = []
    if mutable:
        key = "hydrolakes/README.md"
        readmes = [{"bucket": "nthh", "endpoint": upload.ENDPOINT, "object_key": key,
                    "s3_uri_proposed": "s3://nthh/" + key,
                    "source": {"kind": "repository", "path": "datasets/hydrolakes/source-coop/product-README.md"},
                    "size_bytes": 6, "sha256": digest(b"README"), "content_type": "text/markdown",
                    "binding_status": "canonical_generated_consumer_copy", "mutable": True}]
    return {"schema_version": 1, "plan_type": "source_coop_immutable_exact_file_plan",
            "products": [product], "files": [file], "file_count": 1, "total_bytes": len(content), "mutable_metadata": readmes}


def load(tmp_path: Path, plan: dict, include_readme: bool = False):
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    return upload.load_plan(path, "hydrolakes", include_readme)


class NotFound(Exception):
    response = {"Error": {"Code": "404"}}


class Forbidden(Exception):
    response = {"Error": {"Code": "403"}}


class FakeS3:
    def __init__(self, objects: dict[str, bytes] | None = None):
        self.objects = dict(objects or {})
        self.types = {key: "text/markdown" if key.endswith(".md") else "text/plain" for key in self.objects}
        self.puts = []
        self.multipart = []
        self.abort_count = 0
        self.head_error = None
        self.get_error = None
        self.get_calls = []

    def head_object(self, *, Bucket, Key):
        assert Bucket == "nthh"
        if self.head_error:
            raise self.head_error
        if Key not in self.objects:
            raise NotFound()
        return {"ResponseMetadata": {"HTTPStatusCode": 200},
                "ContentLength": len(self.objects[Key]), "ContentType": self.types[Key],
                "ETag": '"' + digest(self.objects[Key]) + '"', "Metadata": {"sha256": "untrusted"}}

    def get_object(self, *, Bucket, Key, Range):
        self.get_calls.append(Key)
        if self.get_error:
            raise self.get_error
        match = re.fullmatch(r"bytes=(\d+)-(\d+)", Range)
        assert match and Bucket == "nthh"
        start, end = map(int, match.groups())
        data = self.objects[Key]
        return {"ContentRange": f"bytes {start}-{end}/{len(data)}", "Body": BytesIO(data[start:end + 1])}

    def put_object(self, *, Bucket, Key, Body, ContentLength, IfNoneMatch=None, IfMatch=None, **kwargs):
        assert Bucket == "nthh" and kwargs["Metadata"]["sha256"]
        if Key in self.objects:
            assert IfMatch == '"' + digest(self.objects[Key]) + '"' and IfNoneMatch is None
        else:
            assert IfNoneMatch == "*" and IfMatch is None
        self.puts.append((Key, kwargs))
        self.objects[Key] = Body.read()
        self.types[Key] = kwargs["ContentType"]
        assert len(self.objects[Key]) == ContentLength

    def create_multipart_upload(self, *, Bucket, Key, **kwargs):
        self.multipart.append({"key": Key, "parts": [], "kwargs": kwargs})
        return {"UploadId": "this-invocation"}

    def upload_part(self, *, Bucket, Key, UploadId, PartNumber, Body):
        assert UploadId == "this-invocation"
        self.multipart[-1]["parts"].append(Body)
        return {"ETag": str(PartNumber)}

    def complete_multipart_upload(self, *, Bucket, Key, UploadId, MultipartUpload, IfNoneMatch=None):
        assert IfNoneMatch == "*"
        self.objects[Key] = b"".join(self.multipart[-1]["parts"])
        self.types[Key] = self.multipart[-1]["kwargs"]["ContentType"]

    def abort_multipart_upload(self, *, Bucket, Key, UploadId):
        self.abort_count += 1


class Session:
    def __init__(self, client):
        self.fake = client
        self.calls = 0

    def client(self):
        self.calls += 1
        return self.fake


def sources(tmp_path: Path, content: bytes):
    root = tmp_path / "data"
    root.mkdir()
    package = root / "package"
    package.mkdir()
    (package / "asset.txt").write_bytes(content)
    _, entries = load(tmp_path, fixture_plan(content))
    return upload.resolve_sources(entries, {"hydrolakes": package}, {}, tmp_path)


def resume_fixture(tmp_path: Path, *, mutable: bool = False):
    plan = fixture_plan(b"first", mutable=mutable)
    second = dict(plan["files"][0])
    second["object_key"] = "hydrolakes/releases/v1/second.txt"
    second["s3_uri_proposed"] = "s3://nthh/" + second["object_key"]
    second["source"] = {"kind": "package", "dataset_id": "hydrolakes", "path": "second.txt"}
    second["size_bytes"] = 6
    second["sha256"] = digest(b"second")
    plan["files"].append(second)
    plan["file_count"] = 2
    plan["total_bytes"] = 11
    plan_sha, entries = load(tmp_path, plan, include_readme=mutable)
    package = tmp_path / "package"
    package.mkdir()
    (package / "asset.txt").write_bytes(b"first")
    (package / "second.txt").write_bytes(b"second")
    repo = tmp_path / "repo"
    repo.mkdir()
    if mutable:
        readme = repo / "datasets/hydrolakes/source-coop/product-README.md"
        readme.parent.mkdir(parents=True)
        readme.write_bytes(b"README")
    rows = upload.resolve_sources(entries, {"hydrolakes": package}, {}, repo)
    prior = tmp_path / "prior"
    objects = prior / "objects"
    objects.mkdir(parents=True)
    summary = {"schema_version": 1, "mode": "execute", "status": "failed",
               "plan_sha256": plan_sha, "object_count": len(entries),
               "include_readme": mutable, "completed": 1, "failed": 1}
    (prior / "summary.json").write_text(json.dumps(summary))
    for index, (entry, status) in enumerate(((entries[0], "uploaded_verified"), (entries[1], "failed"))):
        record = {"schema_version": 1, "plan_sha256": plan_sha, "bucket": "nthh",
                  "object_key": entry["object_key"], "expected_sha256": entry["sha256"],
                  "expected_size_bytes": entry["size_bytes"], "mutable": False,
                  "remote_sha256": entry["sha256"] if index == 0 else None,
                  "status": status}
        name = f"{index:04d}-{digest(entry['object_key'].encode())[:16]}.json"
        (objects / name).write_text(json.dumps(record))
    return plan_sha, entries, rows, prior


def test_preflight_rejects_tampered_file_before_any_remote_call(tmp_path):
    rows = sources(tmp_path, b"correct")
    rows[0][1].write_bytes(b"changed")
    session = Session(FakeS3())
    with pytest.raises(upload.UploadError, match="differs from plan"):
        upload.execute(rows, "a" * 64, tmp_path / "receipt", execute_upload=True, include_readme=False, session=session)
    assert session.calls == 0


@pytest.mark.parametrize("field,value", [("endpoint", "https://evil.invalid"), ("bucket", "other"),
                                           ("object_key", "hydrolakes/releases/v1/../asset.txt"),
                                           ("source", {"kind": "mystery", "path": "asset.txt"})])
def test_rejects_bad_routes_and_source_kind(tmp_path, field, value):
    plan = fixture_plan()
    plan["files"][0][field] = value
    with pytest.raises(upload.UploadError):
        load(tmp_path, plan)


def test_symlink_and_outside_roots_are_rejected(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "asset.txt").write_bytes(b"x")
    package = data / "package"
    package.mkdir()
    (package / "asset.txt").symlink_to(outside / "asset.txt")
    _, entries = load(tmp_path, fixture_plan(b"x"))
    with pytest.raises(upload.UploadError, match="symlink"):
        upload.resolve_sources(entries, {"hydrolakes": package}, {}, tmp_path)
    with pytest.raises(upload.UploadError, match="outside"):
        upload._check_root(outside, data, "package")


def test_existing_matching_bytes_skip_and_differing_bytes_refused(tmp_path):
    rows = sources(tmp_path, b"right")
    key = rows[0][0]["object_key"]
    matching = Session(FakeS3({key: b"right"}))
    result = upload.execute(rows, "a" * 64, tmp_path / "match", execute_upload=True,
                            include_readme=False, session=matching)
    assert result["status"] == "complete"
    assert not matching.fake.puts
    record = json.loads(next((tmp_path / "match/objects").iterdir()).read_text())
    assert record["status"] == "verified_existing" and record["remote_sha256"] == digest(b"right")
    different = Session(FakeS3({key: b"wrong"}))
    result = upload.execute(rows, "a" * 64, tmp_path / "different", execute_upload=True,
                            include_readme=False, session=different)
    assert result["status"] == "failed" and not different.fake.puts


def test_failed_head_is_not_treated_as_absent_and_error_redacted(tmp_path):
    rows = sources(tmp_path, b"right")
    fake = FakeS3()
    fake.head_error = Forbidden("SECRET-ACCESS-KEY")
    result = upload.execute(rows, "a" * 64, tmp_path / "receipt", execute_upload=True,
                            include_readme=False, session=Session(fake))
    assert result["status"] == "failed" and not fake.puts
    assert "SECRET-ACCESS-KEY" not in (tmp_path / "receipt/summary.json").read_text()
    assert "SECRET-ACCESS-KEY" not in next((tmp_path / "receipt/objects").iterdir()).read_text()


def test_multipart_boundary_and_conditional_write(tmp_path, monkeypatch):
    monkeypatch.setattr(upload, "PART_BYTES", 5)
    rows = sources(tmp_path, b"123456")
    fake = FakeS3()
    result = upload.execute(rows, "a" * 64, tmp_path / "receipt", execute_upload=True,
                            include_readme=False, session=Session(fake))
    assert result["status"] == "complete"
    assert list(map(len, fake.multipart[0]["parts"])) == [5, 1]
    assert fake.objects[rows[0][0]["object_key"]] == b"123456"


def test_readme_requires_flag_and_records_previous_bytes(tmp_path):
    plan = fixture_plan(mutable=True)
    _, default_entries = load(tmp_path, plan)
    assert len(default_entries) == 1
    _, entries = load(tmp_path, plan, include_readme=True)
    repo = tmp_path / "repo"
    readme = repo / "datasets/hydrolakes/source-coop/product-README.md"
    readme.parent.mkdir(parents=True)
    readme.write_bytes(b"README")
    package = tmp_path / "package"
    package.mkdir()
    (package / "asset.txt").write_bytes(b"package")
    rows = upload.resolve_sources(entries, {"hydrolakes": package}, {}, repo)
    key = "hydrolakes/README.md"
    fake = FakeS3({key: b"old"})
    result = upload.execute(rows, "b" * 64, tmp_path / "receipt", execute_upload=True,
                            include_readme=True, session=Session(fake))
    assert result["status"] == "complete"
    assert fake.objects[key] == b"README"
    records = [json.loads(path.read_text()) for path in (tmp_path / "receipt/objects").iterdir()]
    record = next(row for row in records if row["object_key"] == key)
    assert record["previous_remote_sha256"] == digest(b"old")
    assert record["previous_remote_size_bytes"] == 3


def test_readme_only_selects_no_immutable_files_and_keeps_conditional_replace(tmp_path):
    plan = fixture_plan(mutable=True)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan))
    plan_sha, selected = upload.load_plan(plan_path, "hydrolakes", False, readme_only=True)
    assert [row["object_key"] for row in selected] == ["hydrolakes/README.md"]
    repo = tmp_path / "repo"
    readme = repo / "datasets/hydrolakes/source-coop/product-README.md"
    readme.parent.mkdir(parents=True)
    readme.write_bytes(b"README")
    rows = upload.resolve_sources(selected, {}, {}, repo)
    fake = FakeS3({"hydrolakes/README.md": b"old"})
    result = upload.execute(rows, plan_sha, tmp_path / "receipt", execute_upload=True,
                            include_readme=True, session=Session(fake))
    assert result["status"] == "complete" and result["object_count"] == 1
    assert [key for key, _ in fake.puts] == ["hydrolakes/README.md"]
    assert fake.objects["hydrolakes/README.md"] == b"README"
    assert upload.main(["--plan", str(plan_path), "--dataset", "hydrolakes", "--repo-root", str(repo),
                        "--output", str(tmp_path / "dry-run"), "--readme-only"]) == 0
    assert upload.main(["--plan", str(plan_path), "--dataset", "hydrolakes", "--repo-root", str(repo),
                        "--output", str(tmp_path / "refused"), "--readme-only", "--include-readme"]) == 1
    assert not (tmp_path / "refused").exists()


def test_non_readme_mutable_destination_rejected(tmp_path):
    plan = fixture_plan(mutable=True)
    plan["mutable_metadata"][0]["object_key"] = "hydrolakes/other.md"
    with pytest.raises(upload.UploadError):
        load(tmp_path, plan, include_readme=True)
    plan = fixture_plan(mutable=True)
    plan["mutable_metadata"][0]["binding_status"] = "unbound"
    with pytest.raises(upload.UploadError, match="invalid mutable README"):
        load(tmp_path, plan, include_readme=True)


def test_repository_supplement_cannot_cross_dataset(tmp_path):
    plan = fixture_plan()
    plan["files"].append({"bucket": "nthh", "endpoint": upload.ENDPOINT,
                          "object_key": "hydrolakes/metadata/v1/file.json",
                          "s3_uri_proposed": "s3://nthh/hydrolakes/metadata/v1/file.json",
                          "source": {"kind": "repository", "path": "datasets/lakeatlas/file.json"},
                          "size_bytes": 2, "sha256": digest(b"{}"), "content_type": "application/json"})
    plan["file_count"] = 2
    plan["total_bytes"] += 2
    with pytest.raises(upload.UploadError, match="crosses dataset"):
        load(tmp_path, plan)


def test_planned_mime_mismatch_and_remote_mime_mismatch(tmp_path):
    plan = fixture_plan()
    plan["files"][0]["content_type"] = "application/json"
    with pytest.raises(upload.UploadError, match="content type"):
        load(tmp_path, plan)
    # Use a fresh directory because sources() creates its own plan and package.
    second = tmp_path / "second"
    second.mkdir()
    rows = sources(second, b"right")
    key = rows[0][0]["object_key"]
    fake = FakeS3({key: b"right"})
    fake.types[key] = "application/json"
    result = upload.execute(rows, "a" * 64, tmp_path / "receipt", execute_upload=True,
                            include_readme=False, session=Session(fake))
    assert result["status"] == "failed" and not fake.puts


def test_execute_requires_exact_plan_hash_before_receipt_or_network(tmp_path):
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(fixture_plan()), encoding="utf-8")
    helper = tmp_path / "helper"
    helper.write_text("fake", encoding="utf-8")
    common = ["--plan", str(plan_path), "--dataset", "hydrolakes", "--data-root", str(tmp_path),
              "--repo-root", str(tmp_path), "--credential-helper", str(helper),
              "--output", str(tmp_path / "receipt"), "--execute"]
    assert upload.main(common) == 1
    assert upload.main(common + ["--expected-plan-sha256", "0" * 64]) == 1
    assert not (tmp_path / "receipt").exists()


def test_multipart_journal_and_scoped_recovery_after_interruption(tmp_path, monkeypatch):
    monkeypatch.setattr(upload, "PART_BYTES", 5)
    rows = sources(tmp_path, b"123456")
    receipt = tmp_path / "interrupted"

    class InterruptingS3(FakeS3):
        def upload_part(self, *, Bucket, Key, UploadId, PartNumber, Body):
            records = list((receipt / "objects").glob("*.json"))
            assert len(records) == 1
            record = json.loads(records[0].read_text())
            assert record["multipart"]["upload_id"] == "this-invocation"
            assert record["multipart"]["state"] == "open"
            if PartNumber == 2:
                assert record["multipart"]["parts"] == [{"PartNumber": 1, "ETag": "1"}]
                raise KeyboardInterrupt()
            return super().upload_part(Bucket=Bucket, Key=Key, UploadId=UploadId,
                                       PartNumber=PartNumber, Body=Body)

    fake = InterruptingS3()
    with pytest.raises(KeyboardInterrupt):
        upload.execute(rows, "c" * 64, receipt, execute_upload=True,
                       include_readme=False, session=Session(fake))
    assert fake.abort_count == 0
    _, entries = load(tmp_path, fixture_plan(b"123456"))
    recovery = upload.recover_multipart(receipt, entries, "c" * 64, tmp_path / "recovered", Session(fake))
    assert recovery["status"] == "complete" and recovery["completed"] == 1
    assert fake.abort_count == 1
    assert fake.objects == {}


def test_recovery_refuses_tampered_object_scope(tmp_path):
    receipt = tmp_path / "previous"
    records = receipt / "objects"
    records.mkdir(parents=True)
    (receipt / "summary.json").write_text(json.dumps({"mode": "execute", "plan_sha256": "d" * 64}))
    (records / "0000.json").write_text(json.dumps({"multipart": {"state": "open", "upload_id": "id"},
                                                   "object_key": "other/key", "bucket": "nthh",
                                                   "plan_sha256": "d" * 64, "expected_sha256": digest(b"package")}))
    _, entries = load(tmp_path, fixture_plan())
    fake = FakeS3()
    with pytest.raises(upload.UploadError, match="outside selected plan"):
        upload.recover_multipart(receipt, entries, "d" * 64, tmp_path / "recovered", Session(fake))
    assert fake.abort_count == 0 and not (tmp_path / "recovered").exists()


def test_recovery_records_safe_exception_type_without_secret_message(tmp_path):
    receipt = tmp_path / "previous"
    records = receipt / "objects"
    records.mkdir(parents=True)
    (receipt / "summary.json").write_text(json.dumps({"mode": "execute", "plan_sha256": "d" * 64}))
    _, entries = load(tmp_path, fixture_plan())
    entry = entries[0]
    (records / "0000.json").write_text(json.dumps({"multipart": {"state": "abort_failed", "upload_id": "owned-id"},
                                                   "object_key": entry["object_key"], "bucket": "nthh",
                                                   "plan_sha256": "d" * 64, "expected_sha256": entry["sha256"]}))

    class HelperUnavailable(Exception):
        pass

    class FailingSession:
        def client(self):
            raise HelperUnavailable("SECRET-ACCESS-KEY")

    result = upload.recover_multipart(receipt, entries, "d" * 64, tmp_path / "recovered", FailingSession())
    assert result["status"] == "failed"
    raw = next((tmp_path / "recovered/objects").iterdir()).read_text()
    assert json.loads(raw)["error_type"] == "HelperUnavailable"
    assert json.loads(raw)["abort_attempted"] is False
    assert json.loads(raw)["error_operation"] == "S3Client"
    assert "SECRET-ACCESS-KEY" not in raw


def test_multipart_upload_failure_records_abort_outcome(tmp_path, monkeypatch):
    monkeypatch.setattr(upload, "PART_BYTES", 5)
    rows = sources(tmp_path, b"123456")

    class FailingS3(FakeS3):
        def upload_part(self, **kwargs):
            raise RuntimeError("SECRET-ACCESS-KEY")

        def abort_multipart_upload(self, **kwargs):
            self.abort_count += 1
            raise RuntimeError("SECRET-ACCESS-KEY")

    fake = FailingS3()
    result = upload.execute(rows, "e" * 64, tmp_path / "receipt", execute_upload=True,
                            include_readme=False, session=Session(fake))
    assert result["status"] == "failed" and fake.abort_count == 1
    record_text = next((tmp_path / "receipt/objects").iterdir()).read_text()
    record = json.loads(record_text)
    assert record["multipart"]["state"] == "abort_failed"
    assert record["multipart"]["upload_id"] == "this-invocation"
    assert "SECRET-ACCESS-KEY" not in record_text


def test_credential_ttl_accepts_90_seconds_and_rejects_under_60(monkeypatch, tmp_path):
    sentinel = object()
    fake_boto = SimpleNamespace(client=lambda *args, **kwargs: sentinel)
    fake_config = SimpleNamespace(Config=lambda **kwargs: object())
    monkeypatch.setitem(sys.modules, "boto3", fake_boto)
    monkeypatch.setitem(sys.modules, "botocore", SimpleNamespace(config=fake_config))
    monkeypatch.setitem(sys.modules, "botocore.config", fake_config)

    def credential(seconds):
        expires = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()
        return json.dumps({"Version": 1, "AccessKeyId": "a", "SecretAccessKey": "s",
                           "SessionToken": "t", "Expiration": expires}).encode()

    monkeypatch.setattr(upload.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=credential(90)))
    assert upload.S3Session(tmp_path / "helper").client() is sentinel
    monkeypatch.setattr(upload.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=credential(59)))
    with pytest.raises(upload.CredentialTooNearExpiry, match="credential expires too soon") as error:
        upload.S3Session(tmp_path / "helper").client()
    assert error.value.operation == "CredentialHelper"
    assert 59 <= error.value.retry_after_seconds <= 61


def test_plan_total_cap_is_enforced(tmp_path):
    plan = fixture_plan()
    plan["files"][0]["size_bytes"] = upload.MAX_BYTES + 1
    plan["total_bytes"] = upload.MAX_BYTES + 1
    with pytest.raises(upload.UploadError, match="size or SHA"):
        load(tmp_path, plan)


def test_credential_helper_failure_never_exposes_stderr(monkeypatch, tmp_path):
    class FakeBoto:
        pass

    class FakeConfig:
        class Config:
            pass

    monkeypatch.setitem(sys.modules, "boto3", FakeBoto())
    monkeypatch.setitem(sys.modules, "botocore", FakeConfig())
    monkeypatch.setitem(sys.modules, "botocore.config", FakeConfig())

    def fail(command, **kwargs):
        assert command == [str(tmp_path / "helper"), "creds", "--format", "credential-process"]
        assert kwargs["capture_output"] is True
        raise subprocess.CalledProcessError(1, command, stderr=b"SECRET-ACCESS-KEY")

    monkeypatch.setattr(upload.subprocess, "run", fail)
    with pytest.raises(upload.UploadError) as error:
        upload.S3Session(tmp_path / "helper").client()
    assert "SECRET-ACCESS-KEY" not in str(error.value)


def test_credential_helper_timeout_has_safe_stage(monkeypatch, tmp_path):
    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 60, output=b"SECRET-ACCESS-KEY")

    monkeypatch.setattr(upload.subprocess, "run", timeout)
    with pytest.raises(upload.UploadError, match="credential helper timed out") as error:
        upload.S3Session(tmp_path / "helper").client()
    assert error.value.operation == "CredentialHelper"
    assert "SECRET-ACCESS-KEY" not in str(error.value)


def test_resume_reuses_prior_full_readback_without_new_bulk_read_or_local_hash(tmp_path, monkeypatch):
    plan_sha, entries, rows, prior = resume_fixture(tmp_path, mutable=True)
    proofs = upload.load_resume(prior, entries, plan_sha, include_readme=True)
    assert set(proofs) == {entries[0]["object_key"]}
    original_hash = upload.hash_file
    hashed = []

    def tracked_hash(path):
        hashed.append(path.name)
        return original_hash(path)

    monkeypatch.setattr(upload, "hash_file", tracked_hash)
    fake = FakeS3({entries[0]["object_key"]: b"first", "hydrolakes/README.md": b"old"})
    result = upload.execute(rows, plan_sha, tmp_path / "resumed", execute_upload=True,
                            include_readme=True, session=Session(fake), resume_proofs=proofs)
    assert result["status"] == "complete"
    assert (result["reused_prior_verified"], result["fresh_verified"], result["completed"]) == (1, 2, 3)
    assert "asset.txt" not in hashed and "second.txt" in hashed and "product-README.md" in hashed
    assert entries[0]["object_key"] not in fake.get_calls
    assert [key for key, _ in fake.puts] == [entries[1]["object_key"], "hydrolakes/README.md"]
    record = json.loads(next((tmp_path / "resumed/objects").glob("0000-*.json")).read_text())
    assert record["status"] == "verified_prior_attempt" and record["bytes_transferred"] == 0
    assert record["remote_sha256_scope"] == "prior_attempt_full_remote_readback"
    assert record["prior_proof"]["summary_sha256"] == digest((prior / "summary.json").read_bytes())
    assert record["prior_proof"]["record_sha256"] == digest(next((prior / "objects").glob("0000-*.json")).read_bytes())
    assert "multipart" not in record["prior_proof"] and "upload_id" not in json.dumps(record["prior_proof"])
    assert record["current_head"]["size_bytes"] == 5 and record["current_head"]["http_status"] == 200
    assert datetime.fromisoformat(record["current_head"]["checked_at"]).tzinfo is not None
    assert json.loads((prior / "summary.json").read_text())["status"] == "failed"


@pytest.mark.parametrize("response_metadata", [None, {"HTTPStatusCode": 204}])
def test_resume_refuses_head_without_actual_http_200(tmp_path, response_metadata):
    plan_sha, entries, rows, prior = resume_fixture(tmp_path)
    proofs = upload.load_resume(prior, entries, plan_sha, include_readme=False)

    class MissingStatusS3(FakeS3):
        def head_object(self, *, Bucket, Key):
            result = super().head_object(Bucket=Bucket, Key=Key)
            if response_metadata is None:
                result.pop("ResponseMetadata")
            else:
                result["ResponseMetadata"] = response_metadata
            return result

    fake = MissingStatusS3({entries[0]["object_key"]: b"first"})
    result = upload.execute(rows, plan_sha, tmp_path / "resumed", execute_upload=True,
                            include_readme=False, session=Session(fake), resume_proofs=proofs)
    assert result["status"] == "failed" and result["completed"] == 0 and not fake.puts
    record = json.loads(next((tmp_path / "resumed/objects").iterdir()).read_text())
    assert record["error"] == "prior verified object HEAD lacks HTTP 200 evidence"
    assert "current_head" not in record


@pytest.mark.parametrize("change,match", [
    ("running", "stopped failed"), ("wrong_plan", "stopped failed"),
    ("unknown_key", "unknown or duplicate"), ("wrong_expected", "differs from selected plan"),
    ("wrong_remote", "remote SHA-256 differs"), ("bad_counts", "counts do not match"),
])
def test_resume_refuses_unbound_or_corrupt_prior_receipt(tmp_path, change, match):
    plan_sha, entries, _, prior = resume_fixture(tmp_path)
    summary_path = prior / "summary.json"
    first_path = next((prior / "objects").glob("0000-*.json"))
    summary = json.loads(summary_path.read_text())
    first = json.loads(first_path.read_text())
    if change == "running":
        summary["status"] = "running"
    elif change == "wrong_plan":
        summary["plan_sha256"] = "0" * 64
    elif change == "unknown_key":
        first["object_key"] = "other/key"
    elif change == "wrong_expected":
        first["expected_sha256"] = "0" * 64
    elif change == "wrong_remote":
        first["remote_sha256"] = "0" * 64
    elif change == "bad_counts":
        summary["completed"] = 2
    summary_path.write_text(json.dumps(summary))
    first_path.write_text(json.dumps(first))
    with pytest.raises(upload.UploadError, match=match):
        upload.load_resume(prior, entries, plan_sha, include_readme=False)


def test_resume_requires_exact_completed_recovery_for_prior_open_multipart(tmp_path):
    plan_sha, entries, _, prior = resume_fixture(tmp_path)
    failed_path = next((prior / "objects").glob("0001-*.json"))
    failed = json.loads(failed_path.read_text())
    failed["multipart"] = {"state": "abort_failed", "upload_id": "prior-id", "parts": [{"ETag": "1", "PartNumber": 1}]}
    failed_path.write_text(json.dumps(failed))
    with pytest.raises(upload.UploadError, match="requires a completed recovery"):
        upload.load_resume(prior, entries, plan_sha, include_readme=False)
    recovery = tmp_path / "recovery"
    (recovery / "objects").mkdir(parents=True)
    recovery_summary = {"schema_version": 1, "mode": "multipart_recovery", "status": "complete",
                        "plan_sha256": plan_sha, "object_count": 1, "completed": 1, "failed": 0}
    (recovery / "summary.json").write_text(json.dumps(recovery_summary))
    recovery_record = {"schema_version": 1, "plan_sha256": plan_sha, "bucket": "nthh",
                       "object_key": entries[1]["object_key"], "upload_id": "other-id",
                       "action": "abort_multipart", "status": "aborted"}
    (recovery / "objects/0000.json").write_text(json.dumps(recovery_record))
    with pytest.raises(upload.UploadError, match="does not match prior upload ID"):
        upload.load_resume(prior, entries, plan_sha, include_readme=False, recovery=recovery)
    recovery_record["upload_id"] = "prior-id"
    (recovery / "objects/0000.json").write_text(json.dumps(recovery_record))
    assert set(upload.load_resume(prior, entries, plan_sha, include_readme=False, recovery=recovery)) == {entries[0]["object_key"]}


def multipart_resume_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(upload, "PART_BYTES", 2)
    plan_sha, entries, rows, prior = resume_fixture(tmp_path)
    failed_path = next((prior / "objects").glob("0001-*.json"))
    failed = json.loads(failed_path.read_text())
    failed["multipart"] = {"state": "abort_failed", "upload_id": "owned-prior-upload",
                           "parts": [{"PartNumber": 1, "ETag": "stale-etag"}]}
    failed_path.write_text(json.dumps(failed))
    state = {}
    proofs = upload.load_resume(prior, entries, plan_sha, include_readme=False, multipart_state=state)
    return plan_sha, entries, rows, prior, proofs, state


def test_resume_multipart_replays_every_part_on_existing_id_and_verifies_bytes(tmp_path, monkeypatch):
    plan_sha, entries, rows, prior, proofs, state = multipart_resume_fixture(tmp_path, monkeypatch)

    class ExistingUploadS3(FakeS3):
        def __init__(self):
            super().__init__({entries[0]["object_key"]: b"first"})
            self.new_parts = []
            self.completed = False

        def create_multipart_upload(self, **kwargs):
            pytest.fail("resume must not create a new upload ID")

        def upload_part(self, *, Bucket, Key, UploadId, PartNumber, Body):
            assert (Bucket, Key, UploadId) == ("nthh", entries[1]["object_key"], "owned-prior-upload")
            assert PartNumber == len(self.new_parts) + 1
            self.new_parts.append(Body)
            return {"ETag": f"new-{PartNumber}"}

        def complete_multipart_upload(self, *, Bucket, Key, UploadId, MultipartUpload, IfNoneMatch):
            assert UploadId == "owned-prior-upload" and IfNoneMatch == "*"
            assert MultipartUpload["Parts"] == [
                {"PartNumber": n, "ETag": f"new-{n}"} for n in (1, 2, 3)]
            self.objects[Key] = b"".join(self.new_parts)
            self.types[Key] = "text/plain"
            self.completed = True

    fake = ExistingUploadS3()
    result = upload.execute(rows, plan_sha, tmp_path / "resumed", execute_upload=True,
                            include_readme=False, session=Session(fake), resume_proofs=proofs,
                            resume_multipart=state)
    assert result["status"] == "complete" and result["resume_mode"] == "existing_multipart"
    assert (result["reused_prior_verified"], result["resumed_multipart"], result["fresh_verified"]) == (1, 1, 1)
    assert fake.new_parts == [b"se", b"co", b"nd"] and fake.completed
    record = json.loads(next((tmp_path / "resumed/objects").glob("0001-*.json")).read_text())
    assert record["status"] == "uploaded_verified" and record["remote_sha256"] == digest(b"second")
    assert record["remote_sha256_scope"] == "current_attempt_full_remote_readback"
    assert record["multipart"]["state"] == "completed" and record["bytes_transferred"] == 6
    assert record["multipart"]["parts"] == [{"PartNumber": n, "ETag": f"new-{n}"} for n in (1, 2, 3)]
    assert record["multipart_resume"]["summary_sha256"] == digest((prior / "summary.json").read_bytes())
    assert record["multipart_resume"]["record_sha256"] == digest(next((prior / "objects").glob("0001-*.json")).read_bytes())
    assert entries[1]["object_key"] in fake.get_calls


def test_resume_multipart_refuses_existing_target_before_part_write(tmp_path, monkeypatch):
    plan_sha, entries, rows, _, proofs, state = multipart_resume_fixture(tmp_path, monkeypatch)

    class NoWritesS3(FakeS3):
        def create_multipart_upload(self, **kwargs): pytest.fail("unexpected create")
        def upload_part(self, **kwargs): pytest.fail("unexpected part write")

    fake = NoWritesS3({entries[0]["object_key"]: b"first", entries[1]["object_key"]: b"second"})
    result = upload.execute(rows, plan_sha, tmp_path / "resumed", execute_upload=True,
                            include_readme=False, session=Session(fake), resume_proofs=proofs,
                            resume_multipart=state)
    assert result["status"] == "failed" and result["resumed_multipart"] == 0
    record = json.loads(next((tmp_path / "resumed/objects").glob("0001-*.json")).read_text())
    assert record["error"] == "multipart resume target already exists"


def test_resume_multipart_nosuchupload_fails_without_new_id(tmp_path, monkeypatch):
    plan_sha, entries, rows, _, proofs, state = multipart_resume_fixture(tmp_path, monkeypatch)

    class NoSuchUpload(Exception):
        response = {"ResponseMetadata": {"HTTPStatusCode": 404},
                    "Error": {"Code": "NoSuchUpload", "Message": "SECRET"}}

    class MissingUploadS3(FakeS3):
        def create_multipart_upload(self, **kwargs): pytest.fail("unexpected create")
        def upload_part(self, **kwargs): raise NoSuchUpload()

    fake = MissingUploadS3({entries[0]["object_key"]: b"first"})
    result = upload.execute(rows, plan_sha, tmp_path / "resumed", execute_upload=True,
                            include_readme=False, session=Session(fake), resume_proofs=proofs,
                            resume_multipart=state)
    assert result["status"] == "failed" and result["resumed_multipart"] == 0
    raw = next((tmp_path / "resumed/objects").glob("0001-*.json")).read_text()
    record = json.loads(raw)
    assert record["error_code"] == "NoSuchUpload" and record["multipart"]["state"] == "open"
    assert "SECRET" not in raw


def test_resume_multipart_complete_precondition_race_keeps_original_id(tmp_path, monkeypatch):
    plan_sha, entries, rows, _, proofs, state = multipart_resume_fixture(tmp_path, monkeypatch)

    class PreconditionFailed(Exception):
        response = {"ResponseMetadata": {"HTTPStatusCode": 412},
                    "Error": {"Code": "PreconditionFailed", "Message": "SECRET"}}

    class RacingS3(FakeS3):
        def __init__(self):
            super().__init__({entries[0]["object_key"]: b"first"})
            self.part_count = 0

        def create_multipart_upload(self, **kwargs): pytest.fail("unexpected create")

        def upload_part(self, *, Bucket, Key, UploadId, PartNumber, Body):
            assert UploadId == "owned-prior-upload" and PartNumber == self.part_count + 1
            self.part_count += 1
            return {"ETag": f"new-{PartNumber}"}

        def complete_multipart_upload(self, *, Bucket, Key, UploadId, MultipartUpload, IfNoneMatch):
            assert UploadId == "owned-prior-upload" and IfNoneMatch == "*"
            assert len(MultipartUpload["Parts"]) == 3
            raise PreconditionFailed()

    fake = RacingS3()
    result = upload.execute(rows, plan_sha, tmp_path / "resumed", execute_upload=True,
                            include_readme=False, session=Session(fake), resume_proofs=proofs,
                            resume_multipart=state)
    assert result["status"] == "failed" and fake.part_count == 3
    raw = next((tmp_path / "resumed/objects").glob("0001-*.json")).read_text()
    record = json.loads(raw)
    assert record["error_code"] == "PreconditionFailed" and record["error_http_status"] == 412
    assert record["multipart"]["upload_id"] == "owned-prior-upload"
    assert record["multipart"]["state"] == "open" and len(record["multipart"]["parts"]) == 3
    assert "SECRET" not in raw


def test_resume_multipart_complete_requires_full_remote_byte_match(tmp_path, monkeypatch):
    plan_sha, entries, rows, _, proofs, state = multipart_resume_fixture(tmp_path, monkeypatch)

    class CorruptCompletedS3(FakeS3):
        def __init__(self):
            super().__init__({entries[0]["object_key"]: b"first"})

        def create_multipart_upload(self, **kwargs): pytest.fail("unexpected create")

        def upload_part(self, *, UploadId, PartNumber, **kwargs):
            assert UploadId == "owned-prior-upload"
            return {"ETag": f"new-{PartNumber}"}

        def complete_multipart_upload(self, *, Key, UploadId, IfNoneMatch, **kwargs):
            assert UploadId == "owned-prior-upload" and IfNoneMatch == "*"
            self.objects[Key] = b"badbad"
            self.types[Key] = "text/plain"

    fake = CorruptCompletedS3()
    result = upload.execute(rows, plan_sha, tmp_path / "resumed", execute_upload=True,
                            include_readme=False, session=Session(fake), resume_proofs=proofs,
                            resume_multipart=state)
    assert result["status"] == "failed" and result["resumed_multipart"] == 0
    record = json.loads(next((tmp_path / "resumed/objects").glob("0001-*.json")).read_text())
    assert record["multipart"]["state"] == "completed"
    assert record["remote_sha256"] == digest(b"badbad")
    assert record["error"] == "uploaded object failed byte verification"


def auth_retry_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(upload, "PART_BYTES", 2)
    path = tmp_path / "asset.parquet"
    path.write_bytes(b"second")
    entry = {"object_key": "grwl-raw/releases/v1/asset.parquet"}
    binding = {"upload_id": "owned-original-id", "summary_sha256": "a" * 64,
               "record_sha256": "b" * 64, "record_name": "failed.json"}
    record = {"bytes_transferred": 0}
    snapshots = []
    def persist():
        snapshots.append(json.loads(json.dumps(record)))
    return entry, path, binding, record, snapshots, persist


def test_resumed_part_expired_token_retries_same_bytes_on_new_client(tmp_path, monkeypatch):
    from botocore.exceptions import ClientError
    entry, path, binding, record, snapshots, persist = auth_retry_fixture(tmp_path, monkeypatch)

    class Backend:
        def __init__(self):
            self.calls = []
            self.saved = {}
            self.completed = False

        def upload_part(self, client_number, *, Bucket, Key, UploadId, PartNumber, Body):
            assert (Bucket, Key, UploadId) == ("nthh", entry["object_key"], "owned-original-id")
            self.calls.append((client_number, PartNumber, Body))
            if PartNumber == 2 and sum(n == 2 for _, n, _ in self.calls) == 1:
                raise ClientError({"Error": {"Code": "ExpiredToken", "Message": "SECRET-TOKEN"},
                                   "ResponseMetadata": {"HTTPStatusCode": 403}}, "UploadPart")
            self.saved[PartNumber] = Body
            return {"ETag": f"fresh-{PartNumber}"}

        def complete_multipart_upload(self, *, Bucket, Key, UploadId, MultipartUpload, IfNoneMatch):
            assert UploadId == "owned-original-id" and IfNoneMatch == "*"
            assert MultipartUpload["Parts"] == [
                {"PartNumber": n, "ETag": f"fresh-{n}"} for n in (1, 2, 3)]
            assert b"".join(self.saved[n] for n in (1, 2, 3)) == b"second"
            self.completed = True

        def create_multipart_upload(self, **kwargs): pytest.fail("new upload ID forbidden")

    backend = Backend()

    class Session:
        def __init__(self): self.clients = 0
        def client(self):
            self.clients += 1
            number = self.clients
            return SimpleNamespace(
                upload_part=lambda **kwargs: backend.upload_part(number, **kwargs),
                complete_multipart_upload=backend.complete_multipart_upload,
                create_multipart_upload=backend.create_multipart_upload)

    session = Session()
    upload._resume_existing_multipart(session, entry, path, binding, record, persist)
    assert backend.calls == [(1, 1, b"se"), (2, 2, b"co"), (3, 2, b"co"), (4, 3, b"nd")]
    assert backend.completed and record["bytes_transferred"] == 6
    assert record["multipart"]["state"] == "completed"
    assert [part["PartNumber"] for part in record["multipart"]["parts"]] == [1, 2, 3]
    assert len(record["auth_retries"]) == 1
    assert set(record["auth_retries"][0]) == {"operation", "timestamp_utc", "attempt", "reason"}
    assert record["auth_retries"][0]["reason"] == "ExpiredToken"
    assert any(len(s["multipart"]["parts"]) == 1 and len(s.get("auth_retries", [])) == 1 for s in snapshots)
    assert "SECRET-TOKEN" not in json.dumps(record)


@pytest.mark.parametrize("failure", ["NoSuchUpload", "AccessDenied", "wrong_operation", "transport"])
def test_resumed_part_other_errors_never_retry(tmp_path, monkeypatch, failure):
    from botocore.exceptions import ClientError
    entry, path, binding, record, _, persist = auth_retry_fixture(tmp_path, monkeypatch)

    class Session:
        calls = 0
        def client(self):
            self.calls += 1
            def fail(**kwargs):
                if failure == "transport": raise RuntimeError("SECRET")
                code = "ExpiredToken" if failure == "wrong_operation" else failure
                operation = "GetObject" if failure == "wrong_operation" else "UploadPart"
                raise ClientError({"Error": {"Code": code, "Message": "SECRET"},
                                   "ResponseMetadata": {"HTTPStatusCode": 403}}, operation)
            return SimpleNamespace(upload_part=fail)

    session = Session()
    with pytest.raises(upload.UploadError):
        upload._resume_existing_multipart(session, entry, path, binding, record, persist)
    assert session.calls == 1 and record["multipart"]["parts"] == []
    assert "auth_retries" not in record and record["multipart"]["state"] == "open"


def test_resumed_part_expired_token_stops_after_two_retries(tmp_path, monkeypatch):
    from botocore.exceptions import ClientError
    entry, path, binding, record, _, persist = auth_retry_fixture(tmp_path, monkeypatch)
    calls = []

    class Session:
        def client(self):
            number = len(calls) + 1
            def fail(*, PartNumber, Body, UploadId, **kwargs):
                calls.append((number, PartNumber, Body, UploadId))
                raise ClientError({"Error": {"Code": "ExpiredToken", "Message": "SECRET"},
                                   "ResponseMetadata": {"HTTPStatusCode": 403}}, "UploadPart")
            return SimpleNamespace(upload_part=fail)

    with pytest.raises(upload.UploadError) as error:
        upload._resume_existing_multipart(Session(), entry, path, binding, record, persist)
    assert error.value.error_code == "ExpiredToken"
    assert calls == [(n, 1, b"se", "owned-original-id") for n in (1, 2, 3)]
    assert [r["attempt"] for r in record["auth_retries"]] == [1, 2]
    assert record["multipart"]["parts"] == [] and record["bytes_transferred"] == 0


def test_resumed_part_near_expiry_waits_in_bounded_steps_without_real_sleep(tmp_path, monkeypatch):
    entry, path, binding, record, _, persist = auth_retry_fixture(tmp_path, monkeypatch)
    sleeps = []
    monkeypatch.setattr(upload.time, "sleep", lambda seconds: sleeps.append(seconds))
    uploaded = []

    class Session:
        calls = 0
        def client(self):
            self.calls += 1
            if self.calls == 1:
                raise upload.CredentialTooNearExpiry(12)
            return SimpleNamespace(
                upload_part=lambda **kwargs: uploaded.append((kwargs["PartNumber"], kwargs["Body"])) or
                                              {"ETag": f"fresh-{kwargs['PartNumber']}"},
                complete_multipart_upload=lambda **kwargs: None)

    session = Session()
    upload._resume_existing_multipart(session, entry, path, binding, record, persist)
    assert sleeps == [5, 5, 2]
    assert uploaded == [(1, b"se"), (2, b"co"), (3, b"nd")]
    assert session.calls == 5 and record["multipart"]["state"] == "completed"
    assert record["auth_retries"] == [{"operation": "UploadPart",
                                       "timestamp_utc": record["auth_retries"][0]["timestamp_utc"],
                                       "attempt": 1, "reason": "CredentialTooNearExpiry"}]


def test_resumed_expired_token_waits_for_cached_helper_expiry(tmp_path, monkeypatch):
    from botocore.exceptions import ClientError
    entry, path, binding, record, _, persist = auth_retry_fixture(tmp_path, monkeypatch)
    sleeps = []
    monkeypatch.setattr(upload.time, "sleep", lambda seconds: sleeps.append(seconds))
    attempts = []

    class Session:
        last_expiration = datetime.now(timezone.utc) + timedelta(seconds=12)
        def client(self):
            def part(**kwargs):
                attempts.append((kwargs["PartNumber"], kwargs["Body"], kwargs["UploadId"]))
                if len(attempts) == 1:
                    raise ClientError({"Error": {"Code": "ExpiredToken", "Message": "SECRET"},
                                       "ResponseMetadata": {"HTTPStatusCode": 403}}, "UploadPart")
                return {"ETag": f"fresh-{kwargs['PartNumber']}"}
            return SimpleNamespace(upload_part=part, complete_multipart_upload=lambda **kwargs: None)

    upload._resume_existing_multipart(Session(), entry, path, binding, record, persist)
    assert attempts[:2] == [(1, b"se", "owned-original-id")] * 2
    assert 12 <= sum(sleeps) <= 14 and max(sleeps) <= 5
    assert record["auth_retries"][0]["reason"] == "ExpiredToken"


def test_resumed_part_near_expiry_total_wait_budget_fails_closed(tmp_path, monkeypatch):
    entry, path, binding, record, _, persist = auth_retry_fixture(tmp_path, monkeypatch)
    sleeps = []
    monkeypatch.setattr(upload.time, "sleep", lambda seconds: sleeps.append(seconds))

    class Session:
        calls = 0
        def client(self):
            self.calls += 1
            raise upload.CredentialTooNearExpiry(50)

    session = Session()
    with pytest.raises(upload.CredentialTooNearExpiry):
        upload._resume_existing_multipart(session, entry, path, binding, record, persist)
    assert session.calls == 2 and sum(sleeps) == 50 and max(sleeps) <= 5
    assert len(record["auth_retries"]) == 1 and record["multipart"]["parts"] == []


@pytest.mark.parametrize("change", ["wrong_plan", "wrong_key", "wrong_size", "wrong_sha"])
def test_resume_multipart_refuses_unbound_failed_record(tmp_path, monkeypatch, change):
    plan_sha, entries, _, prior, _, _ = multipart_resume_fixture(tmp_path, monkeypatch)
    failed_path = next((prior / "objects").glob("0001-*.json"))
    failed = json.loads(failed_path.read_text())
    if change == "wrong_plan": failed["plan_sha256"] = "0" * 64
    elif change == "wrong_key": failed["object_key"] = "other/key"
    elif change == "wrong_size": failed["expected_size_bytes"] += 1
    else: failed["expected_sha256"] = "0" * 64
    failed_path.write_text(json.dumps(failed))
    with pytest.raises(upload.UploadError):
        upload.load_resume(prior, entries, plan_sha, include_readme=False, multipart_state={})


def test_resume_multipart_cli_rejects_incompatible_scopes_before_io(tmp_path):
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(fixture_plan()))
    plan_sha = digest(plan.read_bytes())
    helper = tmp_path / "helper"
    helper.write_text("fake")
    base = ["--plan", str(plan), "--dataset", "hydrolakes", "--repo-root", str(tmp_path),
            "--credential-helper", str(helper), "--expected-plan-sha256", plan_sha,
            "--output", str(tmp_path / "result"), "--execute", "--resume-multipart",
            "--expected-resume-summary-sha256", "0" * 64,
            "--expected-resume-record-sha256", "0" * 64]
    assert upload.main(base) == 1
    for extra in (["--resume-from", str(tmp_path), "--recovery-receipt", str(tmp_path)],
                  ["--resume-from", str(tmp_path), "--recover-multipart", str(tmp_path)],
                  ["--resume-from", str(tmp_path), "--readme-only"]):
        assert upload.main(base + extra) == 1
    assert not (tmp_path / "result").exists()


def test_resume_multipart_cli_requires_frozen_original_receipt_hashes(tmp_path, monkeypatch):
    plan_sha, entries, _, prior, _, state = multipart_resume_fixture(tmp_path, monkeypatch)
    helper = tmp_path / "helper"
    helper.write_text("fake")
    base = ["--plan", str(tmp_path / "plan.json"), "--dataset", "hydrolakes",
            "--data-root", str(tmp_path), "--package", f"hydrolakes={tmp_path / 'package'}",
            "--repo-root", str(tmp_path / "repo"), "--credential-helper", str(helper),
            "--expected-plan-sha256", plan_sha, "--resume-from", str(prior),
            "--resume-multipart", "--output", str(tmp_path / "result"), "--execute"]
    assert upload.main(base) == 1
    assert upload.main(base + ["--expected-resume-summary-sha256", "0" * 64,
                               "--expected-resume-record-sha256", state[entries[1]["object_key"]]["record_sha256"]]) == 1
    assert upload.main(base + ["--expected-resume-summary-sha256", state[entries[1]["object_key"]]["summary_sha256"],
                               "--expected-resume-record-sha256", "0" * 64]) == 1
    assert not (tmp_path / "result").exists()


def test_remote_error_records_safe_public_http_fields_only(tmp_path):
    rows = sources(tmp_path, b"right")

    class PublicError(Exception):
        response = {"ResponseMetadata": {"HTTPStatusCode": 403},
                    "Error": {"Code": "AccessDenied", "Message": "SECRET-ACCESS-KEY"}}

    fake = FakeS3()
    fake.head_error = PublicError("SECRET-ACCESS-KEY")
    result = upload.execute(rows, "a" * 64, tmp_path / "receipt", execute_upload=True,
                            include_readme=False, session=Session(fake))
    assert result["status"] == "failed"
    raw = next((tmp_path / "receipt/objects").iterdir()).read_text()
    record = json.loads(raw)
    assert (record["error_operation"], record["error_http_status"], record["error_code"]) == ("HeadObject", 403, "AccessDenied")
    assert "SECRET-ACCESS-KEY" not in raw
