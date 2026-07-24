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
                   "sets", "n_breaks", "feedback"},
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


def test_vet_research_prompt_excludes_context_mentions():
    text = load_prompt("vet_research")
    assert text.count("Exclude") >= 2  # once for songs, once for dates
    assert "AT THIS SHOW" in text


def test_vet_research_prompt_extracts_set_count():
    text = load_prompt("vet_research")
    assert "asserted_set_count" in text
    assert "encore" in text.lower()  # encores must not count as sets
