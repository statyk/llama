from importlib.metadata import version as pkg_version

from typer.testing import CliRunner

import llama
from llama.cli import app

runner = CliRunner()


def test_version_resolves_from_installed_metadata():
    # Editable dev install exposes the dist as "llama-radio"; the resolver must
    # find it and must NOT fall through to the unknown sentinel.
    assert llama.__version__ == pkg_version("llama-radio")
    assert llama.__version__ != "0.0.0+unknown"


def test_version_flag_prints_version_and_exits():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == llama.__version__
