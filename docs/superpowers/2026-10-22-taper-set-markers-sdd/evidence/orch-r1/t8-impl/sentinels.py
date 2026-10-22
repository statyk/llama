import json
T = "packages/llama/src/llama/taper.py"; G = "packages/llama/src/llama/stages/gather.py"; R = "packages/llama/src/llama/replay.py"
S = [
 dict(id="S0-base", file=None, predicted=[], note="unmutated copy: expected all green"),
 dict(id="S1-taper", file=T, old="    text, source = taper_text_for(meta)", new='    raise RuntimeError("SENTINEL")',
      predicted=["every decide_taper test in test_taper.py and every compute_gather/compute_legs test (decide_taper runs on every non-override gather)"]),
 dict(id="S2-gather", file=G, old="    notes: list[str] = []\n    kept_count = count_flag", new='    raise RuntimeError("SENTINEL")\n    kept_count = count_flag',
      predicted=["the demote_jerrybase_flags helper tests and the Task 5 gather tests on owned shows with a jerrybase event"]),
 dict(id="S3-replay", file=R, old="    needs_llm = list(gathered.needs_llm)", new='    raise RuntimeError("SENTINEL")',
      predicted=["every compute_legs-based test in test_replay.py and the reapply tests that replay"]),
]
json.dump(S, open("sentinels.json","w"), indent=1)
