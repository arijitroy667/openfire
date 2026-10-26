import unittest

from sqlite_options import connection_options


class SqliteOptionsTests(unittest.TestCase):
    def test_connection_uses_bounded_busy_timeout(self):
        self.assertEqual(connection_options()["timeout"], 5.0)


if __name__ == "__main__":
    unittest.main()
