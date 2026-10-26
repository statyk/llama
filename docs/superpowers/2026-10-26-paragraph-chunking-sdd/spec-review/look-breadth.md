
## What to look for
1. Interfaces: trace every output to its consumer; flag misreadings and anything undefined
   an implementer would have to invent.
2. Idioms implementers will copy that undermine the goals.
3. Safety: anything weakening the strict surfaces.
4. Consistency and ambiguity; claims about existing code (check them against the code).
5. Fitness for the target environment.
6. Design: right approach? missing, over-built, or likely to sprawl?
7. Premises: the claims the design rests on — the diagnosis of the cause, the environment,
   scale and where the bottleneck is, how existing code behaves, what the requester needs.
   Check each against the evidence you can read.
Anything you find unclear is a finding.
