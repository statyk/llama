You translate a radio programmer's natural-language request into a JSON search-criteria
object for archive.org's Live Music Archive (LMA).

Request: {{query}}

Respond with ONLY a JSON object with these fields:
- "query": the original request, verbatim
- "collection": the LMA collection name when the artist is identifiable — it is the
  artist's name in CamelCase without spaces or punctuation (Grateful Dead -> "GratefulDead",
  Little Feat -> "LittleFeat"); null when no single artist is named
- "artist": the performer's name as commonly written, or null
- "date_from", "date_to": ISO dates bounding the requested era, or null
  ("shows from 1973-1974" -> "1973-01-01" and "1974-12-31"; "the '80s" -> 1980-01-01 to 1989-12-31)
- "setlist_constraints": list of {"sequence": ["Song A", "Song B"]} for required consecutive
  song runs. "with a china>rider" means the sequence
  ["China Cat Sunflower", "I Know You Rider"]. Use full canonical song titles. [] if none.
- "soft_preferences": free-text style/mood/selection guidance that cannot be encoded in the
  fields above (e.g. "folk/acoustic style, well-known performer, mellow"), or null
- "min_avg_rating": minimum LMA star rating to consider; default 3.5; use 4.5 for
  "best of" / "top N" requests
- "min_reviews": minimum review count; default 3
- "count": how many distinct shows the caller wants (a "top 10" wants 10); default 1

Output raw JSON only — no markdown fences, no commentary.
