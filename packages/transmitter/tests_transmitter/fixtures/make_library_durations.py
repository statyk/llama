"""Generate `library_durations.json`: a deterministic ~300-show library whose
per-profile lengths reproduce the delivered library measured 2026-10-25
(scheduler spec, "Intent").

Run from anywhere: `python make_library_durations.py` rewrites the JSON next to
this file. Re-running reproduces it byte for byte: lengths are lognormal
quantiles (no randomness), and artists, dates and order come from a fixed-seed
`random.Random`.

Counts are the measured delivered counts scaled to 300 (country kept at its
real 2, the scarce pool). Medians are the measured ones. Spreads (lognormal
sigma) are the measured p10/p90 for dead (136/213 min -> 0.175) and builder
choices for the rest, recorded in PROFILES below.
"""

import calendar
import json
import math
import random
import re
from pathlib import Path
from statistics import NormalDist

SEED = 20261025
OUT = Path(__file__).with_name("library_durations.json")
MIN_MINUTES, MAX_MINUTES = 30.0, 330.0
FRAMES_PER_MINUTE = 60 * 44_100 / 1024

# profile: (count, median minutes, lognormal sigma, (first year, last year), artists)
PROFILES = {
    "dead": (44, 168, 0.175, (1966, 1995), ["Grateful Dead"]),
    "indie": (35, 89, 0.30, (1994, 2015), [
        "Elliott Smith", "Built to Spill", "Modest Mouse", "Godspeed You! Black Emperor",
        "Yo La Tengo"]),
    "americana": (35, 110, 0.25, (1995, 2019), [
        "Drive-By Truckers", "Old Crow Medicine Show", "Gillian Welch", "Son Volt", "Wilco"]),
    "bluegrass": (33, 135, 0.25, (1998, 2019), [
        "Greensky Bluegrass", "Yonder Mountain String Band", "Railroad Earth",
        "Trampled by Turtles", "The Infamous Stringdusters"]),
    "southern": (30, 117, 0.25, (1970, 2019), [
        "Allman Brothers Band", "Tedeschi Trucks Band", "Derek Trucks Band",
        "North Mississippi Allstars", "Rose Hill Drive"]),
    "jam": (26, 168, 0.30, (1992, 2018), [
        "moe.", "String Cheese Incident", "Umphrey's McGee", "Widespread Panic"]),
    "livetronica": (25, 155, 0.25, (1999, 2019), [
        "Lotus", "Sound Tribe Sector 9", "The Disco Biscuits", "Particle"]),
    "dead-family": (24, 180, 0.20, (1975, 2014), [
        "Jerry Garcia Band", "Phil Lesh & Friends", "Ratdog", "Furthur"]),
    "funk": (24, 119, 0.25, (1996, 2019), [
        "Lettuce", "Soulive", "The New Mastersounds", "Galactic", "Karl Denson's Tiny Universe"]),
    "dead-tribute": (22, 170, 0.20, (1998, 2019), [
        "Dark Star Orchestra", "Joe Russo's Almost Dead", "Cubensis"]),
    "country": (2, 125, 0.20, (2000, 2012), ["Hank Williams III", "Wayne Hancock"]),
}


def _minutes(n: int, median: float, sigma: float) -> list[float]:
    """n stratified lognormal quantiles: the sample median is the measured median."""
    z = NormalDist()
    out = []
    for i in range(n):
        q = (i + 0.5) / n
        m = median * math.exp(sigma * z.inv_cdf(q))
        out.append(min(MAX_MINUTES, max(MIN_MINUTES, m)))
    return out


def _slug(artist: str) -> str:
    return re.sub(r"[^a-z0-9]", "", artist.lower())


def build() -> list[dict]:
    rng = random.Random(SEED)
    rows: list[dict] = []
    slugs: set[str] = set()
    for profile, (count, median, sigma, (y0, y1), artists) in PROFILES.items():
        lengths = _minutes(count, median, sigma)
        rng.shuffle(lengths)
        for i, minutes in enumerate(lengths):
            artist = artists[i % len(artists)] if i < len(artists) else rng.choice(artists)
            while True:
                year = rng.randint(y0, y1)
                month = rng.randint(1, 12)
                day = rng.randint(1, calendar.monthrange(year, month)[1])
                date = f"{year:04d}-{month:02d}-{day:02d}"
                slug = f"{_slug(artist)}-{date}"
                if slug not in slugs:
                    break
            slugs.add(slug)
            rows.append({"slug": slug, "artist": artist, "date": date, "profile": profile,
                         "frames": round(minutes * FRAMES_PER_MINUTE)})
    rows.sort(key=lambda r: r["slug"])
    return rows


def main() -> None:
    OUT.write_text(json.dumps(build(), indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
