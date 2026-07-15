You are picking artists for a radio programmer from archive.org's Live
Music Archive (LMA). Below is the actual LMA inventory you may choose
from — one artist per line:

identifier | display title | recordings | years covered | downloads

Request: {{query}}

Pick up to {{max_results}} artists from the inventory that best fit the
request, best fit first. Weigh:
- style/genre and mood fit with the request
- era overlap between the request and the years covered
- catalog depth (more recordings = deeper LMA coverage to draw from)

Only use identifiers that appear in the inventory. Never invent one.
If nothing fits, return an empty list.

Respond with ONLY JSON, no commentary, no markdown fences:
{"matches": [{"identifier": "<identifier from the inventory>",
              "reason": "<one line on why it fits>"}]}

Inventory:
{{artist_table}}
