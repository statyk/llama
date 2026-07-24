Write on-air DJ notes for a full-concert radio broadcast. {{style}}

Show data (JSON):
{{show_json}}

Research findings:
{{research}}

Listener review excerpts:
{{reviews_digest}}

This show has these sets: {{sets}}. There are {{n_breaks}} set break(s).
{{feedback}}

Respond with ONLY JSON in this shape:
{"context": "<one line placing the show in its era/tour>",
 "intro": "<60-90 seconds of spoken copy: artist, date, venue, why this show earns airtime>",
 "set_intros": {<one key per set from: {{sets}}>: "<20-40 seconds: what to listen for>"},
 "set_break_notes": [<exactly {{n_breaks}} strings: recap the set just played, tease the next>],
 "outro": "<sign-off after the encore: recording source credit, invitation to next broadcast>",
 "mentioned_songs": [<every song title referenced anywhere above, spelled exactly as in the show data>]}
Raw JSON only.
