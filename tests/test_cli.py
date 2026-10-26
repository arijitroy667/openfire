from typer.testing import CliRunner

from engbrain import __version__
from engbrain.cli import app


def test_version_option_works_without_a_subcommand():
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == f"EngBrain {__version__}"


def test_invoking_without_a_command_shows_help():
    result = CliRunner().invoke(app, [])

    assert result.exit_code == 0
    assert "Usage:" in result.stdout
