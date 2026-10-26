import unittest

from pool_config import can_serve_workers


class PoolConfigTests(unittest.TestCase):
    def test_pool_serves_four_concurrent_workers(self):
        self.assertTrue(can_serve_workers(4))


if __name__ == "__main__":
    unittest.main()
