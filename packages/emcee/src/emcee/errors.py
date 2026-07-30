"""Central exception taxonomy.

`EmceeError` is the base for expected, user-actionable failures. The CLI
error boundary (`emcee.cli.main_cli`) catches it (alongside `herder.HerderError`,
the shared LLM layer's equivalent) and prints `error: <message>` plus any
indented `details`, instead of a traceback. Anything that is NOT one of those
two is treated as a bug and surfaces as a plain traceback.

This module imports nothing from the rest of the package to stay
import-cycle-free.
"""


class EmceeError(Exception):
    """Base for expected, user-actionable failures.

    `str(self)` must read as a complete, actionable sentence. `details` holds
    optional follow-up lines the boundary prints indented under the message
    (e.g. the candidate list for an ambiguous match).
    """

    def __init__(self, message: str, details: list[str] | None = None):
        super().__init__(message)
        self.details = details or []


class ConfigError(EmceeError):
    """The config file could not be parsed or failed schema validation."""
