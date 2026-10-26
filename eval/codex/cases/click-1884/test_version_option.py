import unittest

from version_option import detected_version


class VersionOptionTests(unittest.TestCase):
    def test_default_version_detection_uses_installed_command_distribution(self):
        self.assertEqual(detected_version("cli"), "0.1.0")

    def test_explicit_distribution_name_is_honored(self):
        self.assertEqual(detected_version("cli", "click-issue-test"), "0.1.0")


if __name__ == "__main__":
    unittest.main()
