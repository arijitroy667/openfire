import unittest

from version_constraints import RUNTIME_MAX_URLLIB3, SETUP_MAX_URLLIB3, runtime_accepts


class VersionConstraintTests(unittest.TestCase):
    def test_runtime_accepts_the_version_allowed_by_install_metadata(self):
        self.assertTrue(runtime_accepts((1, 23)))

    def test_runtime_and_install_bounds_agree(self):
        self.assertEqual(RUNTIME_MAX_URLLIB3, SETUP_MAX_URLLIB3)


if __name__ == "__main__":
    unittest.main()
