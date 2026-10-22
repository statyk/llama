# t7b-fix1: DONE
Commit a892b7a. scripts/test_replay_holds.py 70 passed; full suite 4427 passed (see log).
I1: rows now print "labels: before 1x2 2x1 | after ... | stored ..." plus breaks; numbered<->encore change at same positions tiers as "songs moved" (chosen over a new tier so it gets the full pre-screen); test_taper_changes_numbered_to_encore_is_not_a_plain_rename_and_rows_show_labels.
M1: stored-llm section excludes unreplayable; test_stored_llm_section_excludes_an_unreplayable_candidate.
M2: --config validated (and loaded) up front before any write; summary line "voiced check: delivery_path P" / "off"; test_compare_refuses_a_missing_config_before_writing_and_summary_names_delivery. Side effect: compare now always reads the default config, so an autouse fixture in the test file points rh.DEFAULT_ROOT at a temp dir (no existing test changed).
M4: step1 printed as "overruled:" only when before != after else "step1:"; test_provenance_only_row_says_step1_not_overruled.
Deferred minors 3,5,6 untouched.
