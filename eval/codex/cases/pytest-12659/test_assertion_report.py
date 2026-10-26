import unittest

from assertion_report import render_assertion_diff


class AssertionReportTests(unittest.TestCase):
    def test_importlib_mode_keeps_diff_for_tests_inside_a_package(self):
        report = render_assertion_diff(
            "four lights", "five lights", import_mode="importlib", package_test=True
        )
        self.assertIn("five lights", report)
        self.assertIn("four lights", report)

    def test_non_package_assertions_keep_their_diff(self):
        report = render_assertion_diff(
            "four lights", "five lights", import_mode="importlib", package_test=False
        )
        self.assertIn("AssertionError: assert", report)


if __name__ == "__main__":
    unittest.main()
