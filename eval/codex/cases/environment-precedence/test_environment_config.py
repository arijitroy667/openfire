import unittest

from environment_config import resolve


class EnvironmentConfigTests(unittest.TestCase):
    def test_explicitly_empty_process_value_wins_over_dotenv(self):
        self.assertEqual(resolve("MODE", {"MODE": ""}, {"MODE": "production"}, {}), "")

    def test_absent_process_value_falls_back_to_dotenv(self):
        self.assertEqual(resolve("MODE", {}, {"MODE": "production"}, {}), "production")


if __name__ == "__main__":
    unittest.main()
