"""llama-radio: Live Music Archive -> automated radio station pipeline."""

try:
    # Written by packaging/build.py at freeze time; absent in dev checkouts.
    from llama._version import __version__
except ImportError:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _pkg_version

    try:
        __version__ = _pkg_version("llama-radio")
    except PackageNotFoundError:  # not installed (raw checkout, no metadata)
        __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
