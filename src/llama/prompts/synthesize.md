Write on-air DJ notes for a full-concert radio broadcast. {{style}}

Show data (JSON):
{{show_json}}

Research findings:
{{research}}

Listener review excerpts:
{{reviews_digest}}

Write one lead-in per set: {{lead_in_sets}}. Each set's music is separated by
the lead-in that precedes it, so a lead-in is the only talk in that gap — no
separate show intro or set-break segments. {{encore_note}}
{{feedback}}

Respond with ONLY JSON in this shape:
{"context": "<one line placing the show in its era/tour>",
 "set_intros": {<one key per set from: {{lead_in_sets}}>: "<the lead-in for that set. The FIRST set's lead-in also opens the broadcast — artist, date, venue, why this show earns airtime (~60-90 seconds) — then what to listen for. Each LATER set's lead-in briefly recaps the set just played, then teases this one (~30-45 seconds)>"},
 "outro": "<sign-off after the final music: recap the show including any encore, credit the recording source, invite listeners to the next broadcast>",
 "mentioned_songs": [<every song title referenced anywhere above, spelled exactly as in the show data>]}
Raw JSON only.
