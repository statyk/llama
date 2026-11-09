from llama import ts_rules
from llama.models import RecordingSummary
from taperssection_probe import classify_variant, inline_source_segments, source_lines_variant


def test_inline_segments_split_at_labels_and_stop_at_next_label():
    text = ("Phish 1997-12-05 Cleveland Source: Schoeps CMC6/mk41>PSP-2>DA-P1 Transfer: D8>CDwav>SHN "
            "Location: OTS Set 1: Ghost")
    assert inline_source_segments(text) == ["Source: Schoeps CMC6/mk41>PSP-2>DA-P1",
                                            "Transfer: D8>CDwav>SHN"]


def test_inline_segments_word_anchored_and_capped():
    assert inline_source_segments("Transferred by: Bob. Resource: none") == []
    seg = inline_source_segments("source info: " + "x" * 400)
    assert seg and len(seg[0]) <= len("source info: ") + 250


def test_variant_keeps_line_based_reading_when_breaks_exist():
    desc = "Phish<br />Source: SBD > DAT<br />Set 1: Ghost"
    assert source_lines_variant(desc) == ts_rules.source_lines(desc) == ["Source: SBD > DAT"]


def test_classify_variant_reads_inline_source_and_restores_source_lines():
    rec = RecordingSummary(identifier="phish1991-12-07.x", title="Phish 1991-12-07",
                           description="Phish 1991-12-07 Portsmouth Source: SBD > Cass Transfer: deck")
    # Task 2b adopted the in-line reading in the product (Checkpoint A ruling (B))
    assert ts_rules.classify(rec) == "sbd"
    assert classify_variant(rec) == "sbd"
    assert ts_rules.source_lines is not source_lines_variant
