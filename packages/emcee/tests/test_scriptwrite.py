import json
from pathlib import Path

from herder import FakeProvider

from emcee.errors import EmceeError
from emcee.package_io import Package
from emcee.presenters import Presenter
from emcee.prompts import load_prompt
from emcee.scriptwrite import (
    NEUTRAL_STYLE,
    ScriptNotes,
    narration_note,
    normalize_song,
    persona_style,
    render_notes_md,
    script_guard,
    write_script,
)

from tests.helpers import build_package

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def manifest_of(tmp_path: Path, **kwargs) -> dict:
    pkg_dir = build_package(tmp_path, **kwargs)
    return Package(pkg_dir).manifest()


def notes_dict(**overrides):
    d = {
        "context": "Peak 1973 tour",
        "set_intros": {
            "1": "Tonight: the Dead at RFK. Opens with Morning Dew.",
            "2": "China Cat leads set two.",
        },
        "outro": "I Know You Rider sends us off. Thanks for listening.",
        "mentioned_songs": ["Morning Dew", "China Cat Sunflower", "I Know You Rider"],
    }
    d.update(overrides)
    return d


def single_set_notes(**overrides):
    d = notes_dict(
        set_intros={"1": "Opens with Morning Dew."},
        mentioned_songs=["Morning Dew"],
    )
    d.update(overrides)
    return d


def make_presenter(**overrides):
    d = dict(
        id="casey",
        name="Casey",
        sex="male",
        voice="v-casey",
        character="Warm late-night FM veteran with dry humor.",
    )
    d.update(overrides)
    return Presenter(**d)


# ---------------------------------------------------------------------------
# script_guard -- ported from llama's factual_guard tests, re-addressed to a
# manifest dict via build_package instead of a Show model.
# ---------------------------------------------------------------------------


def test_guard_passes_clean_notes(tmp_path):
    manifest = manifest_of(tmp_path)
    assert script_guard(ScriptNotes(**notes_dict()), manifest, "full") == []


def test_guard_catches_fabrications_and_mismatches(tmp_path):
    manifest = manifest_of(tmp_path)
    bad = ScriptNotes(**notes_dict(
        mentioned_songs=["Morning Dew", "Werewolves of London"],
        set_intros={"1": "x", "2": "y", "3": "huh"},
    ))
    problems = script_guard(bad, manifest, "full")
    assert any("Werewolves of London" in p for p in problems)
    assert any("nonexistent" in p and "3" in p for p in problems)


def test_guard_rejects_encore_lead_in(tmp_path):
    # Option A: the encore gets no lead-in, so an "encore" key is a fault.
    manifest = manifest_of(tmp_path)
    notes = ScriptNotes(**notes_dict(set_intros={"1": "a", "2": "b", "encore": "c"}))
    problems = script_guard(notes, manifest, "full")
    assert any("encore" in p for p in problems)


def test_guard_requires_every_non_encore_set(tmp_path):
    manifest = manifest_of(tmp_path)
    notes = ScriptNotes(**notes_dict(set_intros={"1": "a"}))  # missing set 2
    assert any("missing set intros" in p for p in script_guard(notes, manifest, "full"))


def test_guard_catches_set_count_claim_in_prose(tmp_path):
    # A structurally-consistent script whose lead-in prose still claims two
    # sets against a single-set structure.
    manifest = manifest_of(tmp_path, sets=("1",), encore=False)
    notes = ScriptNotes(**single_set_notes(
        set_intros={"1": "They actually played two sets that day, and both sets cook."}))
    problems = script_guard(notes, manifest, "full")
    assert problems == ["dj notes claim 2 sets but structure has 1"]


def test_guard_catches_set_count_claim_with_adjective(tmp_path):
    manifest = manifest_of(tmp_path, sets=("1",), encore=False)
    notes = ScriptNotes(**single_set_notes(outro="Both festival sets, young band."))
    problems = script_guard(notes, manifest, "full")
    assert problems == ["dj notes claim 2 sets but structure has 1"]


def test_guard_catches_ordinal_set_claim(tmp_path):
    manifest = manifest_of(tmp_path)
    notes = ScriptNotes(**notes_dict(outro="The third set peak says it all."))
    problems = script_guard(notes, manifest, "full")
    assert problems == ["dj notes mention the third set but structure has 2 sets"]


def test_guard_allows_consistent_set_count_prose(tmp_path):
    manifest = manifest_of(tmp_path)
    notes = ScriptNotes(**notes_dict(
        outro="Two sets plus an encore tonight, and the second set is huge."))
    assert script_guard(notes, manifest, "full") == []


def test_guard_ignores_sets_of_phrases(tmp_path):
    manifest = manifest_of(tmp_path, sets=("1",), encore=False)
    notes = ScriptNotes(**single_set_notes(
        outro="Two sets of fiddle tunes bookend the show."))
    assert script_guard(notes, manifest, "full") == []


# ---------------------------------------------------------------------------
# Vague-mode narration checks (spec §3) -- new in emcee.
# ---------------------------------------------------------------------------


def test_guard_vague_flags_named_song(tmp_path):
    manifest = manifest_of(tmp_path)
    notes = ScriptNotes(**notes_dict())  # names known, real songs -- still forbidden under vague
    problems = script_guard(notes, manifest, "vague")
    assert any("vague" in p and "Morning Dew" in p for p in problems)


def test_guard_vague_flags_set_count_claim(tmp_path):
    manifest = manifest_of(tmp_path)
    notes = ScriptNotes(**notes_dict(
        set_intros={"1": "First half.", "2": "Second half."},
        mentioned_songs=[],
        outro="Two sets plus an encore tonight.",
    ))
    problems = script_guard(notes, manifest, "vague")
    assert any("vague" in p and "2 sets" in p for p in problems)


def test_guard_vague_clean_script_with_segment_structure_passes(tmp_path):
    # Per-gap structure (one lead-in per set) stays even under vague
    # narration -- only the asserted content (songs, set counts) is banned.
    manifest = manifest_of(tmp_path)
    notes = ScriptNotes(
        context="",
        set_intros={
            "1": "Something happened in this venue tonight.",
            "2": "The second half continues strong.",
        },
        outro="Thanks for tuning in.",
        mentioned_songs=[],
    )
    assert script_guard(notes, manifest, "vague") == []
    # ...and the structural checks are NOT relaxed by vague mode: a missing
    # lead-in and an encore-keyed lead-in are still faults under narration
    # "vague" -- vague only constrains what the prose may *assert*, never
    # the per-gap structure itself (spec §3).
    missing_one = ScriptNotes(**{**notes.model_dump(), "set_intros": {"1": "only one"}})
    assert script_guard(missing_one, manifest, "vague") == ["dj notes missing set intros: ['2']"]
    encore_keyed = ScriptNotes(**{**notes.model_dump(),
                                   "set_intros": {"1": "a", "2": "b", "encore": "c"}})
    assert any("encore" in p for p in script_guard(encore_keyed, manifest, "vague"))


def test_guard_vague_flags_ordinal_set_claim(tmp_path):
    manifest = manifest_of(tmp_path)
    notes = ScriptNotes(**notes_dict(
        set_intros={"1": "Something happened tonight.", "2": "The second set was great."},
        mentioned_songs=[],
    ))
    problems = script_guard(notes, manifest, "vague")
    assert problems == ["dj notes mention the second set but narration is vague"]


# ---------------------------------------------------------------------------
# render_notes_md
# ---------------------------------------------------------------------------


def test_notes_md_one_lead_in_per_set_then_outro(tmp_path):
    manifest = manifest_of(tmp_path)
    md = render_notes_md(ScriptNotes(**notes_dict()), manifest)
    headers = [ln for ln in md.splitlines() if ln.startswith("## ")]
    assert headers == ["## Set 1 lead-in", "## Set 2 lead-in", "## Outro"]
    assert md.startswith("# Grateful Dead — 1973-06-10, Some Venue")


def test_render_notes_md_full_content(tmp_path):
    # Full-string lock: catches dropping the `if notes.context:` italic
    # block (a mutation the reviewer found unasserted).
    manifest = manifest_of(tmp_path)
    md = render_notes_md(ScriptNotes(**notes_dict()), manifest)
    expected = "\n".join([
        "# Grateful Dead — 1973-06-10, Some Venue",
        "",
        "*Peak 1973 tour*",
        "",
        "## Set 1 lead-in",
        "Tonight: the Dead at RFK. Opens with Morning Dew.",
        "",
        "## Set 2 lead-in",
        "China Cat leads set two.",
        "",
        "## Outro",
        "I Know You Rider sends us off. Thanks for listening.",
        "",
    ])
    assert md == expected


def test_render_notes_md_no_venue_and_no_context():
    # Direct manifest dict (no need for a full package): catches dropping
    # the `or 'venue unknown'` fallback -- build_package's fixture always
    # has a venue, so this must be exercised separately.
    manifest = {"show": {"artist": "X", "date": "2003-04-19", "venue": None}}
    notes = ScriptNotes(context="", set_intros={"1": "Openers."}, outro="Bye.",
                        mentioned_songs=[])
    md = render_notes_md(notes, manifest)
    expected = "\n".join([
        "# X — 2003-04-19, venue unknown",
        "",
        "## Set 1 lead-in",
        "Openers.",
        "",
        "## Outro",
        "Bye.",
        "",
    ])
    assert md == expected


# ---------------------------------------------------------------------------
# NEUTRAL_STYLE / persona_style byte-locks -- these ports may never drift
# from llama's originals; literals are embedded, llama is never imported.
# ---------------------------------------------------------------------------

EXPECTED_NEUTRAL_STYLE = (
    "Every fact must come from the\n"
    "inputs below — do not invent stories, dates, personnel, or song details. "
    "Voice: warm,\nknowledgeable, economical; written to be read aloud."
)


def test_neutral_style_byte_lock():
    assert NEUTRAL_STYLE == EXPECTED_NEUTRAL_STYLE


ORIGINAL_OPENING = (
    "Write on-air DJ notes for a full-concert radio broadcast. Every fact must come from the\n"
    "inputs below — do not invent stories, dates, personnel, or song details. Voice: warm,\n"
    "knowledgeable, economical; written to be read aloud.\n"
)


def test_neutral_style_reproduces_original_prompt_bytes():
    rendered = load_prompt("scriptwrite").replace("{{style}}", NEUTRAL_STYLE)
    assert rendered.startswith(ORIGINAL_OPENING)


EXPECTED_PERSONA_STYLE = "\n".join([
    "You are Casey, the host, speaking in the first person; written to be read "
    "aloud. You are male; refer to yourself accordingly.",
    "Character:",
    "Warm late-night FM veteran with dry humor.",
    'Your show is called "Sunday Morning Dead" — you know it well; drop the '
    "name naturally now and then, not in every segment.",
    "Grounding rules:",
    "- Concert facts — dates, venue, songs, set structure, personnel, what "
    "happened on stage — must come from the inputs below; do not invent any.",
    "- You may voice opinions, perspective, and brief subjective color of "
    "your own.",
    "- You may adopt opinions found in the research or listener reviews as "
    "your own, paraphrased in your voice — never quote reviewers verbatim "
    "at length and never cite them as sources.",
    "- Never claim you attended this concert or took part in real events; "
    "no invented first-hand history presented as fact.",
    "- Every song you name — including in opinions — must be one of this "
    "show's tracks, spelled exactly as in the show data (map any loose "
    "review titles to those spellings), and listed in mentioned_songs.",
])


def test_persona_style_byte_lock():
    style = persona_style(make_presenter(), "Sunday Morning Dead")
    assert style == EXPECTED_PERSONA_STYLE


def test_persona_style_contains_identity_rules_and_title():
    style = persona_style(make_presenter(), "Sunday Morning Dead")
    assert "You are Casey" in style
    assert "You are male; refer to yourself accordingly." in style
    assert "Warm late-night FM veteran" in style
    assert 'Your show is called "Sunday Morning Dead"' in style
    assert "must come from the inputs below" in style          # facts stay grounded
    assert "adopt opinions found in the research or listener reviews" in style
    assert "Never claim you attended this concert" in style
    assert "spelled exactly as in the show data" in style      # guard-coexistence rule


def test_persona_style_omits_title_when_none():
    assert "Your show is called" not in persona_style(make_presenter(), None)


# ---------------------------------------------------------------------------
# narration_note
# ---------------------------------------------------------------------------


def test_narration_note_full_is_empty():
    assert narration_note("full") == ""


def test_narration_note_vague_forbids_naming_songs():
    note = narration_note("vague")
    assert note and "do not name" in note.lower()


def test_scriptwrite_full_path_has_no_extra_blank_line():
    rendered = load_prompt("scriptwrite").replace("{{narration_note}}", narration_note("full"))
    assert "hearing.\n\nShow data (JSON):" in rendered
    assert "\n\n\nShow data" not in rendered


# ---------------------------------------------------------------------------
# normalize_song sanity (curated GD alias table ported verbatim)
# ---------------------------------------------------------------------------


def test_normalize_song_applies_alias():
    assert normalize_song("Rider") == normalize_song("I Know You Rider")


def test_normalize_song_strips_punctuation():
    assert normalize_song("Truckin'") == normalize_song("Truckin")


# ---------------------------------------------------------------------------
# write_script -- orchestration: pure (never writes the package), retries
# once with feedback, raises EmceeError on persistent guard failure.
# ---------------------------------------------------------------------------


def _snapshot(pkg_dir: Path) -> dict[str, tuple[int, float]]:
    return {
        str(p.relative_to(pkg_dir)): (p.stat().st_size, p.stat().st_mtime_ns)
        for p in sorted(pkg_dir.rglob("*"))
        if p.is_file()
    }


def test_write_script_success_returns_notes_and_touches_nothing(tmp_path):
    pkg_dir = build_package(tmp_path)
    pkg = Package(pkg_dir)
    good = json.dumps(notes_dict())
    fake = FakeProvider(completes=[good])

    before = _snapshot(pkg_dir)
    notes = write_script(pkg, fake, presenter=None, title=None)
    after = _snapshot(pkg_dir)

    assert isinstance(notes, ScriptNotes)
    assert set(notes.set_intros) == {"1", "2"}
    assert before == after
    assert "dj_notes" not in pkg.manifest() or pkg.manifest()["dj_notes"] is None
    assert not (pkg_dir / "dj-notes.md").exists()
    assert "A well-loved show." in fake.calls[0][1]   # briefing.md reached the prompt


def test_write_script_prompt_carries_set_breaks_and_excludes_encore_lead_in(tmp_path):
    # One assertion set covering three payload-slot regressions: set_breaks
    # dropped from the manifest_show_json slot, the encore set leaking into
    # the "write one lead-in per set" list (which would instruct the LLM to
    # write a lead-in script_guard then rejects -- a guaranteed retry-then-
    # fail loop), and encore_note forced empty.
    pkg_dir = build_package(tmp_path)  # default: sets ("1", "2") + encore
    pkg = Package(pkg_dir)
    fake = FakeProvider(completes=[json.dumps(notes_dict())])
    write_script(pkg, fake, presenter=None, title=None)
    prompt = fake.calls[0][1]
    assert '"set_breaks"' in prompt
    assert 'Write one lead-in per set: "1", "2".' in prompt
    lead_in_line = next(ln for ln in prompt.splitlines()
                        if ln.startswith("Write one lead-in per set:"))
    assert "encore" not in lead_in_line
    assert "This show ends with an encore" in prompt


def test_write_script_retries_with_feedback_then_raises(tmp_path):
    pkg_dir = build_package(tmp_path)
    pkg = Package(pkg_dir)
    # Both attempts reference a nonexistent set "5" -- guard fails twice.
    bad = json.dumps(notes_dict(set_intros={"1": "a", "2": "b", "5": "??"}))
    fake = FakeProvider(completes=[bad, bad])

    try:
        write_script(pkg, fake, presenter=None, title=None)
        assert False, "expected EmceeError"
    except EmceeError as exc:
        assert exc.details
        assert any("nonexistent" in p and "5" in p for p in exc.details)

    assert len(fake.calls) == 2
    retry_prompt = fake.calls[1][1]
    assert "fact-checking" in retry_prompt and "set: 5" in retry_prompt


def test_write_script_with_presenter_sends_persona_prompt(tmp_path):
    pkg_dir = build_package(tmp_path)
    pkg = Package(pkg_dir)
    fake = FakeProvider(completes=[json.dumps(notes_dict())])
    write_script(pkg, fake, presenter=make_presenter(), title="Sunday Morning Dead")
    prompt = fake.calls[0][1]
    assert "You are Casey" in prompt and "Grounding rules:" in prompt
    assert "Every fact must come from the\ninputs below" not in prompt


def test_write_script_without_presenter_sends_neutral_prompt(tmp_path):
    pkg_dir = build_package(tmp_path)
    pkg = Package(pkg_dir)
    fake = FakeProvider(completes=[json.dumps(notes_dict())])
    write_script(pkg, fake, presenter=None, title=None)
    prompt = fake.calls[0][1]
    assert "Voice: warm,\nknowledgeable, economical" in prompt
    assert "Grounding rules:" not in prompt


def test_write_script_passes_narration_note_from_manifest(tmp_path):
    pkg_dir = build_package(tmp_path, narration="vague")
    pkg = Package(pkg_dir)
    fake = FakeProvider(completes=[json.dumps(
        notes_dict(mentioned_songs=[], outro="Thanks for listening.",
                   set_intros={"1": "Something happened tonight.",
                               "2": "More happened after that."}))])
    write_script(pkg, fake, presenter=None, title=None)
    prompt = fake.calls[0][1]
    assert "do not name" in prompt.lower()


from emcee.scriptwrite import rephrase_problems, rephrase_segment

SEG = ("China Cat Sunflower leads set two. The climax comes a little early tonight. "
       "Stay with us for the rest of the night.")
MANIFEST = {"tracks": [{"title": "China Cat Sunflower"}, {"title": "Deal"},
                       {"title": "Morning Dew"}]}


def test_rephrase_segment_returns_text_and_prompt_carries_inputs():
    provider = FakeProvider(completes=[json.dumps({"text": "  Revised segment.  "})])
    out = rephrase_segment(provider, SEG, "The climax comes a little early tonight.",
                           ["sexual"])
    assert out == "Revised segment."
    prompt = provider.calls[0][1]
    assert SEG in prompt
    # The template quotes the blocked text; SEG contains it unquoted, so only
    # the quoted form proves `blocked` (not the segment) filled the slot.
    assert '"The climax comes a little early tonight."' in prompt
    assert "sexual" in prompt
    assert "previous attempt" not in prompt


def test_rephrase_segment_feedback_reaches_prompt():
    provider = FakeProvider(completes=[json.dumps({"text": "x"})])
    rephrase_segment(provider, SEG, "b", [], feedback="dj notes claim 3 sets")
    prompt = provider.calls[0][1]
    assert "previous attempt" in prompt and "dj notes claim 3 sets" in prompt
    assert "unspecified" in prompt  # empty categories


def test_rephrase_problems_single_sentence_edit_passes():
    revised = SEG.replace("The climax comes a little early tonight.",
                          "A tape flip cuts into the peak tonight.")
    assert rephrase_problems(SEG, revised, MANIFEST) == []


def test_rephrase_problems_two_separated_edits():
    # First and third sentences changed, the middle one kept: two separate edits.
    revised = (SEG.replace("China Cat Sunflower leads", "China Cat Sunflower opens")
                  .replace("Stay with us", "Do stay with us"))
    assert any("more than one passage" in p for p in rephrase_problems(SEG, revised, MANIFEST))


def test_rephrase_problems_newly_named_track():
    revised = SEG.replace("The climax comes a little early tonight.",
                          "Morning Dew arrives a little early tonight.")
    assert rephrase_problems(SEG, revised, MANIFEST) == [
        "rephrase names a track the original did not: Morning Dew"]


def test_rephrase_problems_new_number():
    revised = SEG.replace("The climax comes a little early tonight.",
                          "The peak lands 3 minutes early tonight.")
    assert rephrase_problems(SEG, revised, MANIFEST) == [
        "rephrase adds numbers the original did not have: 3"]


def test_rephrase_problems_title_match_is_whole_word():
    revised = SEG.replace("The climax comes a little early tonight.",
                          "The ideal peak comes a little early tonight.")
    assert rephrase_problems(SEG, revised, MANIFEST) == []  # "ideal" is not "Deal"
    orig = SEG.replace("The climax", "A great deal of the climax")
    rev = orig.replace("A great deal of the climax comes", "A great deal of the peak comes")
    assert rephrase_problems(orig, rev, MANIFEST) == []  # "deal" was already there


GENERIC_MANIFEST = {"tracks": [{"title": "Jam"}, {"title": "Drums"}, {"title": "Space"},
                               {"title": "Morning Dew"}, {"title": "Truckin'"}]}


def test_rephrase_problems_generic_titles_are_ordinary_words():
    revised = SEG.replace("The climax comes a little early tonight.",
                          "The tape flip on this source cuts into the end of that jam.")
    assert rephrase_problems(SEG, revised, GENERIC_MANIFEST) == []
    revised = SEG.replace("The climax comes a little early tonight.",
                          "There is less space before the drums tonight.")
    assert rephrase_problems(SEG, revised, GENERIC_MANIFEST) == []


def test_rephrase_problems_real_title_still_flagged_case_insensitive():
    revised = SEG.replace("The climax comes a little early tonight.",
                          "morning dew arrives a little early tonight.")
    assert rephrase_problems(SEG, revised, GENERIC_MANIFEST) == [
        "rephrase names a track the original did not: Morning Dew"]


def test_rephrase_problems_punctuation_ending_title_flagged():
    revised = SEG.replace("The climax comes a little early tonight.",
                          "Truckin' leads off a little early tonight.")
    assert rephrase_problems(SEG, revised, GENERIC_MANIFEST) == [
        "rephrase names a track the original did not: Truckin'"]


def test_rephrase_problems_typography_noise_is_not_an_edit():
    orig = "It's a fine night.  The climax comes early. Stay with us."
    rev = "It’s a fine night. The climax comes soon. Stay—with us."
    # untouched sentences 1 and 3 differ only by curly quote / dash / spacing
    assert rephrase_problems(orig, rev, MANIFEST) == []


def test_fold_normalizes_typography():
    from emcee.scriptwrite import _fold
    assert _fold("It’s  “fine” – ok\n") == 'It\'s "fine" - ok'
