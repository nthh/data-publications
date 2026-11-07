"""Behavioral checks for evidence integrity, identity joins and generated backlog."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

import yaml
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import candidate_discovery as cd


class CandidateDiscoveryChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / "research/review.json"
        self.path.parent.mkdir()
        self.path.write_text(json.dumps({"candidates": [{"suggested_id": "demo"}]}))
        self.record = {
            "schema_version": 1, "id": "demo", "title": "Demo",
            "intake": {"kind": "official_catalog", "reference_url": "https://example.org/demo", "added_on": "2026-10-31"},
            "triage": {"decision": "pending", "priority": "normal"},
            "discovery": {
                "batch": "global-candidates-20261031", "reviewed_on": "2026-10-31",
                "geographic_scope": "global", "spatial_coverage": "Global land.",
                "sources": [{"provider": "planetary_computer", "entry_id": "demo", "url": "https://planetarycomputer.microsoft.com/api/stac/v1/collections/demo", "relationship": "exact_dataset"}],
                "access": [{"provider": "planetary_computer", "status": "native_available", "formats": ["COG"],
                            "summary": "Metadata only; bytes not checked.", "license_summary": "Unreviewed",
                            "proposed_outputs": [], "rationale": "Review existing native host before conversion.",
                            "evidence_urls": ["https://example.org/demo"]}],
                "citations": [], "evidence": [{"path": "research/review.json", "sha256": self.digest(), "key": "demo"}],
            },
        }
        self.schema = Draft202012Validator(json.loads((ROOT / "schemas/dataset.schema.json").read_text()), format_checker=FormatChecker())

    def tearDown(self):
        self.temp.cleanup()

    def digest(self):
        return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def test_schema_and_pinned_observation_pass_without_promoting_status(self):
        self.schema.validate(self.record)
        records = {"demo": self.record}
        cd.validate_discovery(self.root, records)
        row = cd.rows(records)[0]
        self.assertEqual(row["decision"], "pending")
        self.assertEqual(row["publication_status"], "candidate")
        self.assertEqual(row["access_review"], "native format listed")

    def test_changed_or_missing_observation_key_is_rejected(self):
        self.path.write_text(json.dumps({"candidates": [{"suggested_id": "other"}]}))
        with self.assertRaisesRegex(ValueError, "checksum changed"):
            cd.validate_discovery(self.root, {"demo": self.record})
        self.record["discovery"]["evidence"][0]["sha256"] = self.digest()
        with self.assertRaisesRegex(ValueError, "Unknown discovery evidence key"):
            cd.validate_discovery(self.root, {"demo": self.record})

    def test_unsafe_or_symlink_evidence_refuses(self):
        ref = self.record["discovery"]["evidence"][0]
        ref["path"] = "../outside.json"
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            cd.validate_discovery(self.root, {"demo": self.record})
        link = self.path.with_name("link.json")
        link.symlink_to(self.path)
        ref["path"] = "research/link.json"
        with self.assertRaisesRegex(ValueError, "symlink"):
            cd.validate_discovery(self.root, {"demo": self.record})

    def test_same_paper_never_merges_dataset_records(self):
        second = copy.deepcopy(self.record)
        second["id"] = "different-product"
        second["discovery"]["sources"][0]["entry_id"] = "different-product"
        citation = {"provider": "OpenAlex", "paper_doi": "10.1/example", "work_id": "https://openalex.org/W123",
                    "cited_by_count": 25, "observed_on": "2026-10-30", "scope": "base_dataset_family"}
        self.record["discovery"]["citations"] = [citation]
        second["discovery"]["citations"] = [copy.deepcopy(citation)]
        records = {"demo": self.record, "different-product": second}
        cd.validate_discovery(self.root, records)
        self.assertEqual(len(cd.rows(records)), 2)
        self.assertEqual([r["paper_citations"] for r in cd.rows(records)], [25, 25])

    def test_duplicate_source_and_conflicting_exact_identity_are_rejected(self):
        source = self.record["discovery"]["sources"][0]
        self.record["discovery"]["sources"].append(copy.deepcopy(source))
        with self.assertRaisesRegex(ValueError, "Duplicate discovery catalog entry"):
            cd.validate_discovery(self.root, {"demo": self.record})
        self.record["discovery"]["sources"].pop()
        second = copy.deepcopy(self.record)
        second["id"] = "other"
        with self.assertRaisesRegex(ValueError, "assigned to two records"):
            cd.validate_discovery(self.root, {"demo": self.record, "other": second})

    def test_invalid_scope_access_and_url_fail_schema(self):
        for field, value in (("geographic_scope", "worldwide-maybe"), ("reviewed_on", "2026-14-70")):
            broken = copy.deepcopy(self.record)
            broken["discovery"][field] = value
            with self.assertRaises(ValidationError):
                self.schema.validate(broken)
        broken = copy.deepcopy(self.record)
        broken["discovery"]["access"][0]["status"] = "verified_and_published"
        with self.assertRaises(ValidationError):
            self.schema.validate(broken)
        broken = copy.deepcopy(self.record)
        broken["discovery"]["sources"][0]["url"] = "file:///private/data"
        with self.assertRaises(ValidationError):
            self.schema.validate(broken)

    def test_unknown_count_is_not_zero_and_regional_records_are_excluded(self):
        zero = copy.deepcopy(self.record)
        zero["id"] = "zero"
        zero["discovery"]["citations"] = [{"provider": "OpenAlex", "paper_doi": None, "work_id": "https://openalex.org/W1", "cited_by_count": 0, "observed_on": "2026-10-30", "scope": "dataset_paper"}]
        regional = copy.deepcopy(self.record)
        regional["id"] = "regional"
        regional["discovery"]["geographic_scope"] = "regional"
        rows = cd.rows({"demo": self.record, "zero": zero, "regional": regional})
        self.assertEqual([row["id"] for row in rows], ["zero", "demo"])
        self.assertEqual([row["paper_citations"] for row in rows], [0, None])

    def test_provider_url_mismatch_is_rejected(self):
        self.record["discovery"]["sources"][0]["url"] = "https://unrelated.example/demo"
        with self.assertRaisesRegex(ValueError, "provider URL mismatch"):
            cd.validate_discovery(self.root, {"demo": self.record})

    def test_citation_dates_stay_separate_and_conflicts_fail(self):
        base = {"provider": "OpenAlex", "paper_doi": None, "work_id": "https://openalex.org/W1", "cited_by_count": 20,
                "observed_on": "2026-10-29", "scope": "dataset_paper"}
        newer = {**base, "cited_by_count": 18, "observed_on": "2026-10-30"}
        self.record["discovery"]["citations"] = [base, newer]
        cd.validate_discovery(self.root, {"demo": self.record})
        self.assertEqual(cd.citation_summary(self.record)[:2], (18, "2026-10-30"))
        self.record["discovery"]["citations"].append({**newer, "cited_by_count": 23})
        with self.assertRaisesRegex(ValueError, "Conflicting citation counts"):
            cd.validate_discovery(self.root, {"demo": self.record})

    def test_metadata_capture_redacts_signed_urls_before_retention(self):
        path = ROOT / "research/global-candidates-20261031/planetary/capture.py"
        spec = importlib.util.spec_from_file_location("pc_capture_test", path)
        capture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(capture)
        original = {"assets": [{"href": "https://example.org/image?se=2099&sig=demo"}],
                    "public": "https://example.org/search?limit=2"}
        clean, redactions = capture.redact_url_credentials(original)
        self.assertEqual(clean["assets"][0]["href"], "https://example.org/image")
        self.assertEqual(clean["public"], original["public"])
        self.assertEqual(redactions[0]["json_path"], ["assets", 0, "href"])
        self.assertNotIn("demo", json.dumps(clean))
        self.assertIn("sig=demo", original["assets"][0]["href"])

    def test_metadata_capture_refuses_existing_output_before_network(self):
        script = ROOT / "research/global-candidates-20261031/planetary/capture.py"
        result = subprocess.run([sys.executable, str(script), "--fetch", "--output-dir", str(self.root)],
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn("no requests made", result.stderr)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["research"])

    def test_views_are_deterministic_and_drift_is_detected(self):
        records = {"demo": self.record}
        self.record["title"] = "Untrusted | [link](https://wrong.example) <script>"
        expected = cd.render_views(records)
        self.assertEqual(expected, cd.render_views(records))
        self.assertNotIn("<script>", expected["CANDIDATES.md"])
        self.assertNotIn("[link](https://wrong.example)", expected["CANDIDATES.md"])
        for name, contents in expected.items():
            (self.root / name).write_text(contents)
        cd.check_views(self.root, records)
        (self.root / "candidates.csv").write_text("stale")
        with self.assertRaisesRegex(ValueError, "stale"):
            cd.check_views(self.root, records)


if __name__ == "__main__":
    unittest.main()
