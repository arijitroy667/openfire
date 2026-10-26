import unittest

from cache_validation import is_not_modified


class CacheValidationTests(unittest.TestCase):
    def test_deleted_file_cannot_be_not_modified(self):
        self.assertFalse(is_not_modified(False, 20, 20))

    def test_existing_unchanged_file_can_be_not_modified(self):
        self.assertTrue(is_not_modified(True, 20, 20))


if __name__ == "__main__":
    unittest.main()
