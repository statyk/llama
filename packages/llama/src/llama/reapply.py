"""`llama reapply`: re-process a show with exactly the replay harness's
computation, in place (held-backlog spec slice 6; extended to packaged,
briefed and delivered shows by the bulk-apply spec, "Re-processing").

`compute_legs` (llama.replay) decides everything; this module maps the result
and writes it. Every write happens inside one `show_unit` (the show lock is
held from the first read through the last write, and any failure restores
every file outside `package/audio/` byte-identical, removes added audio and
puts the old audio back); a dry run takes only the show lock. It writes
`vetting.json`, `notes.json`, the briefing, the package and, last, `show.json`:
the commit marker. After the commit the campaign record is marked processed,
a cleared delivered show with a voiced destination has its library audio
purged as deliver purges it, and the caller's `after_commit` hook runs, all
still inside the unit. `reviews.json`, `provenance.json`, `research.md` and the
ledger are never written, and nothing is delivered.

Held shows take `classify`'s held path, as before. A non-held show (briefed,
packaged or delivered) with flags gets a held commit; with no flag, no
manifest-visible change and a reusable briefing a `show.json`-only commit
(`label-only` or `unchanged`), except a marked delivered show whose destination
is unvoiced, which is re-packaged so `deliver --fixed` can re-deliver it; any
other is briefed (reused or fresh) and packaged. A delivered show that will
package plans its audio reuse strictly (`audio_reuse.plan_reuse(strict=...)`,
`check_pairs`) before the fresh brief, unless `allow_download`.
"""
import dataclasses
import hashlib
import json
import shutil
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from llama import campaign, catalog
from llama.audio_reuse import check_pairs, plan_reuse, write_anchor_if_absent
from llama.catalog import CatalogEntry
from llama.config import Config
from llama.errors import LlamaError
from llama.ledger import Ledger, is_delivered
from llama.locks import file_lock
from llama.models import Provenance, Show, ShowNotes
from llama.overrules import split_overruled
from llama.replay import (GATHER_LLM, CacheOnlyIA, _structure_changed, classify, compute_legs,
                          input_digests, setlistfm_client, shipped_diff, visible_changes)
from llama.pipeline import count_llm_calls
from llama.show_unit import show_unit
from llama.stages.brief import generate_briefing, render_briefing_md
from llama.stages.package import build_package
from llama.station_mark import StationUnreadable, destination_voiced
from llama.workspace import (ShowWorkspace, drop_stage_artifacts, read_json, read_model,
                             read_overrides, write_artifact)

# Spec slice 6 "Batch state": the batch also stops after this many
# consecutive LLM failures of any kind (an openrouter 429 or an unrecognised
# refusal arrives as a plain HerderError, which the pause path never sees).
STOP_AFTER_LLM_FAILURES = 3
# Consecutive `StationUnreadable` rows after which a batch stops (a dropped mount).
STOP_AFTER_STATION_UNREADABLE = 3

# classify's held-show outcomes -> the dry-run prediction (`needs-llm` stops
# before the dry-run check, like the apply).
_PREDICTED = {
    "clears": "cleared",
    "needs-brief": "needs-brief",
    "structure-changed": "structure-changed",
    "still-held": "held",
    "still-held-package": "held",
}
# held outcomes that go on to the brief and the package
_HELD_PACKAGE = frozenset({"clears", "needs-brief", "structure-changed"})


@dataclasses.dataclass
class ReapplyOutcome:
    slug: str
    # "cleared" | "held" | "label-only" | "unchanged" | "needs-llm" |
    # "skipped: not held" | "skipped: processed" |
    # "skipped: re-selection (llama redo <slug> --from select)" |
    # "skipped: inputs changed" | "skipped: structure changed" |
    # "dry-run: <predicted>"
    outcome: str
    briefing: str                  # "reuse" | "fresh" | "none"
    flags: list[str]
    delivered: bool                # the ledger records the performance as delivered
    written: list[str]             # artifact names, in write order
    # "fresh" | "reuse" | "needs-llm" | "label-only" | "none": the work this row did
    kind: str = "none"
    # {"reused": r, "downloaded": d} after a package; {} otherwise
    audio: dict[str, int] = dataclasses.field(default_factory=dict)
    align_reproduced: bool | None = None   # set by the gather-LLM path (Task 10)


def _station_dir(config: Config, ws: ShowWorkspace) -> Path | None:
    return config.delivery_path / ws.dir.name if config.delivery_path else None


def _destination_voiced(config: Config, ws: ShowWorkspace, *, tolerate: bool) -> bool:
    """`station_mark.destination_voiced` for a delivered show. A missing or
    unreadable station copy, or no delivery_path, is `StationUnreadable`, never
    "unvoiced"; with `tolerate` (`--allow-download`: the operator has waived the
    station copy) it reads as unvoiced."""
    out = _station_dir(config, ws)
    try:
        if out is None:
            exc = StationUnreadable(
                f"{ws.dir.name}: station copy unreadable: no delivery_path in config")
            exc.detail = "no delivery_path in config"
            raise exc
        return destination_voiced(out)
    except StationUnreadable:
        if tolerate:
            return False
        raise


def _align_reproduced(stored: Show, new: Show) -> bool:
    """Did the fresh alignment reproduce the stored one: equal filenames, set labels,
    segues and `set_breaks`."""
    def key(show: Show):
        return ([(t.filename, t.set, t.segue) for t in show.tracks], list(show.set_breaks))
    return key(stored) == key(new)


def _purge_line(r, slug: str) -> str:
    """deliver's three purge messages (`cli._echo_purge`), slug-prefixed when purged."""
    if r.warning:
        return f"warning: library audio for {slug} partly purged: {r.warning}"
    if r.skipped:
        return f"warning: kept library audio for {slug}: {r.skipped}"
    return f"{slug}: library audio purged ({catalog.human_bytes(r.freed)} freed)"


def reapply_show(config: Config, ia, ledger: Ledger, entry: CatalogEntry, *,
                 providers: dict, row: dict | None, dry_run: bool,
                 echo: Callable[[str], None],
                 allow_structure_change: bool = False,
                 with_gather_llm: bool = False,
                 allow_download: bool = False,
                 after_commit: Callable[[ShowWorkspace], None] | None = None) -> ReapplyOutcome:
    """Reapply one show (spec slice 6; bulk-apply spec "Re-processing"). `ia` is
    the real archive.org client and is used ONLY by `build_package`; the replay
    itself reads the cache through `CacheOnlyIA`. `row` is the show's
    predicted-list row (its `digests` must still match), or None for a show
    named on the command line. The only LLM call is one fresh brief
    (`providers["brief"]`), made before anything is written. A show whose replay
    changes its sets/segues/breaks is applied only when `allow_structure_change`;
    otherwise nothing is written and the outcome is `skipped: structure changed`.

    The writes run inside `show_unit(ws, None)`, so any failure (a refusal, a
    station refusal, a failed package, a failing `after_commit`) restores the
    show. `CampaignUnreadable` and the station refusals propagate.

    `with_gather_llm` (bulk-apply spec "Re-processing", "Shows whose replay needs an
    LLM call"): a show whose only needs-LLM verdicts are gather's own touchpoints
    (`replay.GATHER_LLM`) is recomputed with `providers["extract_setlist"]` and
    `providers["align_structure"]` and then goes on as any other show, with
    `kind = "needs-llm"`. A delivered show first plans its audio reuse strictly (its
    outcome is not known yet), so an unpaired or unreadable station copy spends no
    call. An LLM failure there escapes before any write (the list runner records a
    retryable row failure); a dry run makes no call (`dry-run: needs-llm`)."""
    ws = entry.ws
    if dry_run:
        with file_lock(ws.lock):
            return _reapply(config, ia, ledger, entry, providers=providers, row=row,
                            dry_run=True, echo=echo,
                            allow_structure_change=allow_structure_change,
                            with_gather_llm=with_gather_llm,
                            allow_download=allow_download, after_commit=None)
    with show_unit(ws, None):
        return _reapply(config, ia, ledger, entry, providers=providers, row=row,
                        dry_run=False, echo=echo,
                        allow_structure_change=allow_structure_change,
                        with_gather_llm=with_gather_llm,
                        allow_download=allow_download, after_commit=after_commit)


def _reapply(config: Config, ia, ledger: Ledger, entry: CatalogEntry, *,
             providers: dict, row: dict | None, dry_run: bool,
             echo: Callable[[str], None], allow_structure_change: bool,
             allow_download: bool, with_gather_llm: bool = False,
             after_commit: Callable[[ShowWorkspace], None] | None) -> ReapplyOutcome:
    """`reapply_show`'s body; the caller holds the show lock (and, unless a dry
    run, the unit)."""
    ws, slug = entry.ws, entry.slug
    if not ws.show.exists():
        raise LlamaError(f"cannot reapply {slug}: missing show.json")
    stored = read_model(ws.show, Show)
    delivered = is_delivered(ledger, stored.performance_id)
    held = stored.needs_review
    manifest = ws.package_dir / "manifest.json"
    packaged = manifest.exists()

    extra: dict = {}     # align_reproduced, once the gather-LLM recompute has run

    def result(outcome: str, briefing: str = "none", flags=(), written=(), **kw) -> ReapplyOutcome:
        return ReapplyOutcome(slug, outcome, briefing, list(flags), delivered, list(written),
                              **{**extra, **kw})

    # The campaign record: an unreadable one raises CampaignUnreadable (never "no record").
    rec = campaign.read_record(ws)
    mark = campaign.last_mark(rec)
    awaiting = campaign.awaiting_fix(rec)
    if awaiting and mark is not None and mark.start_stage == "select":
        return result(f"skipped: re-selection (llama redo {slug} --from select)")
    if not held:
        if rec is not None and not awaiting and rec.processed is not None:
            return result("skipped: processed")
        if not (delivered or packaged or ws.briefing_json.exists()):
            # spec "Re-processing": extended to packaged, briefed and delivered shows only
            return result("skipped: not held")
    if row is not None and input_digests(ws) != row["digests"]:
        return result("skipped: inputs changed")

    scratch = Path(tempfile.mkdtemp(prefix="llama-reapply-"))
    try:
        legs = compute_legs(ws, config=config, ia=CacheOnlyIA(config.root / "cache"),
                            slfm=setlistfm_client(config), scratch=scratch / "show")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    station = _station_dir(config, ws)
    reuse = None
    gather_llm = False
    if with_gather_llm and legs.needs_llm and set(legs.needs_llm) <= GATHER_LLM:
        if dry_run:
            return result("dry-run: needs-llm", legs.brief, legs.flags, kind="needs-llm")
        if delivered:
            # The outcome is not known yet, so every delivered show is checked: an
            # unpaired or unreadable station copy raises here, before any call.
            reuse = plan_reuse(ws, station, strict=not allow_download)
            check_pairs(reuse, ws)
        stored_llm = "stored alignment llm" in legs.needs_llm
        # providers["align_structure"] is one provider or a ladder (a list): wrap each rung
        counted, align_calls = count_llm_calls({"align": providers["align_structure"]})
        scratch = Path(tempfile.mkdtemp(prefix="llama-reapply-"))
        try:
            legs = compute_legs(ws, config=config, ia=CacheOnlyIA(config.root / "cache"),
                                slfm=setlistfm_client(config), scratch=scratch / "show",
                                gather_providers=(providers["extract_setlist"], counted["align"]),
                                llm_failures_raise=True)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        gather_llm = True
        # set only when the stored alignment was llm or align_structure was really called
        if stored_llm or align_calls():
            extra["align_reproduced"] = _align_reproduced(legs.stored, legs.replayed_show)
    replayed = legs.replayed_show

    if held:
        outcome, _would_be = classify(legs, "held")
        if outcome == "needs-llm":
            return result("needs-llm", legs.brief, legs.flags, kind="needs-llm")
        if outcome not in _PREDICTED:
            raise LlamaError(f"cannot reapply {slug}: unexpected replay outcome {outcome!r}")
        structure = outcome == "structure-changed"
        route = "package" if outcome in _HELD_PACKAGE else "held"
        predicted = _PREDICTED[outcome]
    else:
        if legs.needs_llm:
            return result("needs-llm", legs.brief, legs.flags, kind="needs-llm")
        diff = shipped_diff(stored, replayed)
        structure = _structure_changed(diff)
        if legs.flags:
            route, predicted = "held", "held"
        elif (not visible_changes(stored, replayed) and legs.brief == "reuse"
              and not (awaiting and delivered
                       and _destination_voiced(config, ws, tolerate=allow_download) is False)):
            # Nothing a listener sees moved: commit show.json only. A marked delivered
            # show whose destination is unvoiced is re-packaged instead (Review Focus 4).
            route = "show"
            predicted = "label-only" if any(diff.values()) else "unchanged"
        else:
            route = "package"
            predicted = "cleared" if legs.brief == "reuse" else "needs-brief"

    if dry_run:
        if structure and not allow_structure_change:
            # as the apply: skipped, so it spends no brief and no download
            return result("dry-run: skipped: structure changed", "none", legs.flags)
        return result(f"dry-run: {predicted}", legs.brief, legs.flags)
    if structure and not allow_structure_change:
        return result("skipped: structure changed", legs.brief, legs.flags)

    flags = list(legs.flags)
    profile = read_model(ws.provenance, Provenance).profile
    final_show = replayed.model_copy(
        update={"review_flags": list(flags), "needs_review": bool(flags)})

    # Station reads before any spend or write: a delivered show that will package
    # pairs its audio strictly (unless allow_download) and learns whether its
    # destination is voiced (the purge rider). Both raise StationUnreadable /
    # StationUnpaired for a station copy that cannot be used.
    voiced = False
    if route == "package":
        if reuse is None:
            reuse = plan_reuse(ws, station, strict=delivered and not allow_download)
            check_pairs(reuse, ws)
        if delivered:
            voiced = _destination_voiced(config, ws, tolerate=allow_download)

    # In memory first: the fresh brief (the one LLM call) runs before any write.
    # legs.flags = gather + vet + carried package flags + brief_flags; the
    # replayed show's own review_flags lack the carried ones.
    briefing = None
    brief_notes: list[str] = []
    if route != "show":
        if legs.brief == "reuse":
            briefing = legs.briefing            # stored, 3a-normalised by compute_legs
            brief_notes = list(legs.brief_notes)    # its overruled guard problems
        elif legs.brief == "fresh":
            research_md = ws.research.read_text() if ws.research.exists() else ""
            reviews = read_json(ws.reviews) if ws.reviews.exists() else []
            echo(f"{slug}: writing a fresh briefing")
            overrides = read_overrides(ws)
            briefing, problems = generate_briefing(
                providers["brief"], final_show, research_md, reviews,
                narration=overrides.narration,
                vetting=legs.vet.result if legs.vet is not None else None,
                overrules=overrides.overrules)
            # Overrules (bulk-apply spec "Overrules persist"), as `run_brief`: a guard
            # problem matching a recorded overrule triggered no retry and is a
            # notes.json `brief` note.
            problems, brief_notes = split_overruled(problems, overrides.overrules, final_show)
            flags += problems

    written: list[str] = []

    def put(path: Path, data) -> None:
        write_artifact(path, data)
        written.append(path.name)

    # From here on this call writes. The first write of a packaged or delivered show
    # is the reuse anchor (bulk-apply spec "Held outcomes keep a reuse anchor").
    if delivered or packaged:
        write_anchor_if_absent(ws)
    audio: dict[str, int] = {}
    if route == "show":
        put(ws.show, final_show)
    else:
        if legs.vet is not None:
            put(ws.vetting, legs.vet.result)
        put(ws.notes, ShowNotes(gather=list(legs.gather.notes),
                                vet=list(legs.vet.notes) if legs.vet is not None else [],
                                brief=brief_notes))
        if briefing is not None:
            # Both files from the (normalised) model, on reuse too: a stored
            # briefing.md is never copied (spec 3a: re-rendered on every reuse).
            put(ws.briefing_json, briefing)
            put(ws.briefing_md, render_briefing_md(briefing, final_show))
        if (briefing is None and flags
                and (ws.briefing_json.exists() or ws.briefing_md.exists())
                and any(shipped_diff(stored, final_show).values())):
            # Held with the briefing leg not run, and the replay moved shipped
            # fields: the stored briefing was written against the OLD show, and
            # a later `fix --overrule` -> `redo --from package` would ship it
            # unchecked (package does not re-run briefing_guard). Drop the
            # brief stage's artifacts (briefing.json, briefing.md and, as a
            # redo from brief, package/manifest.json) so the eventual overrule
            # regenerates the briefing. The anchor stays (it pairs the station
            # copy for that later re-package).
            drop_stage_artifacts(ws, "brief")
            written.append("drop:brief")
        if not flags:
            # As `redo --from package`: a stale manifest must never short-circuit
            # the package and let the show be marked cleared over it.
            drop_stage_artifacts(ws, "package")
            echo(f"{slug}: packaging")
            tally: dict[str, int] = {}
            _pkg, pkg_flags = build_package(ws, ia, final_show, force=False, profile=profile,
                                            reuse=reuse, tally=tally)
            written.append("package")
            audio = {"reused": tally.get("reused", 0), "downloaded": tally.get("downloaded", 0)}
            echo(f"{slug}: audio reused {audio['reused']}, downloaded {audio['downloaded']}")
            flags += pkg_flags
        # The commit marker, written once and last.
        put(ws.show, final_show.model_copy(
            update={"review_flags": list(flags), "needs_review": bool(flags)}))

    campaign.mark_processed(ws, held=bool(flags))
    if after_commit is not None:
        after_commit(ws)          # before the purge: a failure restores, and purged audio is gone
    if route == "package" and not flags and delivered and voiced:
        # A voiced rider: re-packaged, never re-delivered (spec "Purge after a
        # re-package with no re-delivery"); purge_package_audio skips and warns.
        echo(_purge_line(catalog.purge_package_audio(ws, station), slug))

    if route == "show":
        outcome, kind = predicted, "label-only"
    else:
        outcome = "held" if flags else "cleared"
        kind = legs.brief if legs.brief in ("fresh", "reuse") else "none"
    if gather_llm:
        kind = "needs-llm"
    return result(outcome, legs.brief, flags, written, kind=kind, audio=audio)


# --- batch state (spec slice 6 "Batch state"; plan Contracts "Reapply batch state") ---

def load_list(path: Path, *, sha: str, fingerprint: str) -> dict:
    """A predicted list written by `replay compare` (plan Contracts). Refused
    whole when it was written by other code or another config (spec
    "Predicted lists are tied to what produced them"): its rows' outcomes are
    predictions of THAT code under THAT config."""
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise LlamaError(f"cannot read list {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("rows"), list):
        raise LlamaError(f"list {path} is not a predicted list (no rows)")
    for row in data["rows"]:
        if not (isinstance(row, dict) and isinstance(row.get("slug"), str) and row["slug"]
                and isinstance(row.get("digests"), dict)):
            raise LlamaError(f"list {path} has a malformed row: {row!r}"[:300])
    list_sha, list_fp = data.get("sha"), data.get("config_fingerprint")
    # `<sha>-dirty` names no code at all: two trees at one HEAD with different
    # uncommitted edits share it, so equality would accept predictions made by
    # code that is not the code running. Refused on either side.
    if str(list_sha).endswith("-dirty") or sha.endswith("-dirty"):
        raise LlamaError(f"list {path} was written for code {list_sha}; running code is {sha}: "
                         "an uncommitted tree has no code identity, commit first and "
                         "re-run the harness")
    if list_sha != sha or list_fp != fingerprint:
        raise LlamaError(f"list {path} was written for code {list_sha} and config {list_fp}; "
                         f"running code is {sha}, config {fingerprint}")
    return data


def batch_dir(root: Path, list_path: Path) -> Path:
    """`<root>/reapply/<sha256(list bytes)[:16]>`: outside `runs/`, so `llama run
    list` never sees it; the same list file always finds the same batch."""
    return root / "reapply" / hashlib.sha256(Path(list_path).read_bytes()).hexdigest()[:16]


def read_progress(batch: Path) -> dict[str, dict]:
    """slug -> its LAST progress row. A slug is finished when that row has
    `retryable == false`. A line that does not parse (a crash mid-append) is
    skipped: its show is then simply not finished, the safe direction."""
    path = batch / "progress.jsonl"
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and isinstance(row.get("slug"), str):
            out[row["slug"]] = row
    return out


def outcome_retryable(outcome: str, with_gather_llm: bool = False) -> bool:
    """Whether a row that ended in `outcome` is run again by a re-run of the same list:
    a row that needed an LLM call it was not allowed (run without --with-gather-llm), and a structure change nobody
    allowed yet. The committed outcomes and the `skipped: processed`/`re-selection`
    rows are finished."""
    return ((outcome == "needs-llm" and not with_gather_llm)
            or outcome == "skipped: structure changed")


def record_progress(batch: Path, slug: str, outcome: str, retryable: bool,
                    extra: dict | None = None) -> None:
    """Append one progress row under the batch's own lock; `extra`'s keys are merged in."""
    path = batch / "progress.jsonl"
    line = json.dumps({"slug": slug, "outcome": outcome, "retryable": bool(retryable),
                       "at": datetime.now(timezone.utc).isoformat(), **(extra or {})})
    with file_lock(batch / "progress.lock"):
        # A previous append cut short (no trailing newline) must not swallow this row.
        lead = ""
        if path.exists() and path.stat().st_size:
            with open(path, "rb") as f:
                f.seek(-1, 2)
                lead = "" if f.read(1) == b"\n" else "\n"
        with open(path, "a") as f:
            f.write(lead + line + "\n")
