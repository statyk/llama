Write on-air DJ notes for a full-concert radio broadcast. {{style}}

Write for the ear, not the page: this script is read aloud by a synthetic
voice that puts the stress wherever the phrasing leads. Build each sentence so
the word that carries its point — the contrast, the surprise, the name — falls
at a natural stress position (usually near a clause or sentence end) rather
than buried mid-clause. Prefer wording where a listener's stress lands right
without any markup; e.g. "it wasn't even their best show that same week" (stress
on "week"), not a construction that invites stress on the wrong word.

Three hard rules for spoken delivery:
- Segues in words, never symbols: say one song goes "into" the next — never
  write ">" (the voice reads it as "greater than"), and spell out "and" for
  "&". No symbols in the prose at all.
- No very short sentences: never a one- or two-word sentence (a bare "Here's
  set two." makes the voice garble). Fold short lines into fuller ones.
- Show ID in every break: every lead-in AND the outro must re-state the show's
  identity — artist, date, venue and/or city — at least once, so a listener
  tuning in mid-broadcast learns what they are hearing.

{{narration_note}}Show data (JSON):
{{show_json}}

Research findings:
{{research}}

Listener review excerpts:
{{reviews_digest}}

Write one lead-in per set: {{lead_in_sets}}. Each set's music is separated by
the lead-in that precedes it, so a lead-in is the only talk in that gap — no
separate show intro or set-break segments.
{{encore_note}}
{{feedback}}

Respond with ONLY JSON in this shape:
{"context": "<one line placing the show in its era/tour>",
 "set_intros": {<one key per set from: {{lead_in_sets}}>: "<the lead-in for that set. The FIRST set's lead-in also opens the broadcast — artist, date, venue, why this show earns airtime (~60-90 seconds) — then what to listen for. Each LATER set's lead-in briefly recaps the set just played, then teases this one (~30-45 seconds), and — like every break — re-states the show's identity (artist, date, venue and/or city) for anyone just tuning in>"},
 "outro": "<sign-off after the final music: recap the show including any encore, credit the recording source, invite listeners to the next broadcast; re-state the show's identity (artist, date, venue and/or city) once more>",
 "mentioned_songs": [<every song title referenced anywhere above, spelled exactly as in the show data>]}
Raw JSON only.
