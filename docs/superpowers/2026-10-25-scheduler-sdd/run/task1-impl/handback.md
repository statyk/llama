# task1-impl handback
Status: DONE
Commit: 4fa87a7 transmitter: tolerant plan rows with scheduler fields; non-show rows skipped downstream (deploy before the scheduler)
Implemented: PlanRow scheduler fields + `extra` (MappingProxyType, compare=False); hand-written to_json/from_json (tuples<->lists, unknown keys kept, known win); planner._parse_row validates kind non-empty str; kind != "show" skipped in site.build_timeline, publish._publish_site (before analysis_for), service.row_analysis (before cache lookup); runbook subsection "Rolling transmitter back" in docs/playout-setup.md (before 7.1).
Tests added: test_layout (3), test_planner (2), test_site, test_publish, test_service (1 each).
RED: against HEAD src via PYTHONPATH scratch copy (git archive), `python -m pytest test_{layout,planner,site,publish,service}.py -q` -> 7 failed, 156 passed (TypeError unexpected kwarg 'kind', missing extra keys). test_read_plan_still_type_checks_known_fields passes already (regression guard).
GREEN: `./.venv/bin/python -m pytest packages/transmitter/tests_transmitter -q` -> 586 passed, 1 skipped. venv import confirmed inside worktree.
Files: layout.py, planner.py, site.py, publish.py, service.py, five test files, docs/playout-setup.md.
Self-review: no 3.12 syntax; Piece untouched; dataclasses.asdict no longer used in layout. The "extra" key in input JSON is not a known field-> not special-cased (treated as unknown field name excluded; it would be dropped on collision-free write? it is placed in extra under key "extra" and written back as "extra"). Concern: none material.
