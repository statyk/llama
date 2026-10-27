"""Station model: scan a delivered-packages folder (`[station] root`) for
emcee packages and compute each one's voice readiness.

Readiness has five legs: script present, DJ audio present, broadcast.m3u
present, every manifest track's audio on disk, and (2026-10-16) the
profile check: a voiced package was voiced as the profile emcee would voice
it as now (`effective_profile`: a recorded move, else an artist rule, else
llama's profile). transmitter mirrors the first four on files alone and
deliberately NOT the fifth: it cannot see rules or moves.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from emcee.artists import normalize_artist
from emcee.config import EmceeConfig
from emcee.moves import Moves
from emcee.package_io import Package, UnsupportedPackage


AWAITING = "awaiting-fix"
MAX_REASON_CHARS = 200


def awaiting_fix_reason(manifest: object) -> str | None:
    """llama's `awaiting_fix` mark (a top-level raw manifest key): None when
    the package carries none (absent or null), else the status line. ANY
    non-null value means "not to be voiced" -- the inner shape is display
    only, so a malformed value never raises and never lets the package
    through. Mirrors transmitter's function (emcee imports neither)."""
    if not isinstance(manifest, dict):
        return None
    mark = manifest.get("awaiting_fix")
    if mark is None:
        return None
    reason = mark.get("reason") if isinstance(mark, dict) else None
    if isinstance(reason, str):
        reason = " ".join(reason.split())
        if reason:
            if len(reason) > MAX_REASON_CHARS:
                reason = reason[:MAX_REASON_CHARS - 1] + "\u2026"
            return f"awaiting fix from llama: {reason}"
    return "awaiting fix from llama"


@dataclass
class PackageStatus:
    path: Path
    state: str  # "ready" | "pending" | "unsupported" | "error" | "awaiting-fix"
    reasons: list[str] = field(default_factory=list)
    # The EFFECTIVE profile (move > artist rule > llama's). For an unsupported
    # or unreadable manifest, llama's profile best-effort (no resolution).
    profile: str | None = None
    # Who voiced it: None = not voiced, "?" = voiced before emcee recorded the
    # presenter (legacy), "house" = house narrator, else the presenter id.
    voiced_by: str | None = None
    delivered_profile: str | None = None     # llama's profile (manifest_profile)
    profile_source: str | None = None        # "move" | "artist" | "llama"; None = not resolved
    performance_id: str | None = None
    voiced: bool = False                     # the dj_audio block is present
    voiced_profile: str | None = None        # manifest_voiced_profile
    voiced_source: str | None = None         # dj_audio.profile_source as recorded
    profile_reason: str | None = None        # the profile check's failing reason, if it fails
    missing_tracks: int = 0                  # manifest tracks whose audio is not on disk
    clips: int = 0                           # clips a voicing renders: one per non-encore set + outro
    move_problem: str | None = None          # use-time move validation failure
    tts: dict | None = None                  # dj_audio.tts as recorded
    awaiting_fix: str | None = None          # llama's station mark, as its status line


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


def raw_manifest(manifest_path: Path) -> object:
    """The raw parsed manifest, or None when it cannot be read. Never raises."""
    try:
        return json.loads(Path(manifest_path).read_text())
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


@dataclass(frozen=True)
class Assessment:
    """Every readiness leg's outcome for one package, plus what the run plan
    needs to classify it."""
    reasons: list[str]
    voiced: bool                    # the dj_audio block is present
    profile_reason: str | None      # the profile check's failing reason
    missing_tracks: int
    clips: int
    effective: Effective

    @property
    def ok(self) -> bool:
        return not self.reasons


def profile_change_reason(voiced: str | None, effective: Effective,
                          voiced_source: str | None) -> str:
    """The profile check's reason, one per direction (spec section 4)."""
    head = f"voiced as {profile_label(voiced)}, now {profile_label(effective.profile)}"
    if effective.source == "artist":
        return f'{head} (artist rule "{effective.rule}")'
    if effective.source == "move":
        return f"{head} (move)"
    if voiced_source == "move":
        return f"{head} (move no longer recorded)"
    return f"{head} (delivered profile; no rule or move applies)"


def assess(pkg: Package, config: EmceeConfig, moves: Moves,
           manifest: dict | None = None) -> Assessment:
    """All five legs. Callers must have already screened out unsupported
    (pre-v3) packages: this assumes `pkg.manifest()` succeeds and lets
    `UnsupportedPackage`/`EmceeError` (or a bare KeyError from a malformed
    manifest) propagate.

    The profile check runs only when `dj_audio` is present: the voiced
    profile (`manifest_voiced_profile`; a legacy block reads as llama's
    profile) must equal the effective one. A missing `tts`, or a different
    presenter, never fails it.

    `manifest`, when given, is the already-read (and validated) manifest;
    otherwise it is read here."""
    if manifest is None:
        manifest = pkg.manifest()
    effective = effective_profile(config, moves, manifest)
    reasons: list[str] = []

    dj_notes = manifest.get("dj_notes")
    if dj_notes is None or not (pkg.dir / "dj-notes.md").exists():
        reasons.append("no DJ script (dj_notes block + dj-notes.md required)")

    dj_audio = manifest.get("dj_audio")
    profile_reason = None
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
        voiced_as = manifest_voiced_profile(manifest)
        if voiced_as != effective.profile:
            profile_reason = profile_change_reason(voiced_as, effective,
                                                   manifest_voiced_source(manifest))
            reasons.append(profile_reason)

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

    # One intro per non-encore set plus one outro (script_guard enforces it).
    lead_in_sets = {t.get("set") for t in tracks
                    if isinstance(t, dict) and t.get("set") != "encore"}
    return Assessment(reasons, dj_audio is not None, profile_reason, len(missing_tracks),
                      len(lead_in_sets) + 1, effective)


def readiness(pkg: Package, config: EmceeConfig, moves: Moves) -> tuple[bool, list[str]]:
    """(ok, reasons) over the five legs; see `assess`."""
    a = assess(pkg, config, moves)
    return a.ok, a.reasons


def identity(manifest: object, config: EmceeConfig, moves: Moves) -> dict:
    """The PackageStatus fields that need only the manifest. Never raises,
    so an error row can carry them too."""
    effective = effective_profile(config, moves, manifest)
    return {"profile": effective.profile, "profile_source": effective.source,
            "delivered_profile": manifest_profile(manifest),
            "performance_id": manifest_performance_id(manifest),
            "voiced": isinstance(_get(manifest, "dj_audio"), dict),
            "voiced_by": manifest_voiced_by(manifest),
            "voiced_source": manifest_voiced_source(manifest),
            "voiced_profile": manifest_voiced_profile(manifest),
            "tts": manifest_tts(manifest),
            "move_problem": move_target_problem(config, moves, manifest)}


def package_status(pkg: Package, config: EmceeConfig, moves: Moves,
                   manifest: dict | None = None) -> PackageStatus:
    """A loadable v3 package's status. May raise on a malformed manifest.
    `manifest`, when given, is the already-read one (no second read)."""
    if manifest is None:
        manifest = pkg.manifest()
    held = awaiting_fix_reason(manifest)
    if held is not None:
        return PackageStatus(path=pkg.dir, state=AWAITING, reasons=[held], awaiting_fix=held,
                             **identity(manifest, config, moves))
    a = assess(pkg, config, moves, manifest)
    return PackageStatus(path=pkg.dir, state="ready" if a.ok else "pending", reasons=a.reasons,
                         profile_reason=a.profile_reason,
                         missing_tracks=a.missing_tracks, clips=a.clips,
                         **identity(manifest, config, moves))


def unsupported_status(pkg: Package) -> PackageStatus:
    raw = raw_manifest(pkg.manifest_path)
    version = raw.get("schema_version", "?") if isinstance(raw, dict) else "?"
    profile = manifest_profile(raw)
    return PackageStatus(path=pkg.dir, state="unsupported",
                         reasons=[f"unsupported (v{version} — re-deliver from llama)"],
                         profile=profile, delivered_profile=profile,
                         performance_id=manifest_performance_id(raw))


SCAN_WORKERS = 16


def scan(station_root: Path, config: EmceeConfig, moves: Moves) -> list[PackageStatus]:
    """Every direct subdirectory of `station_root` containing a
    `manifest.json` is a package; anything else is skipped, and so are
    dot-prefixed dirs (llama's staged replace-voiced swap). A v2-or-earlier
    manifest yields `state="unsupported"`. Read-only.

    A missing or non-directory `station_root` yields an empty list rather
    than raising: `run`/`status` decide whether that is an error.
    """
    root = Path(station_root)
    if not root.is_dir():
        return []

    def check(entry: Path) -> PackageStatus | None:
        if not entry.is_dir() or entry.name.startswith("."):
            return None
        if not (entry / "manifest.json").exists():
            return None
        pkg = Package(entry)
        try:
            manifest = pkg.manifest()
        except UnsupportedPackage:
            return unsupported_status(pkg)
        return package_status(pkg, config, moves, manifest)

    # Per-package work is I/O-latency-bound (a network share), so check
    # packages concurrently. `map` yields in input (sorted) order and
    # re-raises a worker's exception here, so `scan` fails as it always has.
    entries = sorted(root.iterdir())
    with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as pool:
        results = list(pool.map(check, entries))
    return [r for r in results if r is not None]
