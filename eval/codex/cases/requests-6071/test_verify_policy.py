import unittest

from verify_policy import DEFAULT_CA_BUNDLE, resolve_ca_bundle


class VerifyPolicyTests(unittest.TestCase):
    def test_unset_uses_system_default(self):
        self.assertEqual(resolve_ca_bundle({}), DEFAULT_CA_BUNDLE)

    def test_empty_curl_bundle_uses_system_default(self):
        self.assertEqual(resolve_ca_bundle({"CURL_CA_BUNDLE": ""}), DEFAULT_CA_BUNDLE)

    def test_nonempty_curl_bundle_uses_configured_path(self):
        self.assertEqual(
            resolve_ca_bundle({"CURL_CA_BUNDLE": "certs/private-ca.pem"}),
            "certs/private-ca.pem",
        )


if __name__ == "__main__":
    unittest.main()
