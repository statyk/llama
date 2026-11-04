### Task 2: Briefing parser and the `sections` field

**Model hint:** sonnet.

**Files:**
- Modify: `packages/transmitter/src/transmitter/site.py:99-153`
- Test: `packages/transmitter/tests_transmitter/test_site.py`

**Interfaces:**
- Produces: `site.parse_briefing(text: str) -> list[dict]`, shaped `[{"heading": str|None, "blocks": [{"p": str} | {"ul": [str]}]}]`; `site.archive_link(url) -> str | None`; `build_notes` output gains `"sections"`. Consumed by Tasks 9 (template) and 10 (panel).

- [ ] **Step 1: Write failing tests.**

```python
BRIEFING = """# Briefing: Band — 2005-11-01, Club

## Context
Band played **Club** in Lincoln.
Second line of the paragraph.

## Set 1
- Opened hot
- Closed cold

## Cautions for the scriptwriter
- Do not say great.
"""

def test_parse_briefing_is_line_based_and_drops_title_and_cautions():
    assert site.parse_briefing(BRIEFING) == [
        {"heading": "Context", "blocks": [{"p": "Band played Club in Lincoln. Second line of the paragraph."}]},
        {"heading": "Set 1", "blocks": [{"ul": ["Opened hot", "Closed cold"]}]},
    ]

def test_cautions_cut_is_case_insensitive_and_runs_to_the_end():
    text = "## Context\nA\n\n## CAUTIONS for the host\n- x\n\n## Late\nB\n"
    assert [s["heading"] for s in site.parse_briefing(text)] == ["Context"]

def test_text_before_any_heading_has_a_null_heading():
    assert site.parse_briefing("Plain note.")[0] == {"heading": None, "blocks": [{"p": "Plain note."}]}

@pytest.mark.parametrize("text", ["", "   \n", "# Briefing: only a title\n"])
def test_empty_briefings_give_an_empty_list(text):
    assert site.parse_briefing(text) == []

def test_the_cautions_heading_literal_is_pinned():
    # The heading is llama's (brief.py render_briefing_md); transmitter cannot import it.
    assert site.CAUTIONS_PREFIX == "## cautions"

def test_notes_carry_sections_and_keep_the_briefing(tmp_path):
    ...  # extend test_notes_from_a_package: doc["sections"] == parse_briefing(doc["briefing"]) and doc["briefing"] unchanged

def test_notes_with_no_briefing_have_empty_sections():
    assert site.build_notes("s", None, None, [], META)["sections"] == []

@pytest.mark.parametrize("url,want", [
    ("https://archive.org/details/x", "https://archive.org/details/x"),
    ("http://archive.org/details/x", None),
    ("https://archive.org.evil.test/x", None),
    ("javascript:alert(1)", None), ("", None), (None, None),
])
def test_archive_link_is_a_literal_prefix_check(url, want):
    assert site.archive_link(url) == want
```

Note `"https://archive.org.evil.test/x"` fails the prefix because the prefix ends in `/`.

- [ ] **Step 2: Run** `./.venv/bin/pytest packages/transmitter/tests_transmitter/test_site.py -q`. Expected: the new tests fail with `AttributeError`.

- [ ] **Step 3: Implement.** `CAUTIONS_PREFIX = "## cautions"`, `ARCHIVE_PREFIX = "https://archive.org/"`. Walk lines: `# ` first-level lines are dropped; a line whose lower-cased form starts with `CAUTIONS_PREFIX` ends parsing; `## ` opens a section; `- ` lines collect into one `ul`; blank lines end a paragraph; consecutive text lines join with a space. Remove every `**`. Omit sections with no blocks. In `build_notes`, add `"sections": parse_briefing(briefing or "")`.

- [ ] **Step 4: Run** the same command. Expected: PASS.

- [ ] **Step 5: Commit.** `transmitter: parse briefings into sections and publish them in the notes`.

---

