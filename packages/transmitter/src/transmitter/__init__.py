"""transmitter: plans, renders and publishes the station's HLS stream."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("llama-transmitter")
except PackageNotFoundError:  # raw checkout, no metadata
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
