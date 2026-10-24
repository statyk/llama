# Vendored verbatim from commit e37f670 (v2.17.0): packages/llama/src/llama/models.py,
# class `Overrides`, renamed `OverridesV2170`. The oracle for test_override_keys.py:
# `override_keys.legacy_int` must agree with this model's own lax int parsing (spec 4.1
# "Legacy values"), and this model must reject every migrated (filename-valued) file
# (spec 4.1 "Old binaries fail loudly"). Do not edit below this header.
# Imports: `from __future__ import annotations` and `from pydantic import BaseModel, Field`,
# as in that file.

from __future__ import annotations

from pydantic import BaseModel, Field


class OverridesV2170(BaseModel):
    """Hand-authored per-show operator input, durable across re-derivation.
    Read by gather (exclude, include, venue, city, date, titles, set_breaks,
    encore_after) and brief (narration); never auto-written by a stage.
    Absent file == this default."""
    exclude: list[str] = Field(default_factory=list)   # source filenames to drop
    include: list[str] = Field(default_factory=list)   # filenames re-admitted past the junk filter
    narration: str = "full"                            # "full" | "vague"
    venue: str | None = None
    city: str | None = None
    date: str | None = None                            # YYYY-MM-DD
    titles: dict[int, str] = Field(default_factory=dict)   # track number -> forced title
    set_breaks: list[int] | None = None                # track numbers a break falls after
    encore_after: int | None = None     # encore begins after this track number
