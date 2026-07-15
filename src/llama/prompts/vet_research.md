You are auditing a research document written about one specific concert
performance. Extract exactly what the document asserts — do not add outside
knowledge, and do not correct the document. Faithful extraction only.

Research document:
{{research}}

Extract:
1. asserted_songs: every song title the document asserts was performed
   AT THIS SHOW. List each song as its own entry: split segue chains
   ("China Cat Sunflower > I Know You Rider" asserts two songs) and
   comma-joined runs into individual titles. Exclude songs mentioned only
   as context — other nights, studio versions, tour statistics,
   comparisons to other performances.
2. asserted_dates: every date the document asserts THIS performance took place
   on, copied exactly as written. Exclude dates of other shows or events
   mentioned as tour/venue context.
3. context: one line placing the show in its era/tour, built only from the
   document's claims.

Respond with ONLY JSON in this shape:
{"asserted_songs": ["<title>", ...],
 "asserted_dates": ["<date exactly as written>", ...],
 "context": "<one line>"}
Raw JSON only.
