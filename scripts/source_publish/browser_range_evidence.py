"""Independently check bounded browser range attestations and one frozen footer policy."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

MIB = 1024 * 1024
ORDINARY_LIMIT = 16 * MIB
FOOTER_LIMIT = 32 * MIB
CASE_LIMIT = 128 * MIB
TOTAL_LIMIT = 1024 * MIB
SHA = re.compile(r"[0-9a-f]{64}\Z")
RANGE = re.compile(r"bytes=(\d+)-(\d+)\Z")
POLICY_KEYS = frozenset(("schema_version", "kind", "dataset_id", "case_id",
    "max_requests_per_case", "plan_sha256", "browser_controls_sha256", "object_url",
    "object_sha256", "object_size_bytes", "footer_metadata_bytes", "range", "range_sha256"))
DOCUMENTARY_KEYS = frozenset(("recorded_at_utc", "structural_proof", "failed_diagnostic",
    "unchanged_requirements", "reason"))


class BrowserRangeError(ValueError):
    """Browser transport evidence or its independent allowance is invalid."""


def _integer(value: object) -> bool:
    return type(value) is int and 0 <= value <= 2**53 - 1


def _closed_range(value: object, size: int) -> tuple[int, int, int]:
    match = RANGE.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        raise BrowserRangeError("browser request lacks a closed byte Range")
    start, end = map(int, match.groups())
    if start > end or end >= size:
        raise BrowserRangeError("browser Range is outside its planned object")
    return start, end, end - start + 1


def _policy(path: Path | None, expected_sha: str | None, *, dataset_id: str,
            plan_sha: str, controls_sha: str, planned_assets: dict) -> dict | None:
    if (path is None) != (expected_sha is None):
        raise BrowserRangeError("browser metadata policy requires path and independent SHA-256")
    if path is None:
        return None
    if not isinstance(expected_sha, str) or SHA.fullmatch(expected_sha) is None:
        raise BrowserRangeError("browser metadata policy SHA-256 is invalid")
    try:
        raw = path.read_bytes()
        policy = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise BrowserRangeError("browser metadata policy cannot be read") from exc
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise BrowserRangeError("browser metadata policy bytes differ from independent SHA-256")
    if (not isinstance(policy, dict) or not POLICY_KEYS.issubset(policy)
            or set(policy) - POLICY_KEYS - DOCUMENTARY_KEYS):
        raise BrowserRangeError("browser metadata policy has unsupported fields")
    if (type(policy["schema_version"]) is not int or policy["schema_version"] != 1
            or policy["kind"] != "grwl_parquet_footer_range"
            or dataset_id != "grwl-raw" or policy["dataset_id"] != dataset_id
            or policy["case_id"] != "grwl-raw-mississippi-z7"
            or type(policy["max_requests_per_case"]) is not int or policy["max_requests_per_case"] != 1
            or policy["plan_sha256"] != plan_sha
            or policy["browser_controls_sha256"] != controls_sha):
        raise BrowserRangeError("browser metadata policy identity differs from frozen controls")
    url = policy["object_url"]
    if not isinstance(url, str):
        raise BrowserRangeError("browser metadata policy object URL is invalid")
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.netloc != "data.source.coop"
            or not parsed.path.startswith("/nthh/grwl-raw/")
            or not parsed.path.endswith(".parquet") or parsed.query or parsed.fragment
            or parsed.username or parsed.password):
        raise BrowserRangeError("browser metadata policy object URL is unsafe")
    asset = planned_assets.get(url)
    if (not isinstance(asset, dict) or not isinstance(asset.get("content_type"), str)
            or asset["content_type"].split(";")[0].strip().lower()
            != "application/vnd.apache.parquet"
            or policy["object_sha256"] != asset.get("sha256")
            or policy["object_size_bytes"] != asset.get("size_bytes")
            or not _integer(policy["object_size_bytes"])
            or not _integer(policy["footer_metadata_bytes"])
            or not isinstance(policy["range_sha256"], str)
            or SHA.fullmatch(policy["range_sha256"]) is None):
        raise BrowserRangeError("browser metadata policy differs from exact planned Parquet object")
    size = policy["object_size_bytes"]
    footer = policy["footer_metadata_bytes"]
    start, end, length = _closed_range(policy["range"], size)
    if (start < 4 or start != size - 8 - footer or end not in (size - 9, size - 1)
            or not ORDINARY_LIMIT < length <= FOOTER_LIMIT):
        raise BrowserRangeError("browser metadata policy is not the bounded Parquet footer")
    return policy


def validate_transport(evidence: dict, cases: list[dict], *, dataset_id: str,
                       plan_sha: str, controls_sha: str, planned_assets: dict,
                       evidence_path: Path, policy_path: Path | None = None,
                       policy_sha256: str | None = None) -> dict:
    """Validate reported HTTP metadata; only the footer digest has an independent pin."""
    policy = _policy(policy_path, policy_sha256, dataset_id=dataset_id,
                     plan_sha=plan_sha, controls_sha=controls_sha, planned_assets=planned_assets)
    declared_policy = evidence.get("metadata_range_policy_sha256")
    if declared_policy != policy_sha256:
        raise BrowserRangeError("browser evidence differs from independent metadata policy")
    if evidence.get("blocked_requests") or evidence.get("errors"):
        raise BrowserRangeError("browser report contains blocked requests or errors")
    if (evidence.get("transfer_ceiling_bytes_per_case") != CASE_LIMIT
            or evidence.get("transfer_ceiling_bytes_total") != TOTAL_LIMIT):
        raise BrowserRangeError("browser evidence transfer ceilings changed")
    ui_origin = evidence.get("ui_origin")
    if ui_origin is not None:
        if not isinstance(ui_origin, str):
            raise BrowserRangeError("browser UI origin is invalid")
        parsed = urlsplit(ui_origin)
        if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                or parsed.username or parsed.password):
            raise BrowserRangeError("browser UI origin is unsafe")
    allowed_cors = {"*", ui_origin} if ui_origin is not None else {"*"}
    total = 0
    request_count = 0
    oversized = 0
    for case in cases:
        if case.get("errors") or case.get("blocked_requests"):
            raise BrowserRangeError("browser case contains blocked requests or errors")
        requests = case.get("requests")
        if not isinstance(requests, list) or not requests:
            raise BrowserRangeError("browser case lacks requests")
        case_bytes = 0
        for item in requests:
            if not isinstance(item, dict) or item.get("status_check") != "passed":
                raise BrowserRangeError("browser request is not passed")
            url = item.get("url")
            asset = planned_assets.get(url) if isinstance(url, str) else None
            if not isinstance(asset, dict) or not _integer(asset.get("size_bytes")):
                raise BrowserRangeError("browser request is outside the exact product plan")
            start, end, length = _closed_range(item.get("range"), asset["size_bytes"])
            if (type(item.get("status")) is not int or item["status"] != 206
                    or item.get("content_range") !=
                    f"bytes {start}-{end}/{asset['size_bytes']}"
                    or not _integer(item.get("content_length")) or item["content_length"] != length
                    or not _integer(item.get("body_bytes")) or item["body_bytes"] != length
                    or item.get("planned_sha256") != asset.get("sha256")
                    or not isinstance(item.get("body_sha256"), str)
                    or SHA.fullmatch(item["body_sha256"]) is None):
                raise BrowserRangeError("browser range response differs from exact request and plan")
            media = item.get("content_type")
            exposed = item.get("expose_headers")
            if (not isinstance(media, str) or not isinstance(asset.get("content_type"), str)
                    or media.split(";")[0].strip().lower() != asset["content_type"].split(";")[0].strip().lower()
                    or item.get("cors") not in allowed_cors
                    or not isinstance(exposed, str)
                    or not ({"*", "content-range"} & {part.strip().lower() for part in exposed.split(",")})):
                raise BrowserRangeError("browser range response lacks planned MIME or usable CORS")
            marker = item.get("metadata_range_exception")
            if length > ORDINARY_LIMIT:
                oversized += 1
                if (policy is None or case.get("id") != policy["case_id"]
                        or url != policy["object_url"] or item["range"] != policy["range"]
                        or length > FOOTER_LIMIT or item["body_sha256"] != policy["range_sha256"]
                        or marker != {"kind": "parquet_footer", "range_sha256": policy["range_sha256"]}):
                    raise BrowserRangeError("browser oversized range is outside frozen footer allowance")
            elif marker is not None:
                raise BrowserRangeError("browser request declares an unearned footer exception")
            case_bytes += length
            request_count += 1
        if (case_bytes > CASE_LIMIT or not _integer(case.get("transferred_bytes"))
                or case["transferred_bytes"] != case_bytes):
            raise BrowserRangeError("browser case transfer total differs or exceeds ceiling")
        total += case_bytes
    if policy is not None:
        if oversized != 1:
            raise BrowserRangeError("browser footer exception must occur exactly once")
        target = next(case for case in cases if case.get("id") == policy["case_id"])
        if (target.get("attribute_note") != "All source attributes for this ID."
                or target.get("source_attribute_count") != 14
                or not _integer(target.get("analytic_feature_id"))
                or target["analytic_feature_id"] != (target.get("width_sample") or {}).get("feature_id")):
            raise BrowserRangeError("GRWL footer case lacks fourteen attributes or exact ID equality")
    declared_total = evidence.get("total_transferred_bytes")
    if not _integer(declared_total) or declared_total > TOTAL_LIMIT:
        raise BrowserRangeError("browser aggregate transfer total is invalid")
    all_cases = evidence.get("cases")
    if (not isinstance(all_cases, list) or any(not _integer(c.get("transferred_bytes")) for c in all_cases
            if isinstance(c, dict)) or any(not isinstance(c, dict) for c in all_cases)
            or sum(c["transferred_bytes"] for c in all_cases) != declared_total
            or total > declared_total):
        raise BrowserRangeError("browser aggregate transfer total differs from cases")
    if evidence.get("selected_dataset_id") == dataset_id and total != declared_total:
        raise BrowserRangeError("single-product browser transfer total differs")
    return {"evidence_path": str(evidence_path),
            "evidence_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
            "metadata_policy_path": str(policy_path) if policy_path else None,
            "metadata_policy_sha256": policy_sha256,
            "requests_checked": request_count, "selected_case_bytes": total,
            "footer_exceptions_checked": oversized,
            "scope": "Browser report fields checked against independent plan/policy; response bytes are not re-fetched here."}
