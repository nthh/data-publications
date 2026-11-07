"""Bounded browser attestation and independently frozen Parquet footer policy."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[1] / "scripts/source_publish/browser_range_evidence.py"
SPEC = importlib.util.spec_from_file_location("browser_range_evidence_test", MODULE)
assert SPEC and SPEC.loader
browser = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(browser)

URL = "https://data.source.coop/nthh/grwl-raw/releases/r1/assets/observations.parquet"
SIZE = 5_529_859_809
FOOTER = 19_783_655
START = SIZE - 8 - FOOTER
END = SIZE - 9
RANGE = f"bytes={START}-{END}"
RANGE_SHA = "b" * 64
OBJECT_SHA = "a" * 64
CONTROLS_SHA = "c" * 64
PLAN_SHA = "d" * 64


def fixture(tmp_path):
    asset = {"sha256": OBJECT_SHA, "size_bytes": SIZE,
             "content_type": "application/vnd.apache.parquet"}
    policy = {"schema_version": 1, "kind": "grwl_parquet_footer_range",
              "dataset_id": "grwl-raw", "case_id": "grwl-raw-mississippi-z7",
              "max_requests_per_case": 1, "plan_sha256": PLAN_SHA,
              "browser_controls_sha256": CONTROLS_SHA, "object_url": URL,
              "object_sha256": OBJECT_SHA, "object_size_bytes": SIZE,
              "footer_metadata_bytes": FOOTER, "range": RANGE, "range_sha256": RANGE_SHA}
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy))
    policy_sha = hashlib.sha256(policy_path.read_bytes()).hexdigest()
    request = {"url": URL, "status_check": "passed", "status": 206,
               "range": RANGE, "content_range": f"bytes {START}-{END}/{SIZE}",
               "content_length": FOOTER, "body_bytes": FOOTER,
               "body_sha256": RANGE_SHA, "planned_sha256": OBJECT_SHA,
               "content_type": "application/vnd.apache.parquet", "cors": "*",
               "expose_headers": "Content-Range, Content-Length",
               "metadata_range_exception": {"kind": "parquet_footer", "range_sha256": RANGE_SHA}}
    case = {"id": "grwl-raw-mississippi-z7", "dataset_id": "grwl-raw",
            "requests": [request], "transferred_bytes": FOOTER,
            "attribute_note": "All source attributes for this ID.",
            "source_attribute_count": 14, "analytic_feature_id": 123,
            "width_sample": {"feature_id": 123}}
    evidence = {"metadata_range_policy_sha256": policy_sha,
                "transfer_ceiling_bytes_per_case": 128 * browser.MIB,
                "transfer_ceiling_bytes_total": 1024 * browser.MIB,
                "selected_dataset_id": "grwl-raw", "cases": [case],
                "total_transferred_bytes": FOOTER, "ui_origin": "http://127.0.0.1:8918"}
    evidence_path = tmp_path / "browser.json"
    evidence_path.write_text(json.dumps(evidence))
    return policy, policy_path, policy_sha, asset, evidence, evidence_path


def check(tmp_path, mutate=None, *, with_policy=True):
    policy, path, digest, asset, evidence, evidence_path = fixture(tmp_path)
    if mutate:
        mutate(policy, asset, evidence)
        path.write_text(json.dumps(policy))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    evidence["metadata_range_policy_sha256"] = digest if with_policy else None
    evidence_path.write_text(json.dumps(evidence))
    return browser.validate_transport(evidence, evidence["cases"], dataset_id="grwl-raw",
        plan_sha=PLAN_SHA, controls_sha=CONTROLS_SHA, planned_assets={URL: asset},
        evidence_path=evidence_path, policy_path=path if with_policy else None,
        policy_sha256=digest if with_policy else None)


def test_exact_footer_policy_passes_without_allocating_footer_bytes(tmp_path):
    result = check(tmp_path)
    assert result["footer_exceptions_checked"] == 1
    assert result["selected_case_bytes"] == FOOTER
    assert result["metadata_policy_sha256"] == hashlib.sha256(
        (tmp_path / "policy.json").read_bytes()).hexdigest()


def test_current_frozen_policy_is_compatible():
    root = Path(__file__).resolve().parents[1]
    policy_path = root / "research/source-publication-20261107/grwl-footer-boundary-r1/footer-policy-r1.json"
    controls = root / "research/source-publication-20261106/browser-controls-r1.json"
    policy = json.loads(policy_path.read_text())
    planned = json.loads(controls.read_text())["objects"]
    actual = browser._policy(policy_path, hashlib.sha256(policy_path.read_bytes()).hexdigest(),
        dataset_id="grwl-raw", plan_sha=policy["plan_sha256"],
        controls_sha=hashlib.sha256(controls.read_bytes()).hexdigest(), planned_assets=planned)
    assert actual["range"] == "bytes=5510076146-5529859800"


@pytest.mark.parametrize("mutate", [
    lambda p, a, e: p.__setitem__("object_url", URL.replace("grwl-raw", "hydrolakes")),
    lambda p, a, e: p.__setitem__("case_id", "grwl-raw-mississippi-z8"),
    lambda p, a, e: p.__setitem__("range", f"bytes={START - 1}-{END}"),
    lambda p, a, e: p.__setitem__("range_sha256", "not-a-sha"),
    lambda p, a, e: p.__setitem__("footer_metadata_bytes", 33 * browser.MIB),
    lambda p, a, e: p.__setitem__("object_sha256", "e" * 64),
    lambda p, a, e: p.__setitem__("plan_sha256", "e" * 64),
    lambda p, a, e: p.__setitem__("browser_controls_sha256", "e" * 64),
    lambda p, a, e: p.__setitem__("max_requests_per_case", 2),
    lambda p, a, e: p.__setitem__("unapproved_override", True),
])
def test_policy_identity_and_size_refusals(tmp_path, mutate):
    with pytest.raises(browser.BrowserRangeError):
        check(tmp_path, mutate)


@pytest.mark.parametrize("mutate", [
    lambda p, a, e: e["cases"][0]["requests"][0].__setitem__("url", URL.replace("grwl-raw", "hydrolakes")),
    lambda p, a, e: e["cases"][0].__setitem__("id", "grwl-raw-amazon-z7"),
    lambda p, a, e: e["cases"][0]["requests"][0].__setitem__("range", f"bytes={START - 1}-{END}"),
    lambda p, a, e: e["cases"][0]["requests"][0].__setitem__("body_sha256", "f" * 64),
    lambda p, a, e: e["cases"][0]["requests"][0].__setitem__("body_bytes", FOOTER - 1),
    lambda p, a, e: e["cases"][0]["requests"][0].__setitem__("status", 200),
    lambda p, a, e: e["cases"][0]["requests"][0].__setitem__("cors", "https://elsewhere.example"),
    lambda p, a, e: e["cases"][0]["requests"][0].pop("body_bytes"),
    lambda p, a, e: e["cases"][0]["requests"][0].__setitem__("content_range", "bytes 0-1/2"),
    lambda p, a, e: e["cases"][0]["requests"][0].__setitem__("metadata_range_exception", {"kind": "parquet_footer", "range_sha256": "f" * 64}),
    lambda p, a, e: e["cases"][0].__setitem__("source_attribute_count", 3),
    lambda p, a, e: e["cases"][0].__setitem__("analytic_feature_id", 124),
    lambda p, a, e: e["cases"][0].__setitem__("blocked_requests", [{"reason": "blocked"}]),
    lambda p, a, e: e.__setitem__("errors", ["failed request"]),
    lambda p, a, e: e.__setitem__("total_transferred_bytes", FOOTER - 1),
])
def test_oversized_report_refusals(tmp_path, mutate):
    with pytest.raises(browser.BrowserRangeError):
        check(tmp_path, mutate)


def test_duplicate_footer_exception_is_refused(tmp_path):
    def duplicate(p, a, e):
        case = e["cases"][0]
        case["requests"].append(copy.deepcopy(case["requests"][0]))
        case["transferred_bytes"] *= 2
        e["total_transferred_bytes"] *= 2
    with pytest.raises(browser.BrowserRangeError, match="exactly once"):
        check(tmp_path, duplicate)


def test_exact_footer_larger_than_32_mib_is_refused(tmp_path):
    def oversized(p, a, e):
        length = 33 * browser.MIB
        start = SIZE - 8 - length
        interval = f"bytes={start}-{SIZE - 9}"
        p["footer_metadata_bytes"] = length
        p["range"] = interval
        request = e["cases"][0]["requests"][0]
        request["range"] = interval
        request["content_range"] = f"bytes {start}-{SIZE - 9}/{SIZE}"
        request["content_length"] = length
        request["body_bytes"] = length
        e["cases"][0]["transferred_bytes"] = length
        e["total_transferred_bytes"] = length
    with pytest.raises(browser.BrowserRangeError, match="bounded Parquet footer"):
        check(tmp_path, oversized)


def test_no_policy_rejects_large_request(tmp_path):
    def no_marker(p, a, e):
        e["cases"][0]["requests"][0].pop("metadata_range_exception")
    with pytest.raises(browser.BrowserRangeError, match="outside frozen footer allowance"):
        check(tmp_path, no_marker, with_policy=False)


def ordinary(p, a, e):
    request = e["cases"][0]["requests"][0]
    request.update({"range": "bytes=0-7", "content_range": f"bytes 0-7/{SIZE}",
                    "content_length": 8, "body_bytes": 8})
    request.pop("metadata_range_exception")
    e["cases"][0]["transferred_bytes"] = 8
    e["total_transferred_bytes"] = 8


def test_no_policy_accepts_bounded_ordinary_request(tmp_path):
    assert check(tmp_path, ordinary, with_policy=False)["footer_exceptions_checked"] == 0


@pytest.mark.parametrize("field,value", [
    ("body_bytes", None), ("body_bytes", True), ("body_bytes", 8.0),
    ("content_length", True), ("content_length", 8.0),
    ("status", True), ("status", 206.0),
])
def test_ordinary_request_rejects_missing_or_noninteger_fields(tmp_path, field, value):
    def bad(p, a, e):
        ordinary(p, a, e)
        if value is None:
            e["cases"][0]["requests"][0].pop(field)
        else:
            e["cases"][0]["requests"][0][field] = value
    with pytest.raises(browser.BrowserRangeError):
        check(tmp_path, bad, with_policy=False)


@pytest.mark.parametrize("value", [True, 8.0])
def test_ordinary_case_total_rejects_bool_or_float(tmp_path, value):
    def bad(p, a, e):
        ordinary(p, a, e)
        e["cases"][0]["transferred_bytes"] = value
    with pytest.raises(browser.BrowserRangeError):
        check(tmp_path, bad, with_policy=False)


def test_policy_file_sha_must_be_independent(tmp_path):
    policy, path, digest, asset, evidence, evidence_path = fixture(tmp_path)
    with pytest.raises(browser.BrowserRangeError, match="independent SHA-256"):
        browser.validate_transport(evidence, evidence["cases"], dataset_id="grwl-raw",
            plan_sha=PLAN_SHA, controls_sha=CONTROLS_SHA, planned_assets={URL: asset},
            evidence_path=evidence_path, policy_path=path, policy_sha256="0" * 64)
