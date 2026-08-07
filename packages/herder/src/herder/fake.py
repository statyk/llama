class FakeProvider:
    """Queue-driven test backend: pops canned responses in order, records prompts.

    A queued Exception is raised instead of returned, so a test can stage a
    transport failure (dropped connection, CLI crash) the same way it stages
    a bad reply.
    """

    def __init__(self, completes: list | None = None, researches: list | None = None):
        self.completes = list(completes or [])
        self.researches = list(researches or [])
        self.calls: list[tuple[str, str]] = []

    @staticmethod
    def _serve(item):
        if isinstance(item, BaseException):
            raise item
        return item

    def complete(self, prompt: str) -> str:
        self.calls.append(("complete", prompt))
        if not self.completes:
            raise AssertionError("FakeProvider: no queued complete responses left")
        return self._serve(self.completes.pop(0))

    def research(self, brief: str) -> str:
        self.calls.append(("research", brief))
        if not self.researches:
            raise AssertionError("FakeProvider: no queued research responses left")
        return self._serve(self.researches.pop(0))
