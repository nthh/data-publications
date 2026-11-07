import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import source_products


class HistoricalWorkflowMimeTests(unittest.TestCase):
    def test_known_historical_baseline_native_checker_is_binary(self):
        self.assertEqual(
            source_products.content_type('reports/baseline-r2/workflow/native-oracle/detail-oracle'),
            'application/octet-stream',
        )
        self.assertEqual(
            source_products.content_type('reports/baseline-r1/workflow/native-oracle/detail-oracle'),
            'application/octet-stream',
        )

    def test_existing_direct_native_checker_support_is_preserved(self):
        self.assertEqual(
            source_products.content_type('workflow/native-oracle/detail-oracle'),
            'application/octet-stream',
        )

    def test_historical_checker_source_keeps_extension_mime(self):
        self.assertEqual(
            source_products.content_type('reports/baseline-r2/workflow/native-oracle/checker.cpp'),
            'text/plain',
        )

    def test_arbitrary_extensionless_paths_remain_rejected(self):
        for path in (
            'assets/detail-oracle',
            'workflow/other/detail-oracle',
            'reports/other/workflow/native-oracle/detail-oracle',
            'reports/baseline-rx/workflow/native-oracle/detail-oracle',
            'reports/baseline-r2/workflow/native-oracle/nested/detail-oracle',
            'reports/baseline-r2/native-oracle/detail-oracle',
        ):
            with self.subTest(path=path), self.assertRaises(source_products.ProductError):
                source_products.content_type(path)

    def test_path_traversal_and_windows_separators_are_rejected(self):
        for path in (
            'reports/baseline-r2/workflow/native-oracle/../native-oracle/detail-oracle',
            '../reports/baseline-r2/workflow/native-oracle/detail-oracle',
            r'reports\baseline-r2\workflow\native-oracle\detail-oracle',
            'C:/reports/baseline-r2/workflow/native-oracle/detail-oracle',
            'reports//baseline-r2/workflow/native-oracle/detail-oracle',
            'reports/./baseline-r2/workflow/native-oracle/detail-oracle',
            'reports/baseline-r2/workflow/native-oracle/.hidden-checker',
        ):
            with self.subTest(path=path), self.assertRaises(source_products.ProductError):
                source_products.content_type(path)


if __name__ == '__main__':
    unittest.main()
