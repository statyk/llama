Write on-air DJ notes for a full-concert radio broadcast. {{style}}

Write for the ear, not the page: this script is read aloud by a synthetic
voice that puts the stress wherever the phrasing leads. Build each sentence so
the word that carries its point — the contrast, the surprise, the name — falls
at a natural stress position (usually near a clause or sentence end) rather
than buried mid-clause. Prefer wording where a listener's stress lands right
without any markup; e.g. "it wasn't even their best show that same week" (stress
on "week"), not a construction that invites stress on the wrong word.

Five hard rules for the broadcast:
- "Live" only where it cannot be read as the verb: "a live album", "a live
  recording", "recorded live", "played it live" are fine. Never "live in
  <place>", "live at <venue>" or "live from ...", and never open a sentence
  with "Live" — the voice says those like "to live". Write "recorded in
  Lincoln" or "on stage at the Pershing Center" instead.
- Segues in words, never symbols: say one song goes "into" the next — never
  write ">" (the voice reads it as "greater than"), and spell out "and" for
  "&". No symbols in the prose at all.
- No very short sentences: never a one- or two-word sentence (a bare "Here's
  set two." makes the voice garble). Fold short lines into fuller ones.
- Timeless: this broadcast may air years from now, so never anchor anything to
  the present — no "this year", "last month", "last November", "recently",
  "these days" or "next week", and no claims about how a band, person or
  venue is doing now. If the briefing dates something relative to when it
  was written, give the concrete year or leave it out. The broadcast may also
  air at any hour, so never give it a time of day — no "tonight", "this
  evening" or "this morning"; say "on this show" for the broadcast and "that
  night" for the concert. Time relative to the concert is fine ("the next
  year", "later that night", "a song they had only recently brought back",
  "seven months after this concert").
- Show ID in every break: every lead-in AND the outro must re-state the show's
  identity — artist, date, venue and/or city — at least once, so a listener
  tuning in mid-broadcast learns what they are hearing.

Names are the exception. The show's name, song and album titles, and the names
of bands, people, venues and places are always written exactly as they appear
in the show data or above, even where that breaks a rule here (e.g. "Me & Bobby
McGee", a song called "Tonight"). The rules still govern your own words around
a name: never use a title as licence to break a rule elsewhere in the sentence,
and where you can, put a name that would break a rule after other words rather
than opening a sentence with it.

{{narration_note}}Show data (JSON):
{{manifest_show_json}}

Briefing (your source material):
{{briefing_md}}

Write one lead-in per set: {{lead_in_sets}}. Each set's music is separated by
the lead-in that precedes it, so a lead-in is the only talk in that gap — no
separate show intro or set-break segments.
Write each lead-in and the outro as short paragraphs: one thought per
paragraph, typically two to four sentences. Separate paragraphs with a blank
line, written inside the JSON string as the escape \n\n —
never a raw line break inside a JSON string.
{{encore_note}}
{{feedback}}

Respond with ONLY JSON in this shape:
{"context": "<one line placing the show in its era/tour>",
 "set_intros": {<one key per set from: {{lead_in_sets}}>: "<the lead-in for that set. The FIRST set's lead-in also opens the broadcast — artist, date, venue, why this show earns airtime (~60-90 seconds) — then what to listen for. Each LATER set's lead-in briefly recaps the set just played, then teases this one (~30-45 seconds), and — like every break — re-states the show's identity (artist, date, venue and/or city) for anyone just tuning in>"},
 "outro": "<sign-off after the final music: recap the show including any encore, credit the recording source, invite listeners back for another show without saying when; re-state the show's identity (artist, date, venue and/or city) once more>",
 "mentioned_songs": [<every song title referenced anywhere above, spelled exactly as in the show data>]}
Raw JSON only.
