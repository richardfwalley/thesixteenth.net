"""Manipulations for the stitched panel.

Every function takes a tidy frame and returns a tidy frame (same columns, plus any
derived column it names), so they compose in any order. `Panel` wraps them for chaining.
"""

from __future__ import annotations

from typing import Iterable, Literal, Sequence

import pandas as pd

from .normalise import TIDY_COLUMNS, period_to_timestamp

GROUP = ["ref_area", "indicator", "unit"]
Stat = Literal["median", "mean", "sum", "min", "max", "std"]


def _sorted(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(GROUP + ["time_period"])


def _groups(df: pd.DataFrame) -> list[str]:
    return [c for c in GROUP if c in df.columns and df[c].notna().any()] or ["ref_area"]


def filter_areas(df: pd.DataFrame, areas: Iterable[str], *, exclude: bool = False) -> pd.DataFrame:
    mask = df["ref_area"].isin(list(areas))
    return df.loc[~mask if exclude else mask].reset_index(drop=True)


def filter_periods(df: pd.DataFrame, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    out = df
    if start:
        out = out.loc[out["time_period"] >= start]
    if end:
        out = out.loc[out["time_period"] <= end]
    return out.reset_index(drop=True)


def balanced(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only periods for which every country in the frame reports a value."""
    counts = df.groupby("time_period")["ref_area"].nunique()
    keep = counts[counts == df["ref_area"].nunique()].index
    return df.loc[df["time_period"].isin(keep)].reset_index(drop=True)


def rebase(df: pd.DataFrame, base_period: str, *, base_value: float = 100.0) -> pd.DataFrame:
    """Index each country's series to base_value at base_period."""
    out = _sorted(df).copy()
    keys = _groups(out)
    bases = (
        out.loc[out["time_period"] == base_period]
        .set_index(keys)["obs_value"]
        .rename("_base")
    )
    if bases.empty:
        raise ValueError(f"no observations at base period {base_period!r}")
    out = out.join(bases, on=keys)
    out["obs_value"] = out["obs_value"] / out["_base"] * base_value
    out["unit"] = f"IDX_{base_period}"
    out["unit_mult"] = 0
    return out.drop(columns="_base").reset_index(drop=True)


def growth(df: pd.DataFrame, periods: int = 1, *, pct: bool = True) -> pd.DataFrame:
    """Period-on-period change. Gaps in a series are respected, not silently bridged."""
    out = _sorted(df).copy()
    change = out.groupby(_groups(out), dropna=False)["obs_value"].pct_change(periods=periods)
    out["obs_value"] = change * 100 if pct else change
    out["unit"] = "PCT_CHG" if pct else "CHG"
    out["unit_mult"] = 0
    return out.dropna(subset=["obs_value"]).reset_index(drop=True)


def cagr(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """Compound annual growth between two periods, one row per country."""
    span = filter_periods(df, start, end)
    first = span.loc[span["time_period"] == start].set_index(_groups(span))["obs_value"]
    last = span.loc[span["time_period"] == end].set_index(_groups(span))["obs_value"]
    years = period_to_timestamp(end).year - period_to_timestamp(start).year
    if years <= 0:
        raise ValueError(f"end {end!r} must be at least a year after start {start!r}")
    rate = ((last / first) ** (1 / years) - 1) * 100
    out = rate.rename("obs_value").reset_index()
    out["time_period"] = f"{start}/{end}"
    out["unit"] = "PCT_CAGR"
    return _fill_tidy(out, df).dropna(subset=["obs_value"]).reset_index(drop=True)


def per_capita(df: pd.DataFrame, population: pd.DataFrame, *, multiplier: float = 1.0) -> pd.DataFrame:
    """Divide by a population frame keyed on (ref_area, time_period)."""
    pop = population.set_index(["ref_area", "time_period"])["obs_value"].rename("_pop")
    out = df.join(pop, on=["ref_area", "time_period"])
    missing = out["_pop"].isna().sum()
    out["obs_value"] = out["obs_value"] / out["_pop"] * multiplier
    out["unit"] = out["unit"].astype(str) + "_PC"
    out = out.drop(columns="_pop").dropna(subset=["obs_value"]).reset_index(drop=True)
    if missing:
        out.attrs["warnings"] = [f"{missing} row(s) dropped for want of a population figure"]
    return out


def deflate(df: pd.DataFrame, deflator: pd.DataFrame, base_period: str) -> pd.DataFrame:
    """Convert nominal to real using a price index frame, expressed in base_period prices."""
    idx = deflator.set_index(["ref_area", "time_period"])["obs_value"].rename("_idx")
    base = (
        deflator.loc[deflator["time_period"] == base_period]
        .set_index("ref_area")["obs_value"]
        .rename("_base")
    )
    out = df.join(idx, on=["ref_area", "time_period"]).join(base, on="ref_area")
    out["obs_value"] = out["obs_value"] / out["_idx"] * out["_base"]
    out["unit"] = out["unit"].astype(str) + f"_REAL{base_period}"
    return out.drop(columns=["_idx", "_base"]).dropna(subset=["obs_value"]).reset_index(drop=True)


def convert(df: pd.DataFrame, rates: pd.DataFrame, *, unit: str = "USD_PPP") -> pd.DataFrame:
    """Divide by a conversion-factor frame (exchange rates or PPPs)."""
    rate = rates.set_index(["ref_area", "time_period"])["obs_value"].rename("_rate")
    out = df.join(rate, on=["ref_area", "time_period"])
    out["obs_value"] = out["obs_value"] / out["_rate"]
    out["unit"] = unit
    return out.drop(columns="_rate").dropna(subset=["obs_value"]).reset_index(drop=True)


def aggregate(
    df: pd.DataFrame,
    *,
    stat: Stat = "median",
    areas: Sequence[str] | None = None,
    label: str | None = None,
) -> pd.DataFrame:
    """Append a synthetic cross-country row per period, e.g. the OECD median."""
    work = df if areas is None else filter_areas(df, areas)
    name = label or f"OECD_{stat.upper()}"
    agg = (
        work.groupby("time_period")["obs_value"].agg(stat).rename("obs_value").reset_index()
    )
    agg["ref_area"] = name
    agg["ref_area_label"] = f"{stat.title()} of {work['ref_area'].nunique()} countries"
    agg["source"] = "derived"
    agg["series"] = f"{stat} across {work['ref_area'].nunique()} areas"
    agg = _fill_tidy(agg, df)
    agg["spliced"] = False
    out = pd.concat([df, agg], ignore_index=True)
    return out.sort_values(["ref_area", "time_period"]).reset_index(drop=True)


def gap_to(df: pd.DataFrame, benchmark: str, *, pct: bool = False) -> pd.DataFrame:
    """Each country's distance from a benchmark area (an aggregate row, or a country)."""
    ref = (
        df.loc[df["ref_area"] == benchmark].set_index("time_period")["obs_value"].rename("_ref")
    )
    if ref.empty:
        raise ValueError(f"benchmark area {benchmark!r} is not in the frame; call aggregate() first")
    out = df.loc[df["ref_area"] != benchmark].join(ref, on="time_period")
    out["obs_value"] = (
        (out["obs_value"] / out["_ref"] - 1) * 100 if pct else out["obs_value"] - out["_ref"]
    )
    out["unit"] = f"GAP_PCT_{benchmark}" if pct else f"GAP_{benchmark}"
    return out.drop(columns="_ref").dropna(subset=["obs_value"]).reset_index(drop=True)


def rank(df: pd.DataFrame, *, ascending: bool = False, exclude_aggregates: bool = True) -> pd.DataFrame:
    """Add `rank` and `pct_rank` within each period."""
    out = df.copy()
    mask = ~out["ref_area"].str.contains("OECD|EU|EA|G7|G20", regex=True, na=False) if exclude_aggregates else slice(None)
    ranked = out.loc[mask].copy()
    grp = ranked.groupby("time_period")["obs_value"]
    ranked["rank"] = grp.rank(ascending=ascending, method="min").astype("Int64")
    ranked["n_ranked"] = grp.transform("count").astype("Int64")
    ranked["pct_rank"] = grp.rank(ascending=ascending, pct=True) * 100
    return ranked.sort_values(["time_period", "rank"]).reset_index(drop=True)


def zscore(df: pd.DataFrame) -> pd.DataFrame:
    """Standardise within each period — how unusual is each country that year."""
    out = df.copy()
    grp = out.groupby("time_period")["obs_value"]
    out["obs_value"] = (out["obs_value"] - grp.transform("mean")) / grp.transform("std")
    out["unit"] = "ZSCORE"
    return out.dropna(subset=["obs_value"]).reset_index(drop=True)


def smooth(df: pd.DataFrame, window: int = 3, *, centred: bool = True) -> pd.DataFrame:
    """Rolling mean within each series."""
    out = _sorted(df).copy()
    out["obs_value"] = (
        out.groupby(_groups(out), dropna=False)["obs_value"]
        .transform(lambda s: s.rolling(window, center=centred, min_periods=1).mean())
    )
    return out.reset_index(drop=True)


def interpolate_gaps(df: pd.DataFrame, *, limit: int | None = None) -> pd.DataFrame:
    """Linearly fill interior gaps, flagging every filled row in obs_status."""
    out = _sorted(df).copy()
    keys = _groups(out)
    frames = []
    for _, chunk in out.groupby(keys, dropna=False):
        periods = pd.period_range(
            period_to_timestamp(chunk["time_period"].min()),
            period_to_timestamp(chunk["time_period"].max()),
            freq={"A": "Y", "Q": "Q", "M": "M"}[chunk["freq"].iloc[0]],
        )
        labels = [_label(p, chunk["freq"].iloc[0]) for p in periods]
        chunk = chunk.set_index("time_period").reindex(labels)
        filled = chunk["obs_value"].isna()
        chunk["obs_value"] = chunk["obs_value"].interpolate(method="linear", limit=limit, limit_area="inside")
        # obs_status describes one observation, so it must not be carried across rows.
        carried = [c for c in TIDY_COLUMNS + ["spliced"] if c not in ("obs_value", "obs_status")]
        for col in carried:
            if col in chunk.columns:
                chunk[col] = chunk[col].ffill().bfill()
        chunk.loc[filled & chunk["obs_value"].notna(), "obs_status"] = "I"
        frames.append(chunk.rename_axis("time_period").reset_index())
    return pd.concat(frames, ignore_index=True).dropna(subset=["obs_value"]).reset_index(drop=True)


def _label(period: pd.Period, freq: str) -> str:
    if freq == "A":
        return f"{period.year}"
    if freq == "Q":
        return f"{period.year}-Q{period.quarter}"
    return f"{period.year}-{period.month:02d}"


def wide(df: pd.DataFrame, *, index: str = "time_period", columns: str = "ref_area") -> pd.DataFrame:
    """Country-by-period matrix, ready for a chart or a spreadsheet."""
    return df.pivot_table(index=index, columns=columns, values="obs_value", aggfunc="first").sort_index()


def _fill_tidy(out: pd.DataFrame, template: pd.DataFrame) -> pd.DataFrame:
    """Give a derived frame the tidy columns it is missing, borrowing from the template."""
    for col in TIDY_COLUMNS:
        if col not in out.columns:
            values = template[col].dropna().unique() if col in template.columns else []
            out[col] = values[0] if len(values) == 1 else pd.NA
    extra = [c for c in out.columns if c not in TIDY_COLUMNS]
    return out.loc[:, TIDY_COLUMNS + extra]


class Panel:
    """Chainable wrapper: Panel(df).filter_areas(...).rebase('2010').rank().df"""

    def __init__(self, df: pd.DataFrame) -> None:
        self.df = df.reset_index(drop=True)

    def __len__(self) -> int:
        return len(self.df)

    def __repr__(self) -> str:
        areas = self.df["ref_area"].nunique()
        periods = self.df["time_period"]
        span = f"{periods.min()}..{periods.max()}" if len(periods) else "empty"
        spliced = int(self.df.get("spliced", pd.Series(dtype=bool)).sum())
        return f"<Panel {len(self.df)} obs, {areas} areas, {span}, {spliced} spliced>"

    def pipe(self, func, *args, **kwargs) -> "Panel":
        return Panel(func(self.df, *args, **kwargs))

    def to_csv(self, path, **kwargs) -> "Panel":
        self.df.to_csv(path, index=False, **kwargs)
        return self


def _attach(name):
    func = globals()[name]

    def method(self: Panel, *args, **kwargs) -> Panel:
        return Panel(func(self.df, *args, **kwargs))

    method.__name__ = name
    method.__doc__ = func.__doc__
    setattr(Panel, name, method)


for _name in (
    "filter_areas", "filter_periods", "balanced", "rebase", "growth", "cagr", "per_capita",
    "deflate", "convert", "aggregate", "gap_to", "rank", "zscore", "smooth", "interpolate_gaps",
):
    _attach(_name)

Panel.wide = lambda self, **kwargs: wide(self.df, **kwargs)
