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
3. asserted_set_count: the total number of sets the document asserts THIS
   performance comprised, only when it states a total outright ("both sets"
   → 2, "all three sets" → 3). An encore is not a set — "two sets plus an
   encore" → 2. Passing ordinal references ("during the second set") do not
   establish a total; use null for those and whenever no count is stated.
4. context: one line placing the show in its era/tour, built only from the
   document's claims.

Respond with ONLY JSON in this shape:
{"asserted_songs": ["<title>", ...],
 "asserted_dates": ["<date exactly as written>", ...],
 "asserted_set_count": <integer or null>,
 "context": "<one line>"}
Raw JSON only.
