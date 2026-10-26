
## Output format
First line: `Foundation: SOUND | UNVERIFIED | PROBLEM — <one sentence>`. PROBLEM means a premise
the design rests on is contradicted by evidence you can cite and the design misses its goal
because of it; this line is not subject to the stakes guidance on severity.

Then findings, most severe first:
- **[Critical|Important|Minor] Short title**
  - Where: section heading plus a short exact quote
  - Problem: one or two sentences
  - Evidence: file:line, or the conflicting quote
  - Failure scenario: concrete inputs or situation, and what goes wrong
  - Setup and likelihood: the setup it needs and how likely it is
  - Suggested fix: one sentence, and roughly what it adds or removes
Then `### Unverified premises`: each claim the design depends on that the evidence here cannot
confirm, with the cheapest test that would settle it (or `none`).
End with: `TOTAL: <n> findings (<c> Critical, <i> Important, <m> Minor)`.
