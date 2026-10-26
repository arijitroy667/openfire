import unittest

from queue_worker import process


class QueueWorkerTests(unittest.TestCase):
    def test_failed_persistence_does_not_acknowledge_the_message(self):
        acknowledged = []

        def fail_persist(_payload):
            raise OSError("disk unavailable")

        with self.assertRaises(OSError):
            process("work-item", fail_persist, acknowledged.append)

        self.assertEqual(acknowledged, [])


if __name__ == "__main__":
    unittest.main()
