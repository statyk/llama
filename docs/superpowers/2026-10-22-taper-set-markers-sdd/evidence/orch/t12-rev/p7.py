from llama.models import Track
from llama.taper import decide_taper
def mk(ts): return [Track(index=i+1, set="1", title=t, filename=f"t{i+1:02d}.mp3", title_source="tags") for i,t in enumerate(ts)]
text = "Set 1\n1. Bertha\n2. Sugaree\n3. Jack Straw, Ripple\nSet 2\n4. Scarlet Begonias\n5. Fire on the Mountain\n"
cases = {
 'separate tracks': ["Bertha","Sugaree","Jack Straw","Ripple","Scarlet Begonias","Fire on the Mountain"],
 'tape merges Ripple into set-2 opener': ["Bertha","Sugaree","Jack Straw","Ripple > Scarlet Begonias","Fire on the Mountain"],
 'tape lacks Ripple': ["Bertha","Sugaree","Jack Straw","Scarlet Begonias","Fire on the Mountain"],
}
for name, ts in cases.items():
    today = ["1"]*len(ts)
    d = decide_taper(mk(ts), {"description": text}, aliases={}, today_sets=today)
    print(name, '->', d.placement.sets if d.placement else None, d.reason)
