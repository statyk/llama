import json, random, html, urllib.parse, os
S = os.path.dirname(os.path.abspath(__file__))
sample = json.load(open(f"{S}/sample.json"))
items = [(i, it) for i, it in enumerate(sample) if it["group"] not in ("song", "space")]
random.Random(3).shuffle(items)
rows = []
for n, (i, it) in enumerate(items, 1):
    url = "file://" + urllib.parse.quote(it["path"])
    m, s = divmod(it["dur"], 60)
    rows.append(f'''<div class="t" data-k="{i:03d}"><div class="h"><b>{n}.</b> {html.escape(it["slug"])} &mdash; <i>"{html.escape(it["title"])}"</i> ({m}:{s:02d})</div>
<audio controls preload="none" src="{url}"></audio>
<span class="j">{"".join(f'<button onclick="jump(this,{p})">{int(p*100)}%</button>' for p in (0.1,0.3,0.5,0.7,0.9))}</span>
<div class="l">{"".join(f'<label><input type="radio" name="k{i:03d}" value="{v}" onchange="save()"> {t}</label>' for v,t in [("song","song / real music"),("junk","junk (tuning, crowd, talk, silence)"),("mixed","mixed: junk AND a song"),("unsure","unsure")])}</div>
<input class="note" placeholder="note (optional)" oninput="save()"></div>''')
page = f'''<!DOCTYPE html><html><head><meta charset="utf-8"><title>Classifier spike: label {len(items)} tracks</title>
<style>body{{font:15px system-ui;max-width:900px;margin:2em auto;padding:0 1em}}.t{{border-top:1px solid #ccc;padding:.8em 0}}.h{{margin-bottom:.3em}}
audio{{width:420px;vertical-align:middle}}.j button{{font-size:12px;margin-left:2px}}.l label{{margin-right:1.2em}}.note{{width:60%;margin-top:.3em}}
#bar{{position:sticky;top:0;background:#fff;padding:.5em 0;border-bottom:2px solid #333}}</style></head><body>
<div id="bar"><b>Label each track by ear.</b> Order is shuffled; model scores are hidden on purpose. Progress saves in this browser. <span id="cnt"></span>
<button onclick="dl()">Download labels.json</button></div>
{"".join(rows)}
<script>
const KEY="clf-spike-labels";
function jump(b,p){{const a=b.closest('.t').querySelector('audio');const go=()=>{{a.currentTime=a.duration*p;a.play()}};if(isNaN(a.duration)){{a.preload='metadata';a.addEventListener('loadedmetadata',go,{{once:true}});a.load()}}else go()}}
function collect(){{const o={{}};document.querySelectorAll('.t').forEach(t=>{{const k=t.dataset.k,r=t.querySelector('input[type=radio]:checked'),n=t.querySelector('.note').value;if(r||n)o[k]={{label:r?r.value:null,note:n}}}});return o}}
function save(){{const o=collect();localStorage.setItem(KEY,JSON.stringify(o));document.getElementById('cnt').textContent=Object.values(o).filter(x=>x.label).length+" / {len(items)} labelled"}}
function load(){{const o=JSON.parse(localStorage.getItem(KEY)||"{{}}");for(const k in o){{const t=document.querySelector(`.t[data-k="${{k}}"]`);if(!t)continue;if(o[k].label){{const r=t.querySelector(`input[value="${{o[k].label}}"]`);if(r)r.checked=true}}t.querySelector('.note').value=o[k].note||""}}save()}}
function dl(){{const b=new Blob([JSON.stringify(collect(),null,1)],{{type:"application/json"}});const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download="labels.json";a.click()}}
document.addEventListener('play',e=>{{document.querySelectorAll('audio').forEach(a=>{{if(a!==e.target)a.pause()}})}},true);
load();
</script></body></html>'''
open(f"{S}/label.html", "w").write(page)
print(len(items), f"{S}/label.html")
