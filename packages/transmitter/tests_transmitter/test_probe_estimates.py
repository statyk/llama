"""scripts/probe_estimates.py --time-one says why a package is not eligible."""

import importlib.util
from pathlib import Path

from tests_transmitter.helpers import build_package, make_root

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "probe_estimates.py"


def _load():
    spec = importlib.util.spec_from_file_location("probe_estimates", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cfg(tmp_path, root, quiet=30.0):
    path = tmp_path / "config.toml"
    path.write_text(f'root = "{tmp_path / "tx"}"\n[station]\nroot = "{root}"\nquiet_minutes = {quiet}\n')
    return path


def test_time_one_prints_the_reasons_for_a_package_in_its_quiet_period(tmp_path, capsys):
    root = make_root(tmp_path)
    build_package(root, "fresh-2005-11-01", age_s=10.0)
    rc = _load().main(["--config", str(_cfg(tmp_path, root)), "--time-one", "fresh-2005-11-01"])
    err = capsys.readouterr().err
    assert rc == 1 and "not eligible" in err and "fresh-2005-11-01" in err and "quiet" in err.lower()


def test_time_one_says_not_found_for_a_slug_outside_the_root(tmp_path, capsys):
    root = make_root(tmp_path)
    build_package(root, "band-2005-11-01")
    rc = _load().main(["--config", str(_cfg(tmp_path, root)), "--time-one", "nope-1999-01-01"])
    assert rc == 1 and "not found" in capsys.readouterr().err
