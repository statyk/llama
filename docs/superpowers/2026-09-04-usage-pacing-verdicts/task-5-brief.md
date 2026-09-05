### Task 5: Duration parsing and the `[pacing]` config table

**Files:**
- Create: `packages/llama/src/llama/pacing.py`
- Create: `packages/llama/tests/test_pacing.py`
- Modify: `packages/llama/src/llama/config.py` (add `PacingConfig`, the `Config.pacing` field, and the `DEFAULT_CONFIG_TOML` block)
- Modify: `packages/llama/tests/test_config.py` (only if the template test needs the new block listed; run it and see)

**Interfaces:**
- Consumes: nothing.
- Produces: `parse_duration(text: str) -> float` (seconds, raises `ValueError`); `format_delta(seconds: float) -> str`; `sleep_until(when: datetime, echo) -> None`; module-level `_sleep` and `_now` indirections for tests. `PacingConfig` with fields `enabled: bool`, `wait: bool`, `max_wait: str`, `unknown_reset_wait: str`, `reset_skew: str`, and `Config.pacing`.

- [ ] **Step 1: Write the failing test**

Create `packages/llama/tests/test_pacing.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest

from llama import pacing
from llama.config import Config, PacingConfig


def test_parse_duration_accepts_the_documented_forms():
    assert pacing.parse_duration("6h") == 6 * 3600
    assert pacing.parse_duration("90m") == 90 * 60
    assert pacing.parse_duration("5h30m") == 5 * 3600 + 30 * 60
    assert pacing.parse_duration("45s") == 45


def test_parse_duration_rejects_nonsense():
    for bad in ("", "soon", "6", "-2h", "6x"):
        with pytest.raises(ValueError):
            pacing.parse_duration(bad)


def test_format_delta_is_human_readable():
    assert pacing.format_delta(4 * 3600 + 12 * 60) == "4h 12m"
    assert pacing.format_delta(90) == "1m"


def test_sleep_until_naps_in_chunks_and_reports(monkeypatch):
    start = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)
    clock = {"now": start}
    monkeypatch.setattr(pacing, "_now", lambda: clock["now"])
    monkeypatch.setattr(pacing, "_sleep",
                        lambda s: clock.update(now=clock["now"] + timedelta(seconds=s)))
    said = []
    pacing.sleep_until(start + timedelta(hours=1), echo=said.append, chunk_s=900)
    assert clock["now"] >= start + timedelta(hours=1)
    assert len(said) == 3          # reports after each of the first three naps


def test_sleep_until_returns_at_once_when_the_time_has_passed(monkeypatch):
    now = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(pacing, "_now", lambda: now)
    monkeypatch.setattr(pacing, "_sleep", lambda s: pytest.fail("should not sleep"))
    pacing.sleep_until(now - timedelta(minutes=1), echo=lambda m: None)


def test_pacing_config_defaults_are_parseable():
    cfg = PacingConfig()
    assert cfg.enabled is True and cfg.wait is True
    assert pacing.parse_duration(cfg.max_wait) == 6 * 3600
    assert pacing.parse_duration(cfg.unknown_reset_wait) == 3600
    assert Config().pacing.max_wait == "6h"


def test_pacing_config_rejects_an_unparseable_duration():
    with pytest.raises(Exception):
        PacingConfig(max_wait="whenever")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_pacing.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'llama.pacing'`

- [ ] **Step 3: Write minimal implementation**

Create `packages/llama/src/llama/pacing.py`:

```python
"""Waiting out a usage window.

Phase 1 is the reactive half only: llama learns the reset time from the
backend's own refusal (herder.limits) and either sleeps through it or
checkpoints. The proactive half - reading Claude Code's usage cache,
projecting per-show cost, pausing BEFORE a window is exhausted - is
phase 2 and deliberately absent here.
"""
import re
import time
from datetime import datetime, timezone

_DURATION_RE = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$")

_sleep = time.sleep                                  # indirection for tests
def _now() -> datetime:                              # noqa: E302 - paired with _sleep
    return datetime.now(timezone.utc)


def parse_duration(text: str) -> float:
    """Seconds from `6h`, `90m`, `5h30m`, `45s`. Raises ValueError otherwise."""
    m = _DURATION_RE.match((text or "").strip())
    if not m or not any(m.groups()):
        raise ValueError(f"not a duration: {text!r} (use forms like 6h, 90m, 5h30m)")
    hours, minutes, seconds = (int(g or 0) for g in m.groups())
    return hours * 3600 + minutes * 60 + seconds


def format_delta(seconds: float) -> str:
    """`4h 12m` / `12m` / `1m` - never bare seconds, which read as noise."""
    total = max(int(seconds), 60)
    hours, minutes = divmod(total // 60, 60)
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"


def sleep_until(when: datetime, echo, chunk_s: float = 900) -> None:
    """Sleep until `when`, reporting what is left after each nap.

    Chunked so a multi-hour wait is not a dead prompt, and so a
    KeyboardInterrupt lands promptly. The caller handles that interrupt.
    """
    while True:
        remaining = (when - _now()).total_seconds()
        if remaining <= 0:
            return
        _sleep(min(remaining, chunk_s))
        left = (when - _now()).total_seconds()
        if left > 0:
            echo(f"  … waiting, {format_delta(left)} left")
```

In `packages/llama/src/llama/config.py`, add near the other nested config models (after `ArtistsConfig`):

```python
class PacingConfig(BaseModel):
    """Waiting out an exhausted usage window (see llama/pacing.py).

    Durations are strings so the config reads in the units a human thinks
    in; they are validated at load time rather than at the point of use, so
    a typo fails `llama get` immediately instead of four shows in.
    """
    enabled: bool = True
    wait: bool = True
    max_wait: str = "6h"
    unknown_reset_wait: str = "1h"
    reset_skew: str = "2m"

    @field_validator("max_wait", "unknown_reset_wait", "reset_skew")
    @classmethod
    def _durations_parse(cls, v: str) -> str:
        from llama.pacing import parse_duration
        parse_duration(v)
        return v
```

Add `field_validator` to the pydantic import at the top of `config.py` if it is not already imported, and add the field to `Config`:

```python
    pacing: PacingConfig = Field(default_factory=PacingConfig)
```

Append to `DEFAULT_CONFIG_TOML`, after the `[winnow]` block:

```toml

[pacing]
# When the backend refuses because a usage window is exhausted, wait it out
# instead of failing every remaining show. Set enabled = false to restore the
# old behaviour (the run fails the show and moves on).
enabled = true

# Sleep through the wait (true) or checkpoint the session and exit 0 (false).
# Either way the run resumes with `llama run resume <name>`; stages skip work
# already done, so resuming costs nothing for shows already packaged.
wait = true

# Never sleep longer than this. A wait beyond it checkpoints instead - which
# is what keeps a 7-day window from parking the process for days. Raise it
# (e.g. --max-wait 30h) to deliberately wait out a weekly reset.
max_wait = "6h"

# How long to wait when the refusal names no reset time.
unknown_reset_wait = "1h"

# Added to the reset instant before resuming, so we do not race the window.
reset_skew = "2m"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest packages/llama/tests/test_pacing.py packages/llama/tests/test_config.py -q`
Expected: all pass. If `test_default_config_template_matches_defaults` fails, the TOML block above does not match the model defaults — fix the block, not the test.

- [ ] **Step 5: Commit**

```bash
git add packages/llama/src/llama/pacing.py packages/llama/src/llama/config.py packages/llama/tests/test_pacing.py
git commit -m "feat(llama): add [pacing] config and duration/sleep helpers"
```

---

