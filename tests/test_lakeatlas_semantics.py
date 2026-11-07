"""Focused acceptance tests for the versioned LakeATLAS semantics sidecar."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIDECAR = ROOT / "datasets/lakeatlas/metadata-enhancements/v1/field-semantics.json"
BUILDER = ROOT / "datasets/lakeatlas/metadata-enhancements/v1/build_semantics.py"
spec = importlib.util.spec_from_file_location("lakeatlas_semantics_builder", BUILDER)
builder = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(builder)


class LakeAtlasSemanticsTests(unittest.TestCase):
    def load_sidecar(self):
        return json.loads(SIDECAR.read_text())

    def test_every_source_field_has_semantics_and_evidence(self):
        doc = self.load_sidecar()
        self.assertEqual(doc["enhancement_version"], "v1")
        self.assertEqual(doc["package_manifest_sha256"], builder.PACKAGE_MANIFEST_HASH)
        self.assertEqual(
            {key: value["sha256"] for key, value in doc["bound_assets"].items()},
            builder.PACKAGE_ASSET_HASHES,
        )
        self.assertEqual(builder.validate(doc), [])

        for asset_id, asset in doc["assets"].items():
            with self.subTest(asset=asset_id):
                fields = asset["fields"]
                producer_fields = {
                    name: field for name, field in fields.items()
                    if field["semantics_status"] != "not_a_producer_attribute"
                }
                self.assertEqual(len(fields), asset["field_count"])
                self.assertEqual(len(producer_fields), 305)
                self.assertTrue(all(field["producer_attribute"] for field in producer_fields.values()))
                self.assertTrue(all(field["definition"] and field["units_as_published"] and field["aggregation_or_summary"] for field in producer_fields.values()))
                self.assertTrue(all(field["evidence"] and field["evidence"].get("page") for field in producer_fields.values()))

                catalog_fields = [field for field in producer_fields.values() if field["license_status"] == "explicit_attribute_license_in_catalog"]
                inherited_fields = [field for field in producer_fields.values() if field["license_status"] == "explicit_inherited_HydroLAKES_source_product_license"]
                self.assertEqual(len(catalog_fields), 281)
                self.assertEqual(len(inherited_fields), 24)
                self.assertTrue(all(field["hydroatlas_license_as_published"] in {"Creative Commons CC-BY 4.0", "Open Data Commons Open Database License (ODbL v1.0)"} for field in catalog_fields))
                self.assertTrue(all(field["license_as_published"] == builder.HYDROLAKES_LICENSE and field["hydroatlas_license_as_published"] is None for field in inherited_fields))
                self.assertTrue(all(field["license_scope"].startswith("HydroLAKES v1 source product") for field in inherited_fields))
                self.assertTrue(all(field["license_evidence"][0]["printed_page"] == 14 for field in inherited_fields))
                self.assertTrue(all(field["license_evidence"][0]["sha256"] == builder.HYDROLAKES_TECHDOC_SHA256 for field in inherited_fields))
                self.assertTrue(all("not freshly fetched or rehashed" in field["license_evidence"][0]["sha256_basis"] for field in inherited_fields))
                self.assertTrue(all(field["semantics_status"] == "documented" for field in producer_fields.values()))

                # Check producer values, scaling, aggregation, and license notices.
                scaled = fields["lka_pc_vse"]
                self.assertEqual(scaled["units_as_published"], "percent cover (x10)")
                self.assertIn("value 10 means 1%", scaled["producer_notes"])
                self.assertEqual(scaled["hydroatlas_license_as_published"], "Creative Commons CC-BY 4.0")

                summed = fields["pop_ct_vsu"]
                self.assertIn("{su} sum", summed["dimension_semantics"])
                self.assertEqual(summed["units_as_published"], "count (thousands)")
                self.assertIn("1 represents 1000", summed["producer_notes"])
                self.assertEqual(summed["hydroatlas_license_as_published"], "Creative Commons CC-BY 4.0")

                lake_type = fields["Lake_type"]
                self.assertIn("1 lake, 2 reservoir, 3 lake control", lake_type["definition"])
                self.assertEqual(lake_type["license_as_published"], builder.HYDROLAKES_LICENSE)
                self.assertTrue(lake_type["source_producer_field"])

        polygon_fields = doc["assets"]["lakeatlas-polygons"]["fields"]
        for name in ("OBJECTID", "Shape_Length", "Shape_Area"):
            with self.subTest(field=name):
                self.assertEqual(polygon_fields[name]["semantics_status"], "not_a_producer_attribute")
                self.assertEqual(polygon_fields[name]["field_origin"], "source_geodatabase_default")
                self.assertFalse(polygon_fields[name]["source_producer_field"])
                self.assertEqual(polygon_fields[name]["evidence"]["page"], 15)
        self.assertEqual(polygon_fields["geometry"]["field_origin"], "GeoParquet_geometry_encoding")
        self.assertEqual(polygon_fields["bbox"]["field_origin"], "package_derived_bbox_metadata")

    def test_missing_coverage_fails(self):
        doc = self.load_sidecar()
        doc["assets"]["lakeatlas-polygons"]["field_count"] += 1
        self.assertTrue(any("duplicate or missing fields" in error for error in builder.validate(doc)))

    def test_unresolved_required_semantics_fails(self):
        doc = self.load_sidecar()
        doc["assets"]["lakeatlas-polygons"]["fields"]["Lake_area"]["semantics_status"] = "unresolved"
        errors = builder.validate(doc)
        self.assertTrue(any("Lake_area: unresolved producer field" in error for error in errors))

    def test_incomplete_producer_documentation_fails_strict_validation(self):
        doc = self.load_sidecar()
        doc["assets"]["lakeatlas-polygons"]["fields"]["Lake_area"]["semantics_status"] = "incomplete_producer_documentation"
        errors = builder.validate(doc)
        self.assertTrue(any("Lake_area: incomplete producer documentation" in error for error in errors))

    def test_mismatched_asset_binding_fails(self):
        manifest = {
            "assets": [
                {"asset_id": asset_id, "sha256": digest}
                for asset_id, digest in builder.PACKAGE_ASSET_HASHES.items()
            ]
        }
        manifest["assets"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "manifest does not bind expected asset"):
            builder.verify_manifest_bindings(manifest, builder.PACKAGE_MANIFEST_HASH)

    def test_dangling_output_symlink_is_refused(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "dangling.json"
            output.symlink_to(Path(temp_dir) / "missing.json")
            with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
                builder.ensure_new_output_path(output)


if __name__ == "__main__":
    unittest.main()
