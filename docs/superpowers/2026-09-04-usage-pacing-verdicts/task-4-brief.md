### Task 4: Stop retrying a rate limit as transport noise

Today a limit hit burns three attempts and 10 s of backoff per show. This is a standalone bug fix.

**Files:**
- Modify: `packages/herder/src/herder/tasks.py:36`
- Modify: `packages/herder/tests/test_llm_tasks.py`

**Interfaces:**
- Consumes: `RateLimited` (Task 2).
- Produces: no new API; `_with_transport_retry` re-raises `RateLimited` on the first raise.

- [ ] **Step 1: Write the failing test**

Append to `packages/herder/tests/test_llm_tasks.py`:

```python
from herder.limits import RateLimited


class CountingLimitProvider:
    """Raises a rate limit every time, counting attempts."""

    def __init__(self):
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        raise RateLimited("You've hit your session limit", scope="five_hour")

    def research(self, brief: str) -> str:
        return self.complete(brief)


def test_rate_limit_is_not_retried_as_transport_noise(monkeypatch):
    # Retrying is not merely useless here, it spends three more calls
    # against a window that has none left.
    slept = []
    monkeypatch.setattr(tasks, "_sleep", lambda s: slept.append(s))
    provider = CountingLimitProvider()
    with pytest.raises(RateLimited):
        tasks.run_json_task(provider, "brief", Answer, template="hi")
    assert provider.calls == 1
    assert slept == []


def test_rate_limit_propagates_from_a_research_task(monkeypatch):
    monkeypatch.setattr(tasks, "_sleep", lambda s: None)
    provider = CountingLimitProvider()
    with pytest.raises(RateLimited):
        tasks.run_research_task(provider, "deep_research", template="hi")
    assert provider.calls == 1
```

That file already imports `pytest` and `tasks` (via `from herder import FakeProvider, HerderError, ResearchNotSupported, TaskFailed, tasks`) and defines the schema `Answer(BaseModel)` with a single `value: int` field. Reuse those; add only the `RateLimited` import.

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest packages/herder/tests/test_llm_tasks.py -q -k rate_limit`
Expected: FAIL — `assert 3 == 1`, because the retry loop swallows it twice before propagating.

- [ ] **Step 3: Write minimal implementation**

In `packages/herder/src/herder/tasks.py`, add to the imports:

```python
from herder.limits import RateLimited
```

Change line 36 from:

```python
        except (TaskFailed, ResearchNotSupported):
```

to:

```python
        except (TaskFailed, ResearchNotSupported, RateLimited):
```

And extend the docstring's final sentence so the reason travels with the code:

```python
    """Call a provider, retrying transient backend failures verbatim.

    Deliberately does NOT escalate the ladder or amend the prompt: a dropped
    connection is not evidence the model needed to be smarter, and paying for
    a tier upgrade over a network blip is the wrong reflex. TaskFailed and
    ResearchNotSupported are definitive verdicts, not transport noise, so
    they propagate on the first raise. RateLimited joins them for a
    different reason: the window is empty, so a retry is not merely useless
    but spends two more calls against a budget that has none left, and the
    caller has a reset time it can wait for instead.
    """
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest packages/herder/tests/test_llm_tasks.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add packages/herder/src/herder/tasks.py packages/herder/tests/test_llm_tasks.py
git commit -m "fix(herder): stop retrying a usage-limit refusal as transport noise"
```

---

