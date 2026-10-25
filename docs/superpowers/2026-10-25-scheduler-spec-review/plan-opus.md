Plan review Opus: 1 C, 3 I, 12 m.
P-O1 [C] continuation: re-projection restarts at occurrence containing start_frame; early-landing block X re-filled (k>=1 forced) or max_shows reached -> no options/empty min. Fix: continuing occurrence = last persisted show row's occurrence while its next can still land; placed = fixed prefix, 0..max-placed more, fill after prefix allowed; test step-by-step append == one projection.
P-O2 [I] Recency not updated within one extend -> repeats same show/ID on multi-row extend. Update Recency per appended row; test.
P-O3 [I] clock loads clean but crashes: template typos/str.format, wiggle 0 div-by-zero, days=[]. Validate at load (format with dummies; one-forms no next_*; wiggle>0 or early+late>0; days non-empty).
P-O4 [I] projection cost unbounded, no watchdog: live projection limit current+2 occurrences; prefilter pair partners by length range; notify per projection; timing test 3000 pool.
P-O5 [m] open max_shows 6 cap vs implicit 24h block -> misses; no cap for open, implicit always in window.
P-O6 [m] schedule/status/announcements write (last-good, alerts, clip analysis cache). Read-only mode.
P-O7 [m] phase-1 history package None -> package = row.package or row.slug.
P-O8 [m] absorbed occurrences not counted as misses -> record on next block's first row (absorbed) + measurement.
P-O9 [m] tier1 >=1 own show vs spec "avoid overrun when alternative exists" -> operator interpretation.
P-O10 [m] nonexistent-time procedure contradicts test -> "first UTC instant whose local wall time >= requested".
P-O11 [m] two-block failing only on Y fallback to one-block: state + test.
P-O12 [m] measurement weeks not chained.
P-O13 [m] Task1 rejects unknown kind -> accept any string kind; unknown not renderable.
P-O14 [m] fidelity: schedule missing-audio line; announcements --days extra; scan_delivered key; mean vs summed score; bend-order test.
P-O15 [m] interfaces: build_pool return dropped; history step not in ran/STEP_CODES; role ann vs next/later; boundary_frames with no IDs = one gap; defaults for announce/open/rotation; Station live field vs clock(); to_json no asdict w/ MappingProxy.
P-O16 [m] executability: cli line refs; npm ci; runbook naming task number; mutation bytecode isolation + removal mutant; move Task 13 before Task 10.
