"""Insert a domestic series into an OECD panel without quietly lying about it.

The splice is the risky step: the OECD number and the Stats NZ number are rarely the
same statistic. Everything here exists to make the mismatch visible — conformance
checks up front, a provenance flag on every row, a report you can print in a footnote.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from .normalise import TIDY_COLUMNS, coverage

LinkMethod = Literal["none", "level", "ratio"]


@dataclass
class SpliceReport:
    """What the splice did, and what a careful reader should be told about it."""

    area: str
    n_rows_added: int
    periods_added: tuple[str, ...]
    panel_periods: tuple[str, ...]
    missing_vs_panel: tuple[str, ...]
    link_method: LinkMethod
    link_factor: float | None
    overlap_periods: tuple[str, ...]
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.warnings

    def footnote(self) -> str:
        """One-paragraph provenance note, for the bottom of a chart or table."""
        span = f"{self.periods_added[0]}–{self.periods_added[-1]}" if self.periods_added else "n/a"
        bits = [f"{self.area} ({span}) is not published in this OECD dataflow and is "
                f"spliced in from a domestic source."]
        if self.link_method != "none" and self.link_factor is not None:
            verb = "shifted" if self.link_method == "level" else "scaled"
            bits.append(
                f"The domestic series is {verb} onto the OECD basis by "
                f"{self.link_factor:+.4g}" if self.link_method == "level"
                else f"The domestic series is {verb} onto the OECD basis by a factor of {self.link_factor:.4g}"
            )
            bits.append(f"estimated over {len(self.overlap_periods)} overlapping period(s).")
        if self.missing_vs_panel:
            bits.append(
                f"{self.area} has no observation for {len(self.missing_vs_panel)} period(s) "
                f"covered by the rest of the panel."
            )
        bits.extend(self.notes)
        return " ".join(bits)

    def __str__(self) -> str:
        lines = [
            f"splice: {self.area}  +{self.n_rows_added} rows  link={self.link_method}",
            f"  added:   {self.periods_added[0] if self.periods_added else '-'} .. "
            f"{self.periods_added[-1] if self.periods_added else '-'}",
            f"  panel:   {self.panel_periods[0] if self.panel_periods else '-'} .. "
            f"{self.panel_periods[-1] if self.panel_periods else '-'}",
        ]
        if self.link_factor is not None:
            lines.append(f"  factor:  {self.link_factor:.6g} over {len(self.overlap_periods)} overlap(s)")
        if self.missing_vs_panel:
            lines.append(f"  gaps:    {len(self.missing_vs_panel)} period(s) missing vs panel")
        for w in self.warnings:
            lines.append(f"  WARN:    {w}")
        for n in self.notes:
            lines.append(f"  note:    {n}")
        return "\n".join(lines)


def _unique(values: pd.Series) -> list:
    return sorted({v for v in values.dropna().tolist()})


def _estimate_link(
    panel_overlap: pd.Series, incoming_overlap: pd.Series, method: LinkMethod
) -> float | None:
    """Factor that maps the incoming series onto the panel's basis over shared periods."""
    if method == "none" or panel_overlap.empty:
        return None
    if method == "level":
        return float((panel_overlap - incoming_overlap).mean())
    ratio = panel_overlap / incoming_overlap.replace(0, pd.NA)
    return float(ratio.dropna().mean())


def _apply_link(values: pd.Series, method: LinkMethod, factor: float | None) -> pd.Series:
    if factor is None or method == "none":
        return values
    return values + factor if method == "level" else values * factor


def splice(
    panel: pd.DataFrame,
    incoming: pd.DataFrame,
    *,
    area: str = "NZL",
    link: LinkMethod = "none",
    overwrite: bool = False,
    strict_units: bool = True,
) -> tuple[pd.DataFrame, SpliceReport]:
    """Add `area`'s observations from `incoming` to `panel`.

    link="ratio"/"level" rescales the incoming series onto the panel's basis using
    periods where both sources already report `area` — only meaningful when the OECD
    flow carries a partial or differently-defined NZ series to anchor against.
    """
    for name, frame in (("panel", panel), ("incoming", incoming)):
        missing = [c for c in TIDY_COLUMNS if c not in frame.columns]
        if missing:
            raise ValueError(f"{name} is not tidy: missing {missing}. Run normalise.to_tidy first.")

    warnings: list[str] = []
    notes: list[str] = []

    add = incoming.loc[incoming["ref_area"] == area].copy()
    if add.empty:
        raise ValueError(f"incoming frame has no rows for ref_area={area!r}")

    existing = panel.loc[panel["ref_area"] == area]
    panel_periods = tuple(sorted(set(panel["time_period"])))

    panel_units, add_units = _unique(panel["unit"]), _unique(add["unit"])
    if panel_units and add_units and set(panel_units) != set(add_units):
        message = f"unit mismatch: panel {panel_units} vs incoming {add_units}"
        if strict_units:
            raise ValueError(
                message + ". Convert the incoming series first, or pass strict_units=False "
                "if the codes differ but the underlying unit does not."
            )
        warnings.append(message)

    panel_mult, add_mult = _unique(panel["unit_mult"]), _unique(add["unit_mult"])
    if panel_mult and add_mult and set(panel_mult) != set(add_mult):
        warnings.append(
            f"scale mismatch: panel unit_mult {panel_mult} vs incoming {add_mult}; "
            "call normalise.rescale on both frames."
        )

    panel_freq, add_freq = _unique(panel["freq"]), _unique(add["freq"])
    if panel_freq and add_freq and set(panel_freq) != set(add_freq):
        warnings.append(f"frequency mismatch: panel {panel_freq} vs incoming {add_freq}")

    overlap = tuple(sorted(set(existing["time_period"]) & set(add["time_period"])))
    link_factor = None
    if overlap:
        left = existing.set_index("time_period")["obs_value"].reindex(list(overlap))
        right = add.set_index("time_period")["obs_value"].reindex(list(overlap))
        link_factor = _estimate_link(left, right, link)
        if link == "none":
            if overwrite:
                notes.append(
                    f"{len(overlap)} period(s) already present for {area} in the panel were "
                    "replaced by the domestic source."
                )
            else:
                warnings.append(
                    f"{area} already has {len(overlap)} period(s) in the panel and link='none'; "
                    "pass overwrite=True to replace them or link='ratio'/'level' to chain onto them."
                )
        else:
            add["obs_value"] = _apply_link(add["obs_value"], link, link_factor)
            notes.append(
                f"Domestic values {'shifted' if link == 'level' else 'scaled'} onto the OECD "
                f"basis using {len(overlap)} overlapping period(s)."
            )
    elif link != "none":
        warnings.append(
            f"link={link!r} requested but the panel holds no {area} observations to anchor on; "
            "the domestic series was inserted unadjusted."
        )
        link = "none"

    add["source"] = add["source"].fillna("domestic")
    add["spliced"] = True

    base = panel.copy()
    if "spliced" not in base.columns:
        base["spliced"] = False
    if overwrite and not existing.empty:
        drop = (base["ref_area"] == area) & (base["time_period"].isin(add["time_period"]))
        base = base.loc[~drop]

    # Carry the panel's indicator/unit codes onto rows that arrived without them.
    for column in ("indicator", "unit"):
        if add[column].isna().all() and len(_unique(panel[column])) == 1:
            add[column] = _unique(panel[column])[0]
            notes.append(f"incoming {column} was blank; inherited {add[column].iloc[0]!r} from the panel.")

    out = (
        pd.concat([base, add], ignore_index=True)
        .sort_values(["ref_area", "indicator", "time_period"])
        .reset_index(drop=True)
    )

    added_periods = tuple(sorted(set(add["time_period"])))
    missing = tuple(p for p in panel_periods if p not in set(add["time_period"]))
    if len(missing) > len(panel_periods) * 0.5 and panel_periods:
        warnings.append(
            f"{area} covers only {len(added_periods)} of {len(panel_periods)} panel periods; "
            "cross-country comparisons will be unbalanced."
        )

    report = SpliceReport(
        area=area,
        n_rows_added=len(add),
        periods_added=added_periods,
        panel_periods=panel_periods,
        missing_vs_panel=missing,
        link_method=link,
        link_factor=link_factor,
        overlap_periods=overlap,
        warnings=warnings,
        notes=notes,
    )
    return out, report


def compare_overlap(panel: pd.DataFrame, incoming: pd.DataFrame, area: str = "NZL") -> pd.DataFrame:
    """Side-by-side of both sources where they both report `area` — run this before splicing."""
    left = panel.loc[panel["ref_area"] == area].set_index("time_period")["obs_value"]
    right = incoming.loc[incoming["ref_area"] == area].set_index("time_period")["obs_value"]
    out = pd.DataFrame({"panel": left, "incoming": right}).dropna(how="all")
    out["diff"] = out["incoming"] - out["panel"]
    out["ratio"] = out["incoming"] / out["panel"].replace(0, pd.NA)
    return out


__all__ = ["SpliceReport", "splice", "compare_overlap", "coverage"]
