from llama.scoring import lineage_class, score_recording


def test_lineage_from_identifier_and_metadata():
    assert lineage_class("gd73-06-10.sbd.hollister", {}) == "sbd"
    assert lineage_class("gd77-05-08.mtx.seamons", {"lineage": "Matrix of SBD+AUD"}) == "matrix"
    assert lineage_class("gd83-10-21.aud.walker", {}) == "aud"
    assert lineage_class("gd95-07-09.unknown", {"source": "Soundboard > DAT"}) == "sbd"
    # 'aud' must not fire on substrings like 'auditorium'
    assert lineage_class("gd78-05-16", {"title": "Municipal Auditorium"}) == "unknown"


def test_sbd_beats_aud_at_equal_ratings():
    kw = dict(avg_rating=4.5, num_reviews=20, has_wanted_format=True, completeness=1.0, complaints=0)
    assert score_recording(lineage="sbd", **kw) > score_recording(lineage="aud", **kw)


def test_review_volume_weights_rating():
    kw = dict(lineage="sbd", has_wanted_format=True, completeness=1.0, complaints=0)
    many = score_recording(avg_rating=4.5, num_reviews=50, **kw)
    few = score_recording(avg_rating=4.5, num_reviews=1, **kw)
    assert many > few


def test_complaints_penalize_capped():
    kw = dict(lineage="sbd", avg_rating=4.0, num_reviews=10, has_wanted_format=True, completeness=1.0)
    clean = score_recording(complaints=0, **kw)
    noisy = score_recording(complaints=3, **kw)
    very_noisy = score_recording(complaints=99, **kw)
    assert clean > noisy > very_noisy
    assert very_noisy == score_recording(complaints=4, **kw)  # capped at 4


def test_none_rating_is_zero_not_error():
    s = score_recording(lineage="unknown", avg_rating=None, num_reviews=0,
                        has_wanted_format=False, completeness=0.5, complaints=0)
    assert s == 0.0  # zero evidence stays zero regardless of completeness


def test_fragment_loses_to_fuller_recording_of_same_show():
    # Real case (GD 1969-11-02): a 6-of-13-track sbd fragment with a hotter
    # rating must not beat a complete sbd of the same performance.
    frag = score_recording(lineage="sbd", avg_rating=5.0, num_reviews=6,
                           has_wanted_format=True, completeness=6 / 13, complaints=0)
    full = score_recording(lineage="sbd", avg_rating=4.7, num_reviews=4,
                           has_wanted_format=True, completeness=1.0, complaints=0)
    assert full > frag


def test_taper_bonus_adds_to_base_score():
    kw = dict(lineage="sbd", avg_rating=4.0, num_reviews=10,
              has_wanted_format=True, completeness=1.0, complaints=0)
    assert score_recording(taper_bonus=2.0, **kw) == score_recording(**kw) + 2.0


def test_lineage_scores_override_inverts_preference():
    kw = dict(avg_rating=4.0, num_reviews=10, has_wanted_format=True,
              completeness=1.0, complaints=0)
    era = {"matrix": 3.0, "aud": 2.0, "sbd": 1.0}  # early-80s GD: boards are rough
    assert score_recording(lineage="aud", lineage_scores=era, **kw) > \
        score_recording(lineage="sbd", lineage_scores=era, **kw)
    assert score_recording(lineage="matrix", lineage_scores=era, **kw) > \
        score_recording(lineage="aud", lineage_scores=era, **kw)


def test_completeness_does_not_flip_lineage_preference():
    # Real case (GD 1970-09-19): a complete audience tape must not beat a
    # good sbd fragment just by being longer - lineage still dominates.
    sbd_fragment = score_recording(lineage="sbd", avg_rating=4.9, num_reviews=30,
                                   has_wanted_format=True, completeness=8 / 23, complaints=0)
    full_aud = score_recording(lineage="aud", avg_rating=4.5, num_reviews=5,
                               has_wanted_format=True, completeness=1.0, complaints=0)
    assert sbd_fragment > full_aud
