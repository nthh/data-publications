#!/usr/bin/env python3
"""Upload one selected Source Cooperative product from an exact staged plan.

The default mode validates local bytes and writes a dry-run receipt. Execution
requires --execute. This module deliberately does not create products or change
bucket settings.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import subprocess
import sys
import tempfile
import time
from typing import Any

ENDPOINT = "https://data.source.coop"
BUCKET = "nthh"
ALLOWED_PRODUCTS = frozenset({"river-plastic-inputs", "hydrolakes", "free-flowing-rivers", "lakeatlas", "grwl-raw"})
MAX_BYTES = 25_000_000_000
PART_BYTES = 64 * 1024 * 1024
STREAM_BYTES = 8 * 1024 * 1024
MAX_AUTH_RETRIES_PER_PART = 2
MAX_AUTH_WAIT_TOTAL_SECONDS = 90
AUTH_WAIT_STEP_SECONDS = 5
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MIME_BY_SUFFIX = {
    ".cpp": "text/plain", ".log": "text/plain", ".wasm": "application/wasm",
    ".css": "text/css", ".csv": "text/csv", ".dbf": "application/vnd.shp",
    ".geojson": "application/geo+json", ".gpkg": "application/geopackage+sqlite3",
    ".html": "text/html", ".jpeg": "image/jpeg", ".jpg": "image/jpeg",
    ".js": "text/javascript", ".json": "application/json", ".jsonl": "application/x-ndjson",
    ".md": "text/markdown", ".mjs": "text/javascript", ".parquet": "application/vnd.apache.parquet",
    ".pdf": "application/pdf", ".pmtiles": "application/vnd.pmtiles", ".png": "image/png",
    ".prj": "text/plain", ".py": "text/x-python", ".shp": "application/vnd.shp",
    ".shx": "application/vnd.shp", ".sqlite": "application/vnd.sqlite3",
    ".svg": "image/svg+xml", ".tif": "image/tiff", ".tiff": "image/tiff",
    ".toml": "application/toml", ".txt": "text/plain", ".webp": "image/webp",
    ".xml": "application/xml", ".yaml": "application/yaml", ".yml": "application/yaml",
    ".gz": "application/gzip", ".lock": "text/plain",
}


class UploadError(Exception):
    """Safe, non-secret validation or transfer error."""

    def __init__(self, message: str, *, operation: str | None = None,
                 http_status: int | None = None, error_code: str | None = None) -> None:
        super().__init__(message)
        self.operation = operation
        self.http_status = http_status
        self.error_code = error_code


class CredentialTooNearExpiry(UploadError):
    """Safe retry signal for a cached Source credential with under 60 seconds left."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("credential expires too soon", operation="CredentialHelper")
        self.retry_after_seconds = retry_after_seconds


SAFE_S3_CODES = {"AccessDenied", "ExpiredToken", "InvalidToken", "SignatureDoesNotMatch",
                 "RequestTimeTooSkewed", "SlowDown", "InternalError", "ServiceUnavailable",
                 "NoSuchKey", "NoSuchUpload", "NoSuchBucket", "NotFound", "PreconditionFailed",
                 "RequestTimeout", "Throttling", "403", "404", "409", "412", "429", "500", "502", "503", "504"}


def _remote_error(message: str, operation: str, exc: Exception) -> UploadError:
    response = getattr(exc, "response", None)
    status = response.get("ResponseMetadata", {}).get("HTTPStatusCode") if isinstance(response, dict) else None
    code = response.get("Error", {}).get("Code") if isinstance(response, dict) else None
    return UploadError(message, operation=operation,
                       http_status=status if type(status) is int and 100 <= status <= 599 else None,
                       error_code=code if isinstance(code, str) and code in SAFE_S3_CODES else None)


def _safe_relative(raw: Any, label: str) -> PurePosixPath:
    if not isinstance(raw, str) or not raw or "\\" in raw or raw.startswith("/"):
        raise UploadError(f"unsafe {label}")
    path = PurePosixPath(raw)
    windows = PureWindowsPath(raw)
    if windows.drive or windows.is_absolute() or any(part in ("", ".", "..") for part in raw.split("/")):
        raise UploadError(f"unsafe {label}")
    if any(part.startswith(".") for part in path.parts):
        raise UploadError(f"hidden {label}")
    return path


def _safe_file(root: Path, raw: str, label: str) -> Path:
    relative = _safe_relative(raw, label)
    if root.is_symlink() or not root.is_dir():
        raise UploadError(f"invalid {label} root")
    root = root.resolve(strict=True)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise UploadError(f"symlink in {label}")
    if not current.is_file() or not current.resolve(strict=True).is_relative_to(root):
        raise UploadError(f"invalid {label} file")
    return current


def _expected_content_type(source_path: str) -> str:
    relative = _safe_relative(source_path, "MIME source path")
    parts = relative.parts
    native = ((len(parts) == 3 and parts[:2] == ("workflow", "native-oracle"))
              or (len(parts) == 5 and parts[0] == "reports"
                  and re.fullmatch(r"baseline-r[1-9][0-9]*", parts[1]) is not None
                  and parts[2:4] == ("workflow", "native-oracle")))
    if native and not relative.suffix:
        return "application/octet-stream"
    if relative.name in {"LICENSE", "NOTICE"}:
        return "text/plain"
    content_type = MIME_BY_SUFFIX.get(relative.suffix.lower())
    if content_type is None:
        raise UploadError("unknown source MIME type")
    return content_type


def _check_root(root: Path, allowed: Path, label: str) -> Path:
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise UploadError(f"{label} must be an absolute directory without a symlink")
    resolved = root.resolve(strict=True)
    if not resolved.is_relative_to(allowed.resolve(strict=True)):
        raise UploadError(f"{label} is outside its allowed root")
    return resolved


def parse_mappings(values: list[str], allowed_ids: set[str], data_root: Path, label: str) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        dataset_id, separator, raw = value.partition("=")
        if not separator or dataset_id not in allowed_ids or dataset_id in result or not raw:
            raise UploadError(f"invalid {label} mapping")
        result[dataset_id] = _check_root(Path(raw), data_root, label)
    return result


def _validate_entry(entry: Any, products: dict[str, dict[str, Any]], *, mutable: bool) -> str:
    if not isinstance(entry, dict):
        raise UploadError("invalid plan entry")
    if entry.get("endpoint") != ENDPOINT or entry.get("bucket") != BUCKET:
        raise UploadError("plan endpoint or bucket mismatch")
    key = _safe_relative(entry.get("object_key"), "object key").as_posix()
    source = entry.get("source")
    if not isinstance(source, dict):
        raise UploadError("invalid source descriptor")
    kind = source.get("kind")
    source_path = _safe_relative(source.get("path"), "source path").as_posix()
    product_id = key.split("/", 1)[0]
    product = products.get(product_id)
    if product is None:
        raise UploadError("unknown product in object key")
    dataset_id = product["dataset_id"]
    if kind in ("package", "display_package") and source.get("dataset_id") != dataset_id:
        raise UploadError("source dataset mismatch")
    if kind == "package":
        expected = f"{product_id}/releases/{product['release']}/{source_path}"
    elif kind == "display_package":
        display = product.get("display_publication")
        if not isinstance(display, dict):
            raise UploadError("missing display binding")
        release = _safe_relative(display.get("release"), "display release")
        if len(release.parts) != 1:
            raise UploadError("invalid display release")
        expected = f"{product_id}/display/{release}/{source_path}"
    elif kind == "repository":
        if mutable:
            expected = f"{product_id}/README.md"
            if source_path != f"datasets/{dataset_id}/source-coop/product-README.md":
                raise UploadError("unexpected README source")
        else:
            if not key.startswith(f"{product_id}/metadata/"):
                raise UploadError("unexpected repository destination")
            if not source_path.startswith(f"datasets/{dataset_id}/"):
                raise UploadError("repository supplement crosses dataset boundary")
            expected = key
    else:
        raise UploadError("unknown source kind")
    if key != expected:
        raise UploadError("source and object key differ")
    if mutable and (entry.get("mutable") is not True or entry.get("content_type") != "text/markdown"
                    or entry.get("binding_status") != "canonical_generated_consumer_copy"):
        raise UploadError("invalid mutable README")
    if not mutable and entry.get("mutable"):
        raise UploadError("mutable object in immutable plan")
    if entry.get("content_type") != _expected_content_type(source_path):
        raise UploadError("planned content type differs from source extension")
    size = entry.get("size_bytes")
    if type(size) is not int or size < 0 or size > MAX_BYTES or not isinstance(entry.get("sha256"), str) or not SHA256.fullmatch(entry["sha256"]):
        raise UploadError("invalid size or SHA-256")
    if entry.get("s3_uri_proposed") != f"s3://{BUCKET}/{key}":
        raise UploadError("S3 route mismatch")
    return dataset_id


def load_plan(path: Path, dataset_id: str, include_readme: bool,
              *, readme_only: bool = False) -> tuple[str, list[dict[str, Any]]]:
    try:
        data = path.read_bytes()
        plan = json.loads(data)
    except (OSError, ValueError) as exc:
        raise UploadError("cannot read upload plan") from exc
    if not isinstance(plan, dict) or plan.get("schema_version") != 1 or plan.get("plan_type") != "source_coop_immutable_exact_file_plan":
        raise UploadError("unexpected upload plan schema")
    raw_products = plan.get("products")
    if not isinstance(raw_products, list) or not raw_products:
        raise UploadError("missing products")
    products: dict[str, dict[str, Any]] = {}
    for product in raw_products:
        if not isinstance(product, dict):
            raise UploadError("invalid product")
        pid = product.get("product_id")
        if pid not in ALLOWED_PRODUCTS or product.get("dataset_id") != pid or pid in products or product.get("owner") != BUCKET or product.get("bucket") != BUCKET or product.get("endpoint") != ENDPOINT:
            raise UploadError("unknown product or owner")
        release = _safe_relative(product.get("release"), "release")
        if len(release.parts) != 1:
            raise UploadError("invalid release")
        products[pid] = product
    if dataset_id not in products:
        raise UploadError("selected dataset absent from plan")
    files = plan.get("files")
    readmes = plan.get("mutable_metadata")
    if not isinstance(files, list) or not isinstance(readmes, list):
        raise UploadError("invalid plan file lists")
    seen: set[str] = set()
    total = 0
    selected: list[dict[str, Any]] = []
    for mutable, entries in ((False, files), (True, readmes)):
        for entry in entries:
            owner_id = _validate_entry(entry, products, mutable=mutable)
            key = entry["object_key"]
            if key in seen:
                raise UploadError("duplicate object key")
            seen.add(key)
            if not mutable:
                total += entry["size_bytes"]
            if owner_id == dataset_id and ((mutable and (include_readme or readme_only))
                                           or (not mutable and not readme_only)):
                selected.append(entry)
    if total > MAX_BYTES or total != plan.get("total_bytes") or len(files) != plan.get("file_count"):
        raise UploadError("plan byte total or count mismatch")
    if (include_readme or readme_only) and sum(row.get("mutable") is True for row in selected) != 1:
        raise UploadError("selected product has no unique README")
    if readme_only and (len(selected) != 1 or selected[0].get("mutable") is not True):
        raise UploadError("README-only selection must contain exactly one mutable product README")
    return hashlib.sha256(data).hexdigest(), selected


def resolve_sources(entries: list[dict[str, Any]], packages: dict[str, Path], displays: dict[str, Path], repo_root: Path) -> list[tuple[dict[str, Any], Path]]:
    resolved = []
    for entry in entries:
        source = entry["source"]
        kind = source["kind"]
        dataset_id = source.get("dataset_id")
        if kind == "package":
            root = packages.get(dataset_id)
        elif kind == "display_package":
            root = displays.get(dataset_id)
        else:
            root = repo_root
        if root is None:
            raise UploadError(f"missing explicit {kind} root")
        resolved.append((entry, _safe_file(root, source["path"], kind)))
    return resolved


def hash_file(path: Path) -> tuple[int, str]:
    before = path.stat()
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(STREAM_BYTES):
            size += len(chunk)
            digest.update(chunk)
    after = path.stat()
    if (size != before.st_size or size != after.st_size or before.st_ino != after.st_ino or before.st_mtime_ns != after.st_mtime_ns):
        raise UploadError("source changed while hashing")
    return size, digest.hexdigest()


def preflight(sources: list[tuple[dict[str, Any], Path]]) -> None:
    for entry, path in sources:
        size, digest = hash_file(path)
        if size != entry["size_bytes"] or digest != entry["sha256"]:
            raise UploadError(f"local size or SHA-256 differs from plan: {entry['object_key']}")


class S3Session:
    def __init__(self, helper: Path, region: str = "us-west-2") -> None:
        self.helper = helper
        self.region = region
        self.last_expiration: datetime | None = None

    def client(self) -> Any:
        try:
            import boto3
            from botocore.config import Config
            completed = subprocess.run([str(self.helper), "creds", "--format", "credential-process"],
                                       check=True, capture_output=True, timeout=60)
            credential = json.loads(completed.stdout)
            if credential.get("Version") != 1 or not all(isinstance(credential.get(k), str) and credential[k] for k in ("AccessKeyId", "SecretAccessKey", "SessionToken", "Expiration")):
                raise ValueError("invalid credential shape")
            expiry = datetime.fromisoformat(credential["Expiration"].replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                raise ValueError("credential expiration lacks time zone")
            remaining = (expiry - datetime.now(timezone.utc)).total_seconds()
            if remaining < 60:
                raise CredentialTooNearExpiry(max(1, math.ceil(remaining) + 1))
            self.last_expiration = expiry
            return boto3.client("s3", endpoint_url=ENDPOINT, region_name=self.region,
                                aws_access_key_id=credential["AccessKeyId"],
                                aws_secret_access_key=credential["SecretAccessKey"],
                                aws_session_token=credential["SessionToken"],
                                config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 3}))
        except subprocess.TimeoutExpired:
            raise UploadError("credential helper timed out", operation="CredentialHelper") from None
        except subprocess.CalledProcessError:
            raise UploadError("credential helper exited unsuccessfully", operation="CredentialHelper") from None
        except CredentialTooNearExpiry:
            raise
        except Exception:
            raise UploadError("credential helper or S3 client failed", operation="S3Client") from None


def _not_found(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    return isinstance(response, dict) and str(response.get("Error", {}).get("Code")) in {"404", "NoSuchKey", "NotFound"}


def _head(client: Any, key: str) -> dict[str, Any] | None:
    try:
        return client.head_object(Bucket=BUCKET, Key=key)
    except Exception as exc:
        if _not_found(exc):
            return None
        raise _remote_error("remote HEAD failed", "HeadObject", exc) from None


def _check_head_type(head: dict[str, Any], expected: str) -> None:
    if head.get("ContentType") != expected:
        raise UploadError("remote content type differs from plan")


def _remote_hash(session: S3Session, key: str, size: int) -> str:
    digest = hashlib.sha256()
    offset = 0
    while offset < size:
        end = min(size, offset + PART_BYTES) - 1
        try:
            response = session.client().get_object(Bucket=BUCKET, Key=key, Range=f"bytes={offset}-{end}")
            if response.get("ContentRange") != f"bytes {offset}-{end}/{size}":
                raise UploadError("remote ranged GET returned wrong range")
            body = response["Body"]
            received = 0
            try:
                while chunk := body.read(STREAM_BYTES):
                    received += len(chunk)
                    digest.update(chunk)
            finally:
                body.close()
            if received != end - offset + 1:
                raise UploadError("remote ranged GET returned wrong length")
        except UploadError:
            raise
        except Exception as exc:
            raise _remote_error("remote ranged GET failed", "GetObject", exc) from None
        offset = end + 1
    return digest.hexdigest()


def _put(session: S3Session, entry: dict[str, Any], path: Path, prior_head: dict[str, Any] | None,
         record: dict[str, Any], persist: Any) -> None:
    key = entry["object_key"]
    common = {"Bucket": BUCKET, "Key": key, "ContentType": entry["content_type"], "Metadata": {"sha256": entry["sha256"]}}
    condition: dict[str, str] = {"IfNoneMatch": "*"}
    if entry.get("mutable") and prior_head is not None:
        etag = prior_head.get("ETag")
        if not isinstance(etag, str) or not etag:
            raise UploadError("existing README lacks an ETag for conditional replacement")
        condition = {"IfMatch": etag}
    # A fresh helper invocation is made for each part, so long transfers can renew credentials.
    if entry["size_bytes"] <= PART_BYTES:
        try:
            with path.open("rb") as stream:
                session.client().put_object(**common, Body=stream, ContentLength=entry["size_bytes"], **condition)
        except Exception as exc:
            raise _remote_error("PUT failed", "PutObject", exc) from None
        return
    upload_id = None
    operation = "CreateMultipartUpload"
    try:
        response = session.client().create_multipart_upload(**common)
        upload_id = response["UploadId"]
        if not isinstance(upload_id, str) or not upload_id:
            raise UploadError("multipart creation returned no upload ID")
        record["multipart"] = {"upload_id": upload_id, "state": "open", "parts": []}
        persist()
        parts = []
        with path.open("rb") as stream:
            number = 1
            while chunk := stream.read(PART_BYTES):
                operation = "UploadPart"
                result = session.client().upload_part(Bucket=BUCKET, Key=key, UploadId=upload_id,
                                                      PartNumber=number, Body=chunk)
                parts.append({"PartNumber": number, "ETag": result["ETag"]})
                record["multipart"]["parts"] = list(parts)
                persist()
                number += 1
        operation = "CompleteMultipartUpload"
        session.client().complete_multipart_upload(Bucket=BUCKET, Key=key, UploadId=upload_id,
                                                   MultipartUpload={"Parts": parts},
                                                   **condition)
        record["multipart"]["state"] = "completed"
        persist()
        upload_id = None
    except Exception as exc:
        if upload_id is not None:
            try:
                session.client().abort_multipart_upload(Bucket=BUCKET, Key=key, UploadId=upload_id)
                record["multipart"]["state"] = "aborted"
            except Exception as abort_exc:
                record["multipart"]["state"] = "abort_failed"
                safe_abort = _remote_error("multipart abort failed", "AbortMultipartUpload", abort_exc)
                if safe_abort.http_status is not None:
                    record["multipart"]["abort_http_status"] = safe_abort.http_status
                if safe_abort.error_code is not None:
                    record["multipart"]["abort_error_code"] = safe_abort.error_code
            persist()
        raise _remote_error("multipart upload failed", operation, exc) from None


def _resume_existing_multipart(session: S3Session, entry: dict[str, Any], path: Path,
                               binding: dict[str, Any], record: dict[str, Any], persist: Any) -> None:
    """Replay every part against the exact journaled upload ID, then close it."""
    upload_id = binding["upload_id"]
    key = entry["object_key"]
    record["multipart_resume"] = {"mode": "existing_multipart", **{
        k: binding[k] for k in ("summary_sha256", "record_sha256", "record_name")}}
    record["multipart"] = {"upload_id": upload_id, "state": "open", "parts": []}
    persist()
    operation = "UploadPart"
    total_auth_wait = 0

    def wait_for_refresh(seconds: int) -> None:
        nonlocal total_auth_wait
        while seconds > 0:
            step = min(AUTH_WAIT_STEP_SECONDS, seconds)
            time.sleep(step)
            total_auth_wait += step
            seconds -= step

    def journal_auth_retry(attempt: int, reason: str) -> None:
        record.setdefault("auth_retries", []).append({
            "operation": "UploadPart", "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "attempt": attempt, "reason": reason})
        persist()

    try:
        parts = []
        with path.open("rb") as stream:
            number = 1
            while chunk := stream.read(PART_BYTES):
                for retry in range(MAX_AUTH_RETRIES_PER_PART + 1):
                    try:
                        response = session.client().upload_part(Bucket=BUCKET, Key=key, UploadId=upload_id,
                                                                PartNumber=number, Body=chunk)
                        break
                    except CredentialTooNearExpiry as exc:
                        if retry == MAX_AUTH_RETRIES_PER_PART or exc.retry_after_seconds < 0 \
                                or exc.retry_after_seconds > MAX_AUTH_WAIT_TOTAL_SECONDS - total_auth_wait:
                            raise
                        journal_auth_retry(retry + 1, "CredentialTooNearExpiry")
                        wait_for_refresh(exc.retry_after_seconds)
                    except Exception as exc:
                        if retry == MAX_AUTH_RETRIES_PER_PART or not _is_expired_upload_part(exc):
                            raise
                        expiry = getattr(session, "last_expiration", None)
                        remaining = ((expiry - datetime.now(timezone.utc)).total_seconds()
                                     if isinstance(expiry, datetime) and expiry.tzinfo is not None else -1)
                        delay = max(0, math.ceil(remaining) + 1)
                        if delay > MAX_AUTH_WAIT_TOTAL_SECONDS - total_auth_wait:
                            raise
                        journal_auth_retry(retry + 1, "ExpiredToken")
                        wait_for_refresh(delay)
                etag = response.get("ETag")
                if not isinstance(etag, str) or not etag:
                    raise UploadError("resumed part lacks an ETag")
                parts.append({"PartNumber": number, "ETag": etag})
                record["multipart"]["parts"] = list(parts)
                record["bytes_transferred"] += len(chunk)
                persist()
                number += 1
        operation = "CompleteMultipartUpload"
        session.client().complete_multipart_upload(Bucket=BUCKET, Key=key, UploadId=upload_id,
                                                   MultipartUpload={"Parts": parts}, IfNoneMatch="*")
        record["multipart"]["state"] = "completed"
        persist()
    except Exception as exc:
        # Keep the original upload ID and this attempt's parts journaled for
        # another exact retry. Never create a replacement upload ID here.
        if isinstance(exc, UploadError):
            raise
        raise _remote_error("multipart resume failed", operation, exc) from None


def _is_expired_upload_part(exc: Exception) -> bool:
    try:
        from botocore.exceptions import ClientError
    except ImportError:
        return False
    return (isinstance(exc, ClientError) and exc.operation_name == "UploadPart"
            and isinstance(exc.response, dict)
            and exc.response.get("Error", {}).get("Code") == "ExpiredToken")


def _write_json(path: Path, value: dict[str, Any]) -> None:
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".receipt-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _receipt_json(path: Path, label: str) -> tuple[dict[str, Any], str]:
    if path.is_symlink() or not path.is_file():
        raise UploadError(f"invalid {label}")
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, ValueError):
        raise UploadError(f"cannot read {label}") from None
    if not isinstance(value, dict):
        raise UploadError(f"invalid {label}")
    return value, hashlib.sha256(raw).hexdigest()


def load_resume(previous: Path, entries: list[dict[str, Any]], plan_sha256: str,
                include_readme: bool, recovery: Path | None = None,
                multipart_state: dict[str, dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    """Bind a failed attempt's full-byte proofs to the exact selected plan."""
    if previous.is_symlink() or not previous.is_dir():
        raise UploadError("invalid prior receipt directory")
    records_dir = previous / "objects"
    if records_dir.is_symlink() or not records_dir.is_dir():
        raise UploadError("invalid prior receipt records")
    summary, summary_sha = _receipt_json(previous / "summary.json", "prior summary")
    if (summary.get("schema_version") != 1 or summary.get("mode") != "execute"
            or summary.get("status") != "failed" or summary.get("plan_sha256") != plan_sha256
            or summary.get("object_count") != len(entries)
            or summary.get("include_readme") is not include_readme
            or type(summary.get("failed")) is not int or summary["failed"] != 1
            or type(summary.get("completed")) is not int):
        raise UploadError("prior receipt is not a stopped failed attempt for this exact plan")
    allowed = {entry["object_key"]: (index, entry) for index, entry in enumerate(entries)}
    proofs: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    positions: set[int] = set()
    incomplete: dict[str, str] = {}
    failed = 0
    failed_index = None
    for path in sorted(records_dir.iterdir()):
        record, record_sha = _receipt_json(path, "prior object record")
        key = record.get("object_key")
        if key not in allowed or key in seen:
            raise UploadError("prior receipt has unknown or duplicate object key")
        index, entry = allowed[key]
        expected_name = f"{index:04d}-{hashlib.sha256(key.encode()).hexdigest()[:16]}.json"
        if path.name != expected_name:
            raise UploadError("prior receipt object record has wrong index")
        seen.add(key)
        positions.add(index)
        if (record.get("schema_version") != 1 or record.get("plan_sha256") != plan_sha256
                or record.get("bucket") != BUCKET or record.get("expected_sha256") != entry["sha256"]
                or record.get("expected_size_bytes") != entry["size_bytes"]
                or record.get("mutable") is not bool(entry.get("mutable"))):
            raise UploadError("prior object record differs from selected plan")
        status = record.get("status")
        remote_sha = record.get("remote_sha256")
        if status in {"uploaded_verified", "verified_existing"}:
            if remote_sha != entry["sha256"]:
                raise UploadError("prior remote SHA-256 differs from selected plan")
            multipart = record.get("multipart")
            if isinstance(multipart, dict) and multipart.get("state") in {"open", "abort_failed"}:
                raise UploadError("prior verified record has unfinished multipart state")
            if not entry.get("mutable"):
                proofs[key] = {"summary_sha256": summary_sha, "record_sha256": record_sha,
                               "record_name": path.name, "prior_status": status,
                               "plan_sha256": plan_sha256, "expected_sha256": entry["sha256"],
                               "expected_size_bytes": entry["size_bytes"],
                               "remote_sha256": remote_sha}
        elif status == "failed":
            failed += 1
            failed_index = index
            if remote_sha is not None and remote_sha != entry["sha256"]:
                raise UploadError("prior remote SHA-256 differs from selected plan")
            multipart = record.get("multipart")
            if isinstance(multipart, dict) and multipart.get("state") in {"open", "abort_failed"}:
                upload_id = multipart.get("upload_id")
                if not isinstance(upload_id, str) or not upload_id:
                    raise UploadError("prior multipart state lacks upload ID")
                incomplete[key] = upload_id
                if multipart_state is not None:
                    if entry.get("mutable") or entry["size_bytes"] <= PART_BYTES:
                        raise UploadError("multipart resume requires a large immutable plan entry")
                    multipart_state[key] = {"upload_id": upload_id, "summary_sha256": summary_sha,
                                            "record_sha256": record_sha, "record_name": path.name,
                                            "plan_sha256": plan_sha256, "expected_sha256": entry["sha256"],
                                            "expected_size_bytes": entry["size_bytes"]}
        else:
            raise UploadError("prior receipt has an invalid object status")
    if (failed != summary["failed"] or len(seen) != summary["completed"] + summary["failed"]
            or positions != set(range(len(seen))) or failed_index != summary["completed"]):
        raise UploadError("prior receipt counts do not match object records")
    if incomplete:
        if multipart_state is not None:
            if recovery is not None or len(incomplete) != 1 or len(multipart_state) != 1:
                raise UploadError("multipart resume requires one unfinished upload and no recovery receipt")
        elif recovery is None:
            raise UploadError("unfinished prior multipart requires a completed recovery receipt")
        else:
            assert recovery is not None
            if recovery.is_symlink() or not recovery.is_dir() or (recovery / "objects").is_symlink():
                raise UploadError("invalid multipart recovery receipt")
            recovered, _ = _receipt_json(recovery / "summary.json", "multipart recovery summary")
            if (recovered.get("schema_version") != 1 or recovered.get("mode") != "multipart_recovery"
                    or recovered.get("plan_sha256") != plan_sha256 or recovered.get("status") != "complete"
                    or recovered.get("object_count") != len(incomplete)
                    or recovered.get("completed") != len(incomplete) or recovered.get("failed") != 0):
                raise UploadError("multipart recovery is incomplete or bound to another plan")
            recovered_ids: dict[str, str] = {}
            for path in (recovery / "objects").iterdir():
                item, _ = _receipt_json(path, "multipart recovery object")
                key = item.get("object_key")
                if (key not in incomplete or key in recovered_ids or item.get("schema_version") != 1
                        or item.get("plan_sha256") != plan_sha256 or item.get("bucket") != BUCKET
                        or item.get("upload_id") != incomplete[key] or item.get("action") != "abort_multipart"
                        or item.get("status") != "aborted"):
                    raise UploadError("multipart recovery does not match prior upload ID")
                recovered_ids[key] = item["upload_id"]
            if recovered_ids != incomplete:
                raise UploadError("multipart recovery omits unfinished prior upload")
    elif recovery is not None:
        raise UploadError("multipart recovery receipt provided without unfinished upload")
    elif multipart_state is not None:
        raise UploadError("multipart resume receipt has no unfinished upload")
    return proofs


def execute(sources: list[tuple[dict[str, Any], Path]], plan_sha256: str, output: Path,
            *, execute_upload: bool, include_readme: bool, session: S3Session | None = None,
            resume_proofs: dict[str, dict[str, Any]] | None = None,
            resume_multipart: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    if output.exists():
        raise UploadError("receipt output already exists")
    resume_proofs = resume_proofs or {}
    resume_multipart = resume_multipart or {}
    if resume_proofs and not execute_upload:
        raise UploadError("resume requires execution mode")
    source_by_key = {entry["object_key"]: entry for entry, _ in sources}
    if any(key not in source_by_key or source_by_key[key].get("mutable")
           or proof.get("plan_sha256") != plan_sha256
           or proof.get("expected_sha256") != source_by_key[key]["sha256"]
           or proof.get("remote_sha256") != source_by_key[key]["sha256"]
           or proof.get("expected_size_bytes") != source_by_key[key]["size_bytes"]
           for key, proof in resume_proofs.items()):
        raise UploadError("resume proof is outside selected sources")
    if (resume_multipart and (not execute_upload or len(resume_multipart) != 1
            or bool(set(resume_multipart) & set(resume_proofs)) or
            any(key not in source_by_key or source_by_key[key].get("mutable")
                or source_by_key[key]["size_bytes"] <= PART_BYTES
                or binding.get("plan_sha256") != plan_sha256
                or binding.get("expected_sha256") != source_by_key[key]["sha256"]
                or binding.get("expected_size_bytes") != source_by_key[key]["size_bytes"]
                or not isinstance(binding.get("upload_id"), str) or not binding["upload_id"]
                or not isinstance(binding.get("summary_sha256"), str)
                or not SHA256.fullmatch(binding["summary_sha256"])
                or not isinstance(binding.get("record_sha256"), str)
                or not SHA256.fullmatch(binding["record_sha256"])
                or not isinstance(binding.get("record_name"), str)
                for key, binding in resume_multipart.items()))):
        raise UploadError("multipart resume is outside selected sources")
    preflight([(entry, path) for entry, path in sources if entry["object_key"] not in resume_proofs])
    output.mkdir(parents=True)
    records_dir = output / "objects"
    records_dir.mkdir()
    summary: dict[str, Any] = {"schema_version": 1, "plan_sha256": plan_sha256,
                               "mode": "execute" if execute_upload else "dry_run",
                               "include_readme": include_readme, "object_count": len(sources),
                               "status": "running", "completed": 0, "failed": 0,
                               "reused_prior_verified": 0, "fresh_verified": 0}
    if resume_multipart:
        summary["resume_mode"] = "existing_multipart"
        summary["resumed_multipart"] = 0
        summary["multipart_resume_parent_summary_sha256"] = next(iter(resume_multipart.values()))["summary_sha256"]
    _write_json(output / "summary.json", summary)
    if execute_upload and session is None:
        raise UploadError("S3 session required")
    for index, (entry, path) in enumerate(sources):
        key = entry["object_key"]
        started = time.monotonic()
        record_path = records_dir / f"{index:04d}-{hashlib.sha256(key.encode()).hexdigest()[:16]}.json"
        record = {"schema_version": 1, "plan_sha256": plan_sha256, "bucket": BUCKET,
                  "object_key": key, "expected_sha256": entry["sha256"],
                  "expected_size_bytes": entry["size_bytes"], "mutable": bool(entry.get("mutable")),
                  "status": "pending", "remote_sha256": None, "bytes_transferred": 0,
                  "resumable": True}
        def persist() -> None:
            _write_json(record_path, record)
        try:
            if not execute_upload:
                record["status"] = "dry_run"
            else:
                assert session is not None
                if key in resume_proofs:
                    proof = resume_proofs[key]
                    head = _head(session.client(), key)
                    if head is None or head.get("ContentLength") != entry["size_bytes"]:
                        raise UploadError("prior verified object is absent or changed size")
                    _check_head_type(head, entry["content_type"])
                    metadata = head.get("ResponseMetadata")
                    if not isinstance(metadata, dict) or metadata.get("HTTPStatusCode") != 200:
                        raise UploadError("prior verified object HEAD lacks HTTP 200 evidence")
                    record["prior_proof"] = proof
                    record["current_head"] = {"checked_at": datetime.now(timezone.utc).isoformat(),
                                              "http_status": metadata["HTTPStatusCode"],
                                              "size_bytes": head["ContentLength"],
                                              "content_type": head["ContentType"]}
                    record["remote_sha256"] = proof["remote_sha256"]
                    record["remote_sha256_scope"] = "prior_attempt_full_remote_readback"
                    record["status"] = "verified_prior_attempt"
                    summary["reused_prior_verified"] += 1
                else:
                    # Recheck the file immediately before any write, after the all-file preflight.
                    actual_size, actual_sha = hash_file(path)
                    if (actual_size, actual_sha) != (entry["size_bytes"], entry["sha256"]):
                        raise UploadError("local file changed after preflight")
                    head = _head(session.client(), key)
                    if key in resume_multipart and head is not None:
                        raise UploadError("multipart resume target already exists")
                    if head is not None:
                        _check_head_type(head, entry["content_type"])
                        remote_size = head.get("ContentLength")
                        if type(remote_size) is not int:
                            raise UploadError("remote HEAD missing size")
                        if entry.get("mutable"):
                            if remote_size > 16 * 1024 * 1024:
                                raise UploadError("existing README exceeds safe verification size")
                            previous_sha = _remote_hash(session, key, remote_size)
                            record["previous_remote_sha256"] = previous_sha
                            record["previous_remote_size_bytes"] = remote_size
                        else:
                            if remote_size != entry["size_bytes"]:
                                raise UploadError("existing immutable object has different size")
                            actual_remote_sha = _remote_hash(session, key, remote_size)
                            record["remote_sha256"] = actual_remote_sha
                            if actual_remote_sha != entry["sha256"]:
                                raise UploadError("existing immutable object has different bytes")
                            record["status"] = "verified_existing"
                    if record["status"] != "verified_existing":
                        if entry.get("mutable") and head is not None and record.get("previous_remote_sha256") == entry["sha256"]:
                            record["remote_sha256"] = entry["sha256"]
                            record["status"] = "verified_existing"
                        else:
                            if key in resume_multipart:
                                _resume_existing_multipart(session, entry, path, resume_multipart[key], record, persist)
                            else:
                                _put(session, entry, path, head, record, persist)
                            record["bytes_transferred"] = entry["size_bytes"]
                            # Validate actual remote bytes; self-declared metadata is not evidence.
                            after = _head(session.client(), key)
                            if after is None or after.get("ContentLength") != entry["size_bytes"]:
                                raise UploadError("uploaded object absent or wrong size")
                            _check_head_type(after, entry["content_type"])
                            actual_remote_sha = _remote_hash(session, key, entry["size_bytes"])
                            record["remote_sha256"] = actual_remote_sha
                            if key in resume_multipart:
                                record["remote_sha256_scope"] = "current_attempt_full_remote_readback"
                            if actual_remote_sha != entry["sha256"]:
                                raise UploadError("uploaded object failed byte verification")
                            record["status"] = "uploaded_verified"
                            if key in resume_multipart:
                                summary["resumed_multipart"] += 1
                    summary["fresh_verified"] += 1
            summary["completed"] += 1
        except UploadError as exc:
            record["status"] = "failed"
            record["error_class"] = type(exc).__name__
            record["error"] = str(exc)
            if exc.operation is not None:
                record["error_operation"] = exc.operation
            if exc.http_status is not None:
                record["error_http_status"] = exc.http_status
            if exc.error_code is not None:
                record["error_code"] = exc.error_code
            summary["failed"] += 1
        except Exception:
            record["status"] = "failed"
            record["error_class"] = "UnexpectedError"
            record["error"] = "unexpected upload error"
            summary["failed"] += 1
        finally:
            record["elapsed_seconds"] = round(time.monotonic() - started, 3)
            persist()
            _write_json(output / "summary.json", summary)
        if record["status"] == "failed":
            break
    summary["status"] = "failed" if summary["failed"] else "complete"
    _write_json(output / "summary.json", summary)
    return summary


def recover_multipart(previous: Path, entries: list[dict[str, Any]], plan_sha256: str,
                      output: Path, session: S3Session) -> dict[str, Any]:
    """Abort only incomplete multipart IDs journaled by a matching prior run."""
    if output.exists() or previous.is_symlink() or not previous.is_dir():
        raise UploadError("invalid recovery receipt directory")
    summary_path = previous / "summary.json"
    records_dir = previous / "objects"
    if summary_path.is_symlink() or records_dir.is_symlink() or not records_dir.is_dir():
        raise UploadError("invalid recovery receipt files")
    try:
        old_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UploadError("cannot read recovery summary") from exc
    if old_summary.get("mode") != "execute" or old_summary.get("plan_sha256") != plan_sha256:
        raise UploadError("recovery receipt does not match exact execution plan")
    allowed = {row["object_key"]: row for row in entries}
    pending: list[dict[str, str]] = []
    for path in sorted(records_dir.glob("*.json")):
        if path.is_symlink() or not path.is_file():
            raise UploadError("invalid recovery object record")
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise UploadError("cannot read recovery object record") from exc
        multipart = record.get("multipart")
        if not isinstance(multipart, dict) or multipart.get("state") not in {"open", "abort_failed"}:
            continue
        key = record.get("object_key")
        item = allowed.get(key)
        upload_id = multipart.get("upload_id")
        if (item is None or record.get("bucket") != BUCKET or record.get("plan_sha256") != plan_sha256
                or record.get("expected_sha256") != item["sha256"] or not isinstance(upload_id, str) or not upload_id):
            raise UploadError("recovery multipart record is outside selected plan")
        pending.append({"object_key": key, "upload_id": upload_id})
    output.mkdir(parents=True)
    destination = output / "objects"
    destination.mkdir()
    result: dict[str, Any] = {"schema_version": 1, "mode": "multipart_recovery", "plan_sha256": plan_sha256,
                              "object_count": len(pending), "completed": 0, "failed": 0, "status": "running"}
    _write_json(output / "summary.json", result)
    for index, item in enumerate(pending):
        record = {"schema_version": 1, "plan_sha256": plan_sha256, "bucket": BUCKET,
                  "object_key": item["object_key"], "upload_id": item["upload_id"], "action": "abort_multipart"}
        abort_attempted = False
        try:
            client = session.client()
            abort_attempted = True
            client.abort_multipart_upload(Bucket=BUCKET, Key=item["object_key"],
                                          UploadId=item["upload_id"])
            record["status"] = "aborted"
            record["abort_attempted"] = True
            result["completed"] += 1
        except Exception as exc:
            record["status"] = "abort_failed"
            record["error_class"] = "RemoteAbortError"
            record["abort_attempted"] = abort_attempted
            error_type = type(exc).__name__
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", error_type):
                record["error_type"] = error_type
            safe = (exc if isinstance(exc, UploadError) else
                    _remote_error("multipart recovery abort failed",
                                  "AbortMultipartUpload" if abort_attempted else "S3Client", exc))
            record["error_operation"] = safe.operation or ("AbortMultipartUpload" if abort_attempted else "S3Client")
            if safe.http_status is not None:
                record["error_http_status"] = safe.http_status
            if safe.error_code is not None:
                record["error_code"] = safe.error_code
            result["failed"] += 1
        _write_json(destination / f"{index:04d}-{hashlib.sha256(item['object_key'].encode()).hexdigest()[:16]}.json", record)
        _write_json(output / "summary.json", result)
    result["status"] = "failed" if result["failed"] else "complete"
    _write_json(output / "summary.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--dataset", required=True, choices=sorted(ALLOWED_PRODUCTS))
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--credential-helper", type=Path)
    parser.add_argument("--expected-plan-sha256", help="required 64-character plan digest for --execute")
    parser.add_argument("--recover-multipart", type=Path, help="abort only incomplete uploads recorded by this prior receipt")
    parser.add_argument("--resume-from", type=Path, help="reuse exact prior full-byte proofs from a stopped failed attempt")
    parser.add_argument("--resume-multipart", action="store_true", help="replay all parts on the failed receipt's own upload ID")
    parser.add_argument("--expected-resume-summary-sha256", help="frozen SHA-256 of the stopped receipt summary")
    parser.add_argument("--expected-resume-record-sha256", help="frozen SHA-256 of its failed multipart object record")
    parser.add_argument("--recovery-receipt", type=Path, help="completed scoped abort receipt for prior unfinished multipart")
    parser.add_argument("--package", action="append", default=[], metavar="ID=ABSOLUTE_PATH")
    parser.add_argument("--display-package", action="append", default=[], metavar="ID=ABSOLUTE_PATH")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--include-readme", action="store_true")
    parser.add_argument("--readme-only", action="store_true", help="upload only the selected product-root mutable README")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--region", default="us-west-2")
    args = parser.parse_args(argv)
    try:
        if args.execute and (args.credential_helper is None or not args.credential_helper.is_absolute() or not args.credential_helper.is_file()):
            raise UploadError("--execute requires an absolute credential helper file")
        if args.execute and (not isinstance(args.expected_plan_sha256, str) or not SHA256.fullmatch(args.expected_plan_sha256)):
            raise UploadError("--execute requires --expected-plan-sha256")
        if args.recover_multipart is not None and not args.execute:
            raise UploadError("multipart recovery requires --execute")
        if args.resume_from is not None and not args.execute:
            raise UploadError("resume requires --execute")
        if args.resume_multipart and args.resume_from is None:
            raise UploadError("--resume-multipart requires --resume-from")
        if args.resume_multipart and (not isinstance(args.expected_resume_summary_sha256, str)
                                      or not SHA256.fullmatch(args.expected_resume_summary_sha256)
                                      or not isinstance(args.expected_resume_record_sha256, str)
                                      or not SHA256.fullmatch(args.expected_resume_record_sha256)):
            raise UploadError("--resume-multipart requires both frozen prior receipt SHA-256 digests")
        if not args.resume_multipart and (args.expected_resume_summary_sha256 is not None
                                          or args.expected_resume_record_sha256 is not None):
            raise UploadError("frozen multipart receipt digests require --resume-multipart")
        if args.resume_multipart and (args.recovery_receipt is not None or args.recover_multipart is not None
                                      or args.readme_only):
            raise UploadError("--resume-multipart cannot combine with recovery or README-only mode")
        if args.recover_multipart is not None and (args.resume_from is not None or args.recovery_receipt is not None):
            raise UploadError("multipart recovery and resume must be separate invocations")
        if args.recovery_receipt is not None and args.resume_from is None:
            raise UploadError("--recovery-receipt requires --resume-from")
        if args.readme_only and (args.include_readme or args.recover_multipart is not None
                                 or args.resume_from is not None or args.package or args.display_package):
            raise UploadError("--readme-only cannot include package mappings, --include-readme, or recovery/resume")
        plan_sha, entries = load_plan(args.plan, args.dataset, args.include_readme,
                                      readme_only=args.readme_only)
        if args.execute and plan_sha != args.expected_plan_sha256:
            raise UploadError("upload plan SHA-256 differs from expected digest")
        if args.recover_multipart is not None:
            result = recover_multipart(args.recover_multipart, entries, plan_sha, args.output,
                                       S3Session(args.credential_helper, args.region))
            print(json.dumps(result, sort_keys=True))
            return 0 if result["status"] == "complete" else 1
        if args.data_root is None and not args.readme_only:
            raise UploadError("--data-root is required for immutable package uploads")
        data_root = (_check_root(args.data_root, args.data_root, "data root")
                     if args.data_root is not None else None)
        repo_root = _check_root(args.repo_root, args.repo_root, "repository root")
        selected = {args.dataset}
        packages = parse_mappings(args.package, selected, data_root, "package") if data_root else {}
        displays = parse_mappings(args.display_package, selected, data_root, "display package") if data_root else {}
        sources = resolve_sources(entries, packages, displays, repo_root)
        multipart_state: dict[str, dict[str, Any]] | None = {} if args.resume_multipart else None
        resume_proofs = (load_resume(args.resume_from, entries, plan_sha, args.include_readme,
                                     args.recovery_receipt, multipart_state) if args.resume_from is not None else None)
        if args.resume_multipart:
            assert multipart_state is not None
            binding = next(iter(multipart_state.values()))
            if (binding["summary_sha256"] != args.expected_resume_summary_sha256
                    or binding["record_sha256"] != args.expected_resume_record_sha256):
                raise UploadError("multipart resume receipt differs from frozen digests")
        result = execute(sources, plan_sha, args.output, execute_upload=args.execute,
                         include_readme=args.include_readme or args.readme_only,
                         session=S3Session(args.credential_helper, args.region) if args.execute else None,
                         resume_proofs=resume_proofs, resume_multipart=multipart_state)
        print(json.dumps(result, sort_keys=True))
        return 0 if result["status"] == "complete" else 1
    except UploadError as exc:
        print(f"upload validation failed: {exc}", file=sys.stderr)
        return 1
    except Exception:
        print("upload failed: unexpected error", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
