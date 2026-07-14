import re

import pytest

from llama.llm.tasks import load_prompt

EXPECTED = {
    "interpret": {"query"},
    "score_reviews": {"candidates_json", "soft_preferences"},
    "light_research": {"artist", "date", "venue"},
    "extract_setlist": {"description"},
    "deep_research": {"artist", "date", "venue", "dossier", "setlist"},
    "synthesize": {"show_json", "research", "reviews_digest", "sets", "n_breaks"},
}


@pytest.mark.parametrize("name,placeholders", EXPECTED.items())
def test_prompt_loads_with_placeholders(name, placeholders):
    text = load_prompt(name)
    found = set(re.findall(r"\{\{(\w+)\}\}", text))
    assert found == placeholders
    assert len(text) > 200  # a real prompt, not a stub
