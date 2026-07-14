class FakeProvider:
    """Queue-driven test backend: pops canned responses in order, records prompts."""

    def __init__(self, completes: list[str] | None = None, researches: list[str] | None = None):
        self.completes = list(completes or [])
        self.researches = list(researches or [])
        self.calls: list[tuple[str, str]] = []

    def complete(self, prompt: str) -> str:
        self.calls.append(("complete", prompt))
        if not self.completes:
            raise AssertionError("FakeProvider: no queued complete responses left")
        return self.completes.pop(0)

    def research(self, brief: str) -> str:
        self.calls.append(("research", brief))
        if not self.researches:
            raise AssertionError("FakeProvider: no queued research responses left")
        return self.researches.pop(0)
