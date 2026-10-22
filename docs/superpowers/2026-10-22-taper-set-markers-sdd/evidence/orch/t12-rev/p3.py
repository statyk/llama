from llama.structure import fuzzy_norm_title as n, fuzzy_title_eq as eq, title_components as tc
from llama.songs import DEFAULT_ALIASES as A
pairs = [("Not Fade Away, Goin' Down the Road", "Not Fade Away"),
         ("Not Fade Away, Goin' Down the Road", "Goin' Down the Road Feeling Bad"),
         ("Sugar Magnolia, Sunshine Daydream", "Sugar Magnolia"),
         ("Sugar Magnolia, Sunshine Daydream", "Sugar Magnolia > Sunshine Daydream"),
         ("Jack Straw, Ripple", "Jack Straw"),
         ("Jack Straw, Ripple", "Ripple"),
         ("Quantico, VA", "Quantico"),
         ]
for a,b in pairs:
    print(repr(a), repr(b), n(a,A), '|', n(b,A), eq(n(a,A), n(b,A)), [eq(c, n(a,A)) for c in tc(b,A)])
