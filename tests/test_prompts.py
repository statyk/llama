import re

import pytest

from llama.llm.tasks import load_prompt

EXPECTED = {
    "interpret": {"query"},
    "score_reviews": {"candidates_json", "soft_preferences"},
    "light_research": {"artist", "date", "venue"},
    "extract_setlist": {"description"},
    "deep_research": {"artist", "date", "venue", "dossier", "setlist"},
    "synthesize": {"style", "show_json", "research", "reviews_digest",
                   "lead_in_sets", "encore_note", "feedback", "narration_note"},
    "find_artists": {"query", "max_results", "artist_table"},
    "align_structure": {"tracks", "setlist"},
    "vet_research": {"research"},
}


@pytest.mark.parametrize("name,placeholders", EXPECTED.items())
def test_prompt_loads_with_placeholders(name, placeholders):
    text = load_prompt(name)
    found = set(re.findall(r"\{\{(\w+)\}\}", text))
    assert found == placeholders
    assert len(text) > 200  # a real prompt, not a stub


def test_synthesize_prompt_guides_spoken_stress():
    # The script is spoken by a TTS voice that infers emphasis from phrasing
    # (Voxtral has no emphasis markup); the prompt must steer toward sentences
    # whose focus word carries the natural stress rather than burying it.
    text = load_prompt("synthesize")
    assert "stress" in text.lower()


def test_synthesize_prompt_forbids_symbol_segues():
    text = load_prompt("synthesize")
    low = text.lower()
    assert '"into"' in low or "the word into" in low
    assert "greater than" in low  # explains WHY not to use ">"


def test_synthesize_prompt_bans_very_short_sentences():
    assert "short sentence" in load_prompt("synthesize").lower()


def test_synthesize_prompt_requires_show_id_every_break():
    # Every break must re-state artist + date + venue/city for mid-show tune-ins.
    low = load_prompt("synthesize").lower()
    assert "artist, date, venue" in low
    assert "every break" in low
    assert "tuning in" in low


def test_vet_research_prompt_excludes_context_mentions():
    text = load_prompt("vet_research")
    assert text.count("Exclude") >= 2  # once for songs, once for dates
    assert "AT THIS SHOW" in text


def test_vet_research_prompt_extracts_set_count():
    text = load_prompt("vet_research")
    assert "asserted_set_count" in text
    assert "encore" in text.lower()  # encores must not count as sets
