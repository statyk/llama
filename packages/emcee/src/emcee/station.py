"""Station model: scan a delivered-packages folder (`[station] root`) for
emcee packages and compute each one's voice readiness (spec section 2).
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from emcee.artists import normalize_artist
from emcee.config import EmceeConfig
from emcee.moves import Moves
from emcee.package_io import Package, UnsupportedPackage


@dataclass
class PackageStatus:
    path: Path
    state: str  # "ready" | "pending" | "unsupported"
    reasons: list[str] = field(default_factory=list)
    profile: str | None = None  # manifest["source"]["profile"], when readable
    # Who voiced it: None = not voiced, "?" = voiced before emcee recorded the
    # presenter (legacy), "house" = house narrator, else the presenter id.
    voiced_by: str | None = None


def manifest_profile(manifest: object) -> str | None:
    """`manifest["source"]["profile"]` from a raw manifest dict; None for any
    shape that does not carry a string there. Never raises."""
    try:
        profile = manifest["source"]["profile"]  # type: ignore[index]
    except Exception:
        return None
    return profile if isinstance(profile, str) and profile else None


def manifest_voiced_by(manifest: object) -> str | None:
    """`voiced_by` from a raw manifest dict's `dj_audio` block (see
    `PackageStatus.voiced_by`). Never raises."""
    try:
        dj_audio = manifest["dj_audio"]  # type: ignore[index]
    except Exception:
        return None
    if not isinstance(dj_audio, dict):
        return None
    if "presenter" not in dj_audio:
        return "?"
    presenter = dj_audio["presenter"]
    return presenter if isinstance(presenter, str) and presenter else "house"


def raw_profile(manifest_path: Path) -> str | None:
    """Best-effort profile from the raw manifest JSON (for rows whose
    manifest could not be loaded normally). Never raises."""
    try:
        return manifest_profile(json.loads(Path(manifest_path).read_text()))
    except Exception:
        return None


ProfileSource = Literal["move", "artist", "llama"]


@dataclass(frozen=True)
class Effective:
    """Which profile a package is voiced as, and why (spec section 1).
    `rule` is the matching [assign.artists] key as written in config, for
    messages; None unless `source == "artist"`."""
    profile: str | None
    source: ProfileSource
    rule: str | None


def profile_label(profile: str | None) -> str:
    return profile if profile is not None else "(none)"


def _get(obj: object, *keys: str) -> object:
    """obj[k1][k2]... or None for any missing key or non-dict on the way."""
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _nonempty_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def manifest_performance_id(manifest: object) -> str | None:
    """`manifest["source"]["performance_id"]`, None for any other shape. Never raises."""
    return _nonempty_str(_get(manifest, "source", "performance_id"))


def manifest_artist(manifest: object) -> str | None:
    """`manifest["show"]["artist"]`, None for any other shape. Never raises."""
    return _nonempty_str(_get(manifest, "show", "artist"))


def manifest_voiced_source(manifest: object) -> str | None:
    """`dj_audio.profile_source` as recorded, else None. Never raises."""
    return _nonempty_str(_get(manifest, "dj_audio", "profile_source"))


def manifest_voiced_profile(manifest: object) -> str | None:
    """The profile a voiced package was voiced as: `dj_audio["profile"]` when
    the key is present, else llama's profile (a legacy block was voiced under
    llama's profile, since no rules or moves existed). Never raises."""
    dj_audio = _get(manifest, "dj_audio")
    if isinstance(dj_audio, dict) and "profile" in dj_audio:
        return _nonempty_str(dj_audio["profile"])
    return manifest_profile(manifest)


def manifest_tts(manifest: object) -> dict | None:
    """`dj_audio.tts` as recorded (a dict), else None. Never raises."""
    tts = _get(manifest, "dj_audio", "tts")
    return tts if isinstance(tts, dict) else None


def effective_profile(config: EmceeConfig, moves: Moves, manifest: object) -> Effective:
    """The profile a package is voiced as. First match wins:

    1. a move recorded for the manifest's `source.performance_id`;
    2. an [assign.artists] rule whose normalized key equals the normalized
       `show.artist`, and whose `from` (if any) contains llama's profile;
    3. llama's profile (`manifest_profile`, possibly None).

    Pure and total: never raises, whatever the manifest holds."""
    entry = moves.get(manifest_performance_id(manifest))
    if entry is not None:
        return Effective(entry["profile"], "move", None)
    llama = manifest_profile(manifest)
    artist = manifest_artist(manifest)
    if artist is not None:
        wanted = normalize_artist(artist)
        for key, rule in config.assign.artists.items():
            if normalize_artist(key) == wanted and (rule.from_ is None or llama in rule.from_):
                return Effective(rule.profile, "artist", key)
    return Effective(llama, "llama", None)


def target_problem(config: EmceeConfig, target: str | None, delivered: str | None) -> str | None:
    """Why a move to `target` cannot be voiced, or None. A move to the
    delivered profile is always valid; any other target needs an
    [assign.profiles.<target>] entry."""
    if target == delivered or (target is not None and target in config.assign.profiles):
        return None
    return f'move target "{profile_label(target)}" has no [assign.profiles] entry'


def move_target_problem(config: EmceeConfig, moves: Moves, manifest: object) -> str | None:
    """Use-time validation of this package's recorded move (spec section 3):
    None when there is no move or it is valid. Never raises."""
    entry = moves.get(manifest_performance_id(manifest))
    if entry is None:
        return None
    return target_problem(config, entry["profile"], manifest_profile(manifest))


def readiness(pkg: Package) -> tuple[bool, list[str]]:
    """(ok, reasons) over the four independent legs: script present, DJ audio
    present, broadcast.m3u present, every manifest track's audio file on
    disk. `reasons` names each failing leg (empty when ready). Callers must
    have already screened out unsupported (pre-v3) packages -- this assumes
    `pkg.manifest()` succeeds and will propagate `UnsupportedPackage`/
    `EmceeError` if it doesn't."""
    manifest = pkg.manifest()
    reasons: list[str] = []

    dj_notes = manifest.get("dj_notes")
    if dj_notes is None or not (pkg.dir / "dj-notes.md").exists():
        reasons.append("no DJ script (dj_notes block + dj-notes.md required)")

    dj_audio = manifest.get("dj_audio")
    if dj_audio is None:
        reasons.append("no DJ audio (unvoiced)")
    else:
        clips = [*dj_audio.get("set_intros", {}).values(), dj_audio.get("outro")]
        missing_clips = [c for c in clips if c and not (pkg.dir / c).exists()]
        if missing_clips:
            reasons.append(
                f"{len(missing_clips)} DJ audio clip(s) missing on disk: "
                + ", ".join(sorted(missing_clips))
            )

    if not (pkg.dir / "broadcast.m3u").exists():
        reasons.append("no broadcast.m3u")

    tracks = manifest.get("tracks", [])
    missing_tracks = [
        t["filename"]
        for t in tracks
        if not (pkg.dir / "audio" / t["filename"]).exists()
    ]
    if missing_tracks:
        reasons.append(
            f"{len(missing_tracks)} of {len(tracks)} audio file(s) missing: "
            + ", ".join(sorted(missing_tracks))
        )

    return (not reasons), reasons


def scan(station_root: Path) -> list[PackageStatus]:
    """Every direct subdirectory of `station_root` containing a
    `manifest.json` is a package; anything else (files, dirs without a
    manifest) is skipped. A v2-or-earlier manifest yields `state=
    "unsupported"` and is never touched further.

    A missing or non-directory `station_root` yields an empty list rather
    than raising -- `scan` alone can't distinguish "not configured yet" from
    "legitimately empty", so that judgment call is left to callers. `emcee
    run`/`emcee status` raise an `EmceeError` naming `[station] root` when
    they need "not configured"/"missing" to be a hard error; `scan`'s
    empty-list result is what they check for that.
    """
    root = Path(station_root)
    if not root.is_dir():
        return []

    statuses: list[PackageStatus] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue   # dot dirs: llama's staged replace-voiced swap
        if not (entry / "manifest.json").exists():
            continue
        pkg = Package(entry)
        try:
            manifest = pkg.manifest()
        except UnsupportedPackage:
            version = json.loads(pkg.manifest_path.read_text()).get(
                "schema_version", "?"
            )
            statuses.append(
                PackageStatus(
                    path=entry,
                    state="unsupported",
                    reasons=[f"unsupported (v{version} — re-deliver from llama)"],
                    profile=raw_profile(pkg.manifest_path),
                )
            )
            continue
        ok, reasons = readiness(pkg)
        statuses.append(
            PackageStatus(path=entry, state="ready" if ok else "pending", reasons=reasons,
                          profile=manifest_profile(manifest),
                          voiced_by=manifest_voiced_by(manifest))
        )
    return statuses
