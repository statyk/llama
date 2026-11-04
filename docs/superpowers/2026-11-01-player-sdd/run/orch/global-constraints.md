## Global Constraints

- Nothing billed per listener: every new listener request is a static object from the edge cache. No Worker route. No third-party request.
- All untrusted text reaches the page as text: escaped on the server, `textContent` in the browser, never `innerHTML`.
- A link is emitted only for a URL starting with the literal `https://archive.org/`; otherwise the button is left out.
- Every ticket, notes and share URL is built from the encoded slug. The file's `notes` and `page` fields are never read.
- `antenna/public/player.js`, `nowplaying.js` and `style.css` stay byte-for-byte unchanged and stay published.
- `antenna/src/` changes only through `npm run pages` regenerating `src/pages.ts`.
- `/assets/` returns 403 while blocked, so `offair.html` uses inline styles, system fonts and no scripts. The kill-switch rule does not change.
- Concert dates are formatted from the string, never through `Date`. Blank fields are left out, never printed as "null".
- Palette: cream paper, tape brown, oxblood, muted teal. No rainbow, no Internet Archive branding.
- Exact copy: "Live concert tapes from the Live Music Archive, around the clock."; "Show notes are AI generated and may contain mistakes."; "Hear the full tape on archive.org"; "LMA RADIO PRESENTS"; "GEN ADM"; "Open the show page"; "No notes yet."; "<artist> is on the air. Press Play."; "Reconnecting…"; "Lost the stream."; "The station is off the air."; "Playback was blocked."; "This browser can't play the stream; open the stream URL in VLC."; keys "Play" and "Stop".
- `site.py` runs on Python 3.11 and transmitter never imports llama or emcee.
