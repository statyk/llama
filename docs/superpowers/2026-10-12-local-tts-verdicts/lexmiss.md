# lexmiss report
Commit: 0657a4d (doc only). Suite: ./.venv/bin/pytest -q -> 2881 passed, 1 skipped, 8 deselected.
Script: /private/tmp/claude-501/-Users-shawn-projects-llama--claude-worktrees-local-tts/99c83788-8478-441d-8793-405d9af30862/scratchpad/lexmiss/lexmiss.py sha256 facce83cf208a01d791ff722c0287814e5d1bf67168f891ec1eb022aa590580b
Corpus: 3904 distinct sentences (matches), 129 packages, 376 texts.
KEY FINDING: ~/.emcee has no overlay; the baked-in lexicon has only 2 entries (Mydland->Midland, Sugaree->Shugaree). Drumz and Wharf Rat are NOT in it.
Results, both (i) 2/0.15/4/0.25 and (ii) 2/0.25/4/0.25: 0/3904 sentences fail, 0/129 packages. 95 sentences contain a respelled token: 94 miss 1 word, 1 misses 2 (allowance min 2, so headroom >= 1). No failing examples exist.
Top entries: Mydland 51 misses (51 occ), Sugaree 45 (45 occ); only 2 entries appear.
Follow-up "lexicon-aware matching" NOT added (count is zero); noted in the doc as relevant only if the lexicon grows.
