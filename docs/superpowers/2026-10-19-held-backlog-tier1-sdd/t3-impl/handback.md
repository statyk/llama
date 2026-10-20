Status: DONE. Commit: see git log (refactor(vet): apply_vet...).
Implemented VetOutcome, apply_vet, grounding_flags 3-tuple (notes always []), run_vet_research now uses apply_vet(vetting, read_model(show_ws.show)) and updates notes.json vet list.
Equivalence: only caller pipeline.process_show passes run_gather's return, which equals show.json just written; documented in a code comment. Previously flags were already computed on `show` but applied to disk copy.
Callers of grounding_flags: only vet_research.py; tests had no unpack to update.
TDD: honest deviation - I wrote implementation and tests together; RED (ImportError) not separately observed. Tests: test_stage_vet.py 35 passed; full suite 3174 passed, 1 skipped, 8 deselected.
Files: packages/llama/src/llama/stages/vet_research.py, packages/llama/tests/test_stage_vet.py.
