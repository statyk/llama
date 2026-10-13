# Your seat: CODE QUALITY
Judge whether the change is well built, assuming the spec reviewer handles requirement coverage:
- correctness and edge cases (especially failure paths: exceptions, absent/corrupt state, races, timeouts);
- error handling (no swallowed errors; fail closed on the spend surface);
- tests: do they verify real behaviour, pin the constraint they claim, and would they fail if the code were
  wrong? (a test that cannot fail is Important);
- structure: one responsibility per file, clean interfaces, DRY without premature abstraction, matches the
  plan's file structure, follows surrounding idiom;
- public-repo hygiene: no account ID, zone ID, token, key or email address (except alerts@lma-radio.com)
  in any committed file; no test reaches the network (every fetch injected).
