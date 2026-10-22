# llama bugs found during the overnight run (2026-10-21)

1. `llama fix` with an invalid structure combo (`--set-breaks 10,20 --set-encore 20`) writes overrides.json,
   then gather refuses -- but the redo has ALREADY dropped show.json/notes/reviews (drop_stage_artifacts
   runs before the validation fails). The show is left with no show.json.
2. After that, every `llama fix` on the show fails, because fix validates the EXISTING overrides before
   applying the new edit (even `--set-breaks 10`, which would make it valid). Recovery needed a hand edit
   of overrides.json (billystrings-2021-12-04; backup in apply/billystrings-2021-12-04.overrides.bak).
   Fix: validate the edited overrides, and validate before writing/dropping anything.
3. vet: yearless asserted dates never get the +-1 day window (vet_research._date_flags, ~14/160 sample).
4. jerrybase data: Phil Lesh & Friends rows are frequently one-set lumps (2001-02-18, 2001-07-07, 2001-12-31,
   2007-10-07, 2008-07-04, 2008-11-18, 2008-12-31 ...) that contradict tapers' explicit set headers and
   setlist.fm, so anchoring removes correct breaks and the set-count tripwire re-holds after every fix.
   Candidate rule: never let anchoring reduce a structure below explicit description set headers; or
   exclude/flag PLF one-set rows. (DSO and 1970 Dead rows showed the same shape less often.)
