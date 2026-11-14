import pytest

from llama.junk_titles import (
    DropInput as D, JunkDrop, held, hold_flag, plan_drops, renumber_text, show_stats,
)


def _drops(rows, **kw):   # rows: (title, set) pairs; filename f"f{i}.mp3", duration 100
    return [(d.position, d.rule) for d in plan_drops(
        [D(f"f{i}.mp3", t, s, 100.0) for i, (t, s) in enumerate(rows)], **kw)]


@pytest.mark.parametrize("title", ["Tuning", "crowd", "Crowd Noise", "Crowd/Tuning", "crowd & tuning",
    "Tuning Up", "Tune Up", "tuneup", "Silence", "TUNING", "(crowd)", "[crowd]", "***crowd noise***",
    "Crowd + Tuning", "Crowd~", "01 Tuning", "Tuning (2:01)"])
def test_rule_a_drops_anywhere(title):
    assert _drops([("Song", "1"), (title, "1"), ("Song 2", "1")]) == [(1, "A")]


@pytest.mark.parametrize("title", ["Crowd/Banter", "crowd encore call", "Mexican Hat Dance Tuning",
    "Crowded Tub", "Tuning >", "Tuning ->", "Crowd > (1:20.19)", "Applause", "Intro", "Banter"])
def test_rule_a_keeps(title):
    assert _drops([("Song", "1"), (title, "1"), ("Song 2", "1")]) == []


def test_raw_arrow_keeps():  # slice 2a stripped the arrow from the shipped title
    assert plan_drops([D("a", "S", "1", 1), D("b", "Crowd", "1", 1, raw_arrow=True), D("c", "S", "1", 1)]) == []


@pytest.mark.parametrize("title", ["Intro", "Intro/Tuning", "Tuning & Intro", "crowd/intro",
    "Introductions", "(Intro)", "[Intro]", "Intro,", "~intro~"])
def test_rule_b_at_show_and_set_start(title):
    assert _drops([(title, "1"), ("Song", "1"), (title, "2"), ("Song", "2")]) == [(0, "B"), (2, "B")]


@pytest.mark.parametrize("title", ["Intro Jam", "Intro > Song", "Intro >"])
def test_rule_b_keeps_at_start(title):
    assert _drops([(title, "1"), ("Song", "1")]) == []


def test_intro_mid_set_keeps():
    assert _drops([("Song", "1"), ("Intro", "1"), ("Song", "1")]) == []


def test_rule_c_last_only():
    assert _drops([("Song", "1"), ("Outro", "1")]) == [(1, "C")]
    assert _drops([("Song", "1"), ("-> Outro", "1")]) == []
    assert _drops([("Song", "1"), ("Outro", "1"), ("Song", "1")]) == []


def test_edge_runs_go_whole():
    assert _drops([("S", "1"), ("Crowd", "2"), ("Intro", "2"), ("S", "2")]) == [(1, "A"), (2, "B")]
    assert _drops([("S", "1"), ("Outro", "1"), ("Crowd", "1")]) == [(1, "C"), (2, "A")]


def test_no_iteration_to_a_fixed_point():
    assert _drops([("Intro", "1"), ("Intro", "1"), ("S", "1")]) == [(0, "B")]


def test_include_wins():
    assert _drops([("S", "1"), ("Tuning", "1")], include=frozenset({"f1.mp3"})) == []


def test_breaker_two_of_three():
    assert held(400, total=6000, median=300)        # 3 of 3
    assert held(370, total=10000, median=300)       # >360 and >median
    assert not held(400, total=10000, median=500)   # >360 only
    assert not held(360, total=7000, median=360)    # strict >: 360 is not > 360; 5.14% passes alone


def test_breaker_missing_durations():
    assert show_stats([None, 100.0, None]) == (100.0, 0.0)
    assert show_stats([]) == (0.0, 0.0)
    assert not held(None, total=100.0, median=0.0)


def test_hold_flag_text():
    d = JunkDrop("gd79-12-05d1t01.mp3", "Tuning", "1", 280.4, "A", 0, 0, True)
    assert hold_flag(d, total=4000.0, median=250.0) == (
        "junk-title drop held for review: 'Tuning' (4:40, 7.0% of show, 1.12x median) "
        "file gd79-12-05d1t01.mp3")


def test_renumber_text():
    m = {1: 1, 2: 2, 3: None, 4: 3, 5: 4, 6: 5, 7: 6}
    assert renumber_text("segues restored: track 5 'X' (E3); track 7 'Y' (E2)", m) == \
        "segues restored: track 4 'X' (E3); track 6 'Y' (E2)"
    assert renumber_text("merged track(s) 4, 6 span a set break", m) == "merged track(s) 3, 5 span a set break"
    assert renumber_text("lossless title: tracks 2-5", m) == "lossless title: tracks 2-4"
    assert renumber_text("short-kept track 3 'Tuning'", m) == "short-kept dropped track 'Tuning'"
    assert renumber_text("tracks 3-3 demoted", m) == "dropped tracks demoted"
    assert renumber_text("set 2 has track 9 'Track 2'", m) == "set 2 has track 9 'Track 2'"
    ident = {i: i for i in range(1, 8)}
    assert renumber_text("tracks 1, 2, 3 and track 4", ident) == "tracks 1, 2, 3 and track 4"


def test_renumber_text_extra_shapes():
    m = {1: 1, 2: None, 3: None, 4: 2, 5: 3}
    assert renumber_text("tracks 2, 3", m) == "dropped tracks"
    assert renumber_text("tracks 1, 2, 4", m) == "tracks 1, 2"
    assert renumber_text("tracks 2-4", m) == "track 2"
    assert renumber_text("tracks 1-5", m) == "tracks 1-3"


@pytest.mark.parametrize("text", ["tracks 1-3, 5", "tracks 1-3-5", "tracks 1,2,3", "tracks 2 - 5",
                                  "track  5", "tracks 1, 2, 3 and track 4"])
def test_renumber_text_identity_never_raises_and_is_unchanged(text):
    ident = {i: i for i in range(1, 8)}
    assert renumber_text(text, ident) == text


@pytest.mark.parametrize("text", ["tracks 1-3, 5", "tracks 1-3-5"])
def test_renumber_text_odd_shapes_do_not_raise(text):
    renumber_text(text, {1: 1, 2: None, 3: 2, 4: 3, 5: 4})


def test_renumber_text_does_not_read_times_as_tracks():
    m = {1: 1, 2: 2, 3: None, 4: 3, 5: 4, 6: 5, 7: 6}
    assert renumber_text("track 5 - 6:30 long", m) == "track 4 - 6:30 long"
    assert renumber_text("track 5-6:30 long", m) == "track 4-6:30 long"


@pytest.mark.parametrize("title", ["-> Crowd", "-> Intro"])
def test_last_track_leading_arrow_never_drops_under_any_rule(title):
    assert plan_drops([D("a", "S", "1", 100.0), D("b", title, "2", 100.0)]) == []
