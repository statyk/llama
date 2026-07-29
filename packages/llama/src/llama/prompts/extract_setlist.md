Extract the setlist from this archive.org concert-item description.

Description:
{{description}}

Respond with ONLY JSON in this shape:
{"items": [{"title": "<song title as written>",
            "normalized": "<lowercase, punctuation and apostrophes removed>",
            "set": "1" | "2" | "3" | "encore",
            "segue": true | false}],
 "confidence": "high" | "medium" | "low"}

Rules:
- Preserve stage order exactly.
- segue=true when a song runs directly into the next (marked ">" or "->" or "seg.").
- If the description shows songs but no set markings, put everything in set "1" and use
  confidence "medium".
- If you cannot find a setlist at all, return {"items": [], "confidence": "low"}.
- Ignore lineage, transfer, taper, and equipment notes — they are not songs.
Raw JSON only.
