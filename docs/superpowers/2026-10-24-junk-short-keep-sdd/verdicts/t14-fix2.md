# t14-fix2 handback
Status: DONE. Commit a756350.
Correction: my round-1 report wrongly said plan_reuse ran once per sampled show; it ran twice. Now fixed and pinned.
Changes (scripts/short_keep_probe.py): the byte-sum loop stores the plan and its monotonic duration per show; the sample loop reuses that plan (no second call); wall = first-call time + duration reads. After the scan, delivery_path is re-checked and a Refusal (exit 2, nothing written) is raised if it is no longer a directory.
Tests (written first): test_reuse_check_plans_each_changed_show_exactly_once, test_reuse_check_refuses_when_the_share_drops_mid_scan.
RED (before fix): 2 failed, 46 passed. Failures: "assert ['s0','s0',...] == ['s0','s1','s2','s3'] ... Left contains 4 more items" and "assert 0 == 2" (main returned 0).
GREEN: ./.venv/bin/python -m pytest scripts/test_short_keep_probe.py -q -> 48 passed in 1.11s.
Full: ./.venv/bin/python -m pytest -q -p no:cacheprovider -> 5076 passed, 1 skipped, 8 deselected, 26 warnings in 87.01s.
