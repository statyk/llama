"""Package IO: read/validate one delivered llama package, and atomically
rewrite the two manifest blocks emcee owns.

A package is a directory llama's `deliver` command wrote: `manifest.json`
(schema_version >= 3), `briefing.md`/`briefing.json`, and an `audio/` dir of
packaged tracks. Everything in a package except the `dj_notes`/`dj_audio`
manifest blocks (and the `dj-audio/`, `dj-notes.md`, `broadcast.m3u` files
emcee itself adds) is llama-owned and read-only from here.
"""

import json
from pathlib import Path

from emcee.errors import EmceeError
from emcee.models import DJAudioBlock, ScriptNotes
from emcee.workspace import atomic_write_text

MIN_SUPPORTED_SCHEMA_VERSION = 3


class UnsupportedPackage(EmceeError):
    """The package's manifest predates emcee's v3 contract (missing
    `briefing`/`dj_notes`/`dj_audio` blocks) -- station.scan reports these as
    `unsupported` and never modifies them; the fix is re-delivering from
    llama, not upgrading the manifest in place."""


class Package:
    """Wraps one delivered package directory. Construction never touches the
    filesystem -- callers that need validation call `manifest()`."""

    def __init__(self, dir: Path):
        self.dir = Path(dir)
        self.manifest_path = self.dir / "manifest.json"

    def _read_json(self, path: Path, *, what: str) -> dict:
        if not path.exists():
            raise EmceeError(f"{what} not found: {path}")
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise EmceeError(f"{what} is not valid JSON: {path}") from exc

    def manifest(self) -> dict:
        """The raw manifest dict, after validating `schema_version >= 3`.
        Raises `UnsupportedPackage` for an older manifest, `EmceeError` if
        the file is missing or unreadable."""
        data = self._read_json(self.manifest_path, what="manifest.json")
        version = data.get("schema_version", 0)
        if version < MIN_SUPPORTED_SCHEMA_VERSION:
            raise UnsupportedPackage(
                f"unsupported (v{version} — re-deliver from llama): {self.dir}"
            )
        return data

    def briefing(self) -> dict:
        return self._read_json(self.dir / "briefing.json", what="briefing.json")

    def briefing_md(self) -> str:
        path = self.dir / "briefing.md"
        if not path.exists():
            raise EmceeError(f"briefing.md not found: {path}")
        return path.read_text()


def rewrite_manifest(
    pkg: Package, *, dj_notes: ScriptNotes | None, dj_audio: DJAudioBlock | None
) -> None:
    """Set exactly the `dj_notes`/`dj_audio` blocks on the manifest, leaving
    every other key -- including the briefing block's `"json"` wire alias --
    byte-for-byte untouched.

    Reads the manifest as a raw dict rather than round-tripping it through a
    pydantic model: emcee has no `Manifest` model (it never owns the whole
    document, only these two blocks), and modeling the full manifest just for
    this write would risk renaming/dropping the `briefing.json_file` alias on
    the way back out. Operating on the dict directly is the only way to
    guarantee additivity.
    """
    data = json.loads(pkg.manifest_path.read_text())
    data["dj_notes"] = dj_notes.model_dump() if dj_notes is not None else None
    data["dj_audio"] = dj_audio.model_dump() if dj_audio is not None else None
    atomic_write(pkg.manifest_path, json.dumps(data, indent=2) + "\n")


# Alias, not a reimplementation: package_io has no atomic-write logic of its
# own -- see workspace.py's module docstring for why the unique-temp +
# os.replace pattern must not be duplicated.
atomic_write = atomic_write_text
