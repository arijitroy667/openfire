import unittest
from datetime import datetime, timedelta, timezone

from timestamp_utils import normalize_utc


class TimestampUtilsTests(unittest.TestCase):
    def test_naive_timestamp_uses_utc_convention(self):
        self.assertEqual(normalize_utc(datetime(2024, 1, 1)), "2024-01-01T00:00:00+00:00")

    def test_aware_timestamp_is_converted_to_utc(self):
        value = datetime(2024, 1, 1, 5, tzinfo=timezone(timedelta(hours=5)))
        self.assertEqual(normalize_utc(value), "2024-01-01T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
