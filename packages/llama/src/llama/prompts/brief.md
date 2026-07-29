Write a neutral, factual briefing on a full-concert recording for a radio
scriptwriter. The reader has never heard of this show; the briefing must be
thorough enough that they can write an on-air script from it alone. This is a
reference document, not a script: plain informative prose, no address to
listeners, no radio patter.

Register rules:
- Strictly neutral: no first-person voice, no enthusiasm of your own, no
  hype adjectives asserted in your own voice.
- Opinions appear ONLY as attributed sentiment ("reviewers describe...",
  "tapers regard..."), never as the briefing's own judgment.
- Every fact — dates, venue, songs, set structure, personnel, events on
  stage — must come from the inputs below. Do not invent anything.
- Note in `cautions` anything a scriptwriter must know before asserting
  facts on air: thin or conflicting research, corrected dates, vetting
  flags, uncertain structure.

{{narration_note}}Show data (JSON):
{{show_json}}

Research findings:
{{research}}

Vetting notes (the research above was checked against the show data):
{{vetting}}

Listener review excerpts:
{{reviews_digest}}
{{feedback}}

Respond with ONLY JSON in this shape:
{"context": "<a short paragraph placing the show in its era/tour/venue>",
 "significance": "<a short paragraph on why this show is worth airtime>",
 "per_set": {<one key per set label found in the show data (e.g. "1", "2",
   "encore")>: ["<talking point grounded in the inputs>", ...]},
 "notable_moments": ["<specific highlight grounded in research/reviews>", ...],
 "review_sentiment": "<summary of reception: who praises it and for what>",
 "non_attendee_sentiment": <true iff the sentiment includes voices who were
   not at the show>,
 "cautions": ["<caveat the scriptwriter needs>", ...],
 "narration": "full",
 "mentioned_songs": [<every song title referenced anywhere above, spelled
   exactly as in the show data>]}
Raw JSON only.
