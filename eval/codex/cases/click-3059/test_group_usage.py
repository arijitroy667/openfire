import unittest

from group_usage import group_usage


class GroupUsageTests(unittest.TestCase):
    def test_command_is_optional_when_group_invokes_without_a_subcommand(self):
        self.assertEqual(
            group_usage("app", has_commands=True, invoke_without_command=True),
            "Usage: app [OPTIONS] [COMMAND] [ARGS]...",
        )

    def test_command_remains_required_for_normal_groups(self):
        self.assertEqual(
            group_usage("app", has_commands=True, invoke_without_command=False),
            "Usage: app [OPTIONS] COMMAND [ARGS]...",
        )


if __name__ == "__main__":
    unittest.main()
