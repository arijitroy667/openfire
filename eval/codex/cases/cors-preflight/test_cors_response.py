import unittest

from cors_response import preflight_status


class CorsResponseTests(unittest.TestCase):
    def test_preflight_status_does_not_inherit_missing_resource_status(self):
        self.assertEqual(preflight_status(404), 204)

    def test_preflight_status_does_not_inherit_server_error(self):
        self.assertEqual(preflight_status(503), 204)


if __name__ == "__main__":
    unittest.main()
