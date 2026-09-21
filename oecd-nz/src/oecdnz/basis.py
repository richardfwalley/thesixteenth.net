"""Survey-design metadata, and what it means when the two sides disagree.

For most spliced series the numbers line up on units and periods and still are not
comparable, because the two statistical agencies surveyed different firms over a
different window. Innovation surveys are the sharpest case: an innovation "rate" is
almost entirely a function of who was asked and over how long.

A Basis records that design. Mismatches become warnings on the SpliceReport and
sentences in its footnote, so the caveat travels with the number instead of living
in someone's head.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any, Mapping


@dataclass(frozen=True)
class Basis:
    """How a series was produced. Every field is optional; unknown fields stay None."""

    survey: str | None = None              # "Community Innovation Survey", "Business Operations Survey"
    manual: str | None = None              # "Oslo Manual 2018"
    reference_period_years: float | None = None  # observation window the respondent reports on
    size_threshold: int | None = None      # minimum employee count in the surveyed population
    industry_scope: str | None = None      # "NACE core CIS", "ANZSIC selected industries"
    population: str | None = None          # free text: what the denominator is
    notes: str = ""

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "Basis | None":
        if not data:
            return None
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"unknown basis field(s): {sorted(unknown)}; allowed: {sorted(known)}")
        return cls(**dict(data))

    def describe(self) -> str:
        parts = []
        if self.survey:
            parts.append(self.survey)
        if self.reference_period_years:
            parts.append(f"{_years(self.reference_period_years)} reference period")
        if self.size_threshold:
            parts.append(f"{self.size_threshold}+ employees")
        if self.industry_scope:
            parts.append(self.industry_scope)
        return ", ".join(parts) or "basis not recorded"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _years(value: float) -> str:
    return f"{int(value)}-year" if float(value).is_integer() else f"{value}-year"


# Fields where a mismatch has a known direction of bias, phrased for a footnote.
_DIRECTIONAL = {
    "reference_period_years": (
        "A shorter reference period gives a respondent less time in which to have "
        "innovated, so it tends to depress the measured rate."
    ),
    "size_threshold": (
        "A lower size threshold pulls more small firms into the denominator, and small "
        "firms report innovation less often, so it tends to depress the measured rate."
    ),
}


def compare(panel: Basis | None, incoming: Basis | None) -> tuple[list[str], list[str]]:
    """Return (warnings, footnote_sentences) describing how the two designs differ."""
    if panel is None or incoming is None:
        if panel is None and incoming is None:
            return [], []
        side = "OECD panel" if panel is None else "domestic source"
        return ([f"no survey basis recorded for the {side}; comparability is unverified"], [])

    warnings: list[str] = []
    sentences: list[str] = []
    for field_ in fields(Basis):
        if field_.name == "notes":
            continue
        left, right = getattr(panel, field_.name), getattr(incoming, field_.name)
        if left is None or right is None or left == right:
            continue
        label = field_.name.replace("_", " ")
        warnings.append(f"basis mismatch on {label}: panel {left!r} vs incoming {right!r}")
        if field_.name in _DIRECTIONAL:
            direction = _DIRECTIONAL[field_.name]
            sentences.append(
                f"The two sources differ on {label} ({left} against {right}). {direction}"
            )
        else:
            sentences.append(f"The two sources differ on {label}: {left} against {right}.")

    for source in (panel, incoming):
        if source.notes and source.notes not in sentences:
            sentences.append(source.notes)

    return warnings, sentences
