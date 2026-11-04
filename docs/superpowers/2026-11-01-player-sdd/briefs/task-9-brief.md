### Task 9: Show pages

**Model hint:** opus.

**Files:**
- Modify: `packages/transmitter/src/transmitter/site.py`, `antenna/templates/show.html`
- Create: `antenna/public/assets/show.js`
- Test: `packages/transmitter/tests_transmitter/test_site.py`

**Interfaces:**
- Consumes: Task 2's `sections` and `archive_link`; Task 3's `airTime`, `zoneLabel`, `notesHref`; Task 7's `hostile.json`.
- Produces: `site.concert_stub(date) -> (line, year)`, `site.where_line(venue, city) -> str`. `render_show_page` keeps its signature. `show.html` placeholders added: `$sections_html`, `$archive_html`, `$og_image_html`, `$date_stub`, `$year_stub`, `$where`; removed: `$briefing_html`, `$venue`, `$city_suffix`, `$archive_url`.

- [ ] **Step 1: Write failing pytest tests.**

```python
def test_show_page_renders_sections_and_never_the_raw_marks():
    page = _page(briefing=BRIEFING)
    assert "<h2>Context</h2>" in page or ">Context<" in page
    assert "<li>Opened hot</li>" in page
    for raw in ("# Briefing", "## ", "**", "Cautions", "Do not say great"):
        assert raw not in page

def test_show_page_description_is_the_first_non_heading_text():
    assert 'content="Band played Club in Lincoln.' in _page(briefing=BRIEFING)

def test_show_page_leaves_out_the_button_for_a_non_archive_url():
    page = _page(url="javascript:alert(1)")
    assert "Hear the full tape" not in page and "javascript:" not in page

def test_a_quote_in_an_archive_url_is_escaped_in_the_href():
    page = _page(url='https://archive.org/x"><script>')
    assert '"><script>' not in page and "&quot;&gt;&lt;script&gt;" in page

def test_a_quote_in_the_description_is_escaped():
    assert 'Band said &quot;hi&quot;' in _page(briefing='## A\nBand said "hi"\n')

def test_doubled_segue_marks_are_gone():
    page = _page(setlist=[{"title": "Drums / Space >", "segue": True, "set": "2"}])
    assert "Drums / Space &gt; &gt;" not in page and "Drums / Space &gt;" in page

def test_the_ai_disclaimer_is_on_the_page():
    assert "Show notes are AI generated and may contain mistakes." in _page()

def test_og_image_needs_a_site_url():
    assert "cassette-og.png" in _page(site_url="https://x.example")
    assert "og:image" not in _page(site_url=None)

def test_show_page_escapes_sections():
    assert "<script>" not in _page(briefing="## A\n<script>x</script>\n")

def test_show_page_escapes_a_heading_and_a_bullet():
    page = _page(briefing="## <b>A</b>\n- <i>x</i>\n")
    assert "<b>" not in page and "<i>" not in page

def test_the_hostile_fixture_stays_text():
    hostile = json.loads((REPO / "antenna" / "e2e" / "fixtures" / "hostile.json").read_text())
    page = site.render_show_page(TEMPLATE, hostile, site_url=None, station_name="LMA Radio")
    assert "<img" not in page

def test_the_template_has_no_inline_script():
    assert "<script>" not in TEMPLATE

@pytest.mark.parametrize("date,want", [
    ("2008-11-01", ("SAT NOV 1", "2008")),
    ("1977-05-00", ("1977-05-00", "")),
    ("1977", ("1977", "")),
    ("2008-13-45", ("2008-13-45", "")),
    ("garbage", ("garbage", "")),
    (None, ("", "")),
    (1977, ("1977", "")),
])
def test_concert_stub_never_raises(date, want):
    assert site.concert_stub(date) == want

@pytest.mark.parametrize("venue,city,want", [
    ("Club", "Lincoln", "Club, Lincoln"), ("Club", None, "Club"), (None, "Lincoln", "Lincoln"), (None, None, ""),
])
def test_where_line(venue, city, want):
    assert site.where_line(venue, city) == want
```

  Update `test_show_page_escapes_and_fills_every_placeholder` for the new placeholders. `_page` is a small helper over `render_show_page(TEMPLATE, build_notes(...))`; `REPO` is the repository root, as `TEMPLATE` already finds it.

- [ ] **Step 2: Run** `./.venv/bin/pytest packages/transmitter/tests_transmitter/test_site.py -q`. Expected: the new tests fail.

- [ ] **Step 3: Implement `render_show_page`** from `notes["sections"]`. The setlist uses one rule: normalise a trailing `>` or `->` to " >", add " >" from the flag only when absent. `$archive_html` comes from `archive_link`, opening with `target="_blank" rel="noopener"`. `$date_stub` and `$year_stub` come from `concert_stub`, which never raises, because an exception here would stop `timeline.json`. `$where` comes from `where_line`. Rewrite `show.html` to `show-page.html`: full ticket, setlist card grouped by set, "Liner notes", air times with the zone line, lineage, the corner disclaimer, a link back to `/`. It uses `/assets/radio.css` and `<script type="module" src="/assets/show.js">`, so no `$` in the template.

- [ ] **Step 4: Run** the same command. Expected: PASS. Also `packages/transmitter/scripts/test-in-debian12.sh` if Docker is running; otherwise say so in the report.

- [ ] **Step 5: `show.js`.** Port the old inline script: reads `/notes/<slug>.json`, slug from `data-slug` built with `notesHref`, writes air times with `airTime` and `zoneLabel`, `textContent` only.

- [ ] **Step 6: Commit.** `transmitter + antenna: show pages from sections`.

---

