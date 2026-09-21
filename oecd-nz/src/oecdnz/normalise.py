"""Harmonise heterogeneous inputs (OECD SDMX-CSV, Stats NZ CSV) into one tidy frame.

Everything downstream assumes TIDY_COLUMNS. One row = one observation.
"""

from __future__ import annotations

import re
from typing import Iterable, Mapping

import pandas as pd

TIDY_COLUMNS = [
    "ref_area",       # ISO-3166 alpha-3, upper case
    "ref_area_label", # human-readable country name
    "indicator",      # indicator / measure code
    "unit",           # unit of measure code, e.g. PT_B1GQ, USD_PPP
    "unit_mult",      # power of ten already applied to obs_value
    "freq",           # A, Q, M
    "time_period",    # canonical string: 2023, 2023-Q1, 2023-01
    "obs_value",      # float
    "obs_status",     # SDMX observation status, e.g. E (estimate), P (provisional)
    "source",         # provenance: "OECD" or the domestic source's short name
    "series",         # free-text description of the exact upstream series
]

# SDMX-CSV column -> tidy column. Case-insensitive; labelled variants ("REF_AREA: Label")
# are handled by _strip_sdmx_labels before this map is applied.
_SDMX_ALIASES = {
    "ref_area": "ref_area",
    "location": "ref_area",
    "country": "ref_area",
    "reference area": "ref_area_label",
    "measure": "indicator",
    "indicator": "indicator",
    "subject": "indicator",
    "unit_measure": "unit",
    "unit of measure": "unit",
    "unit": "unit",
    "unit_mult": "unit_mult",
    "freq": "freq",
    "frequency": "freq",
    "frequency of observation": "freq",
    "time_period": "time_period",
    "time": "time_period",
    "obs_value": "obs_value",
    "observation value": "obs_value",
    "value": "obs_value",
    "obs_status": "obs_status",
    "observation status": "obs_status",
}

_FREQ_FROM_LABEL = {"annual": "A", "quarterly": "Q", "monthly": "M", "yearly": "A"}

_ISO3_FIXUPS = {
    "NEW ZEALAND": "NZL",
    "NZ": "NZL",
    "EU27_2020": "EU27",
    "OECD": "OECD",
}


class NormalisationError(ValueError):
    """Raised when an input cannot be coerced into the tidy schema."""


def _strip_sdmx_labels(df: pd.DataFrame) -> pd.DataFrame:
    """SDMX-CSV 'csvfilewithlabels' emits `CODE: Label` pairs; keep the code column."""
    renamed = {}
    for col in df.columns:
        base = col.split(":", 1)[0].strip() if ":" in col else col
        renamed[col] = base
    out = df.rename(columns=renamed)
    return out.loc[:, ~out.columns.duplicated(keep="first")]


def canonical_period(value: object, freq: str | None = None) -> str:
    """Return a sortable canonical period string, or raise NormalisationError."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        raise NormalisationError("empty time period")
    s = str(value).strip().upper().replace("/", "-")
    if re.fullmatch(r"\d{4}", s):
        return s
    m = re.fullmatch(r"(\d{4})[-\s]?Q([1-4])", s)
    if m:
        return f"{m.group(1)}-Q{m.group(2)}"
    m = re.fullmatch(r"(\d{4})[-\s]?M?(\d{1,2})", s)
    if m and 1 <= int(m.group(2)) <= 12:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    raise NormalisationError(f"unrecognised time period: {value!r}")


def infer_freq(period: str) -> str:
    if re.fullmatch(r"\d{4}", period):
        return "A"
    if "Q" in period:
        return "Q"
    return "M"


def period_to_timestamp(period: str) -> pd.Timestamp:
    """Period start as a Timestamp, for plotting and resampling."""
    freq = infer_freq(period)
    if freq == "A":
        return pd.Timestamp(int(period), 1, 1)
    if freq == "Q":
        year, q = period.split("-Q")
        return pd.Timestamp(int(year), (int(q) - 1) * 3 + 1, 1)
    year, month = period.split("-")
    return pd.Timestamp(int(year), int(month), 1)


def normalise_area(value: object) -> str:
    s = str(value).strip().upper()
    return _ISO3_FIXUPS.get(s, s)


def to_tidy(
    df: pd.DataFrame,
    *,
    source: str,
    mapping: Mapping[str, str] | None = None,
    constants: Mapping[str, object] | None = None,
    series: str | None = None,
) -> pd.DataFrame:
    """Coerce an arbitrary frame into TIDY_COLUMNS.

    mapping: extra {input_column: tidy_column} pairs, applied after the SDMX aliases.
    constants: tidy columns to fill with a fixed value (e.g. indicator for a domestic
        series that carries no code of its own).
    """
    work = _strip_sdmx_labels(df.copy())
    lowered = {c: c.strip().lower() for c in work.columns}
    rename = {c: _SDMX_ALIASES[low] for c, low in lowered.items() if low in _SDMX_ALIASES}
    rename.update(dict(mapping or {}))
    work = work.rename(columns=rename)
    work = work.loc[:, ~work.columns.duplicated(keep="first")]

    for key, value in (constants or {}).items():
        work[key] = value
    work["source"] = source
    if series is not None:
        work["series"] = series

    missing = [c for c in ("ref_area", "time_period", "obs_value") if c not in work.columns]
    if missing:
        raise NormalisationError(
            f"cannot build tidy frame from columns {list(df.columns)}: missing {missing}. "
            "Pass mapping={'your_column': 'ref_area', ...} to bridge the gap."
        )

    work["ref_area"] = work["ref_area"].map(normalise_area)
    work["time_period"] = [canonical_period(v) for v in work["time_period"]]
    work["obs_value"] = pd.to_numeric(work["obs_value"], errors="coerce")

    if "freq" in work.columns:
        work["freq"] = (
            work["freq"].astype(str).str.strip().str.lower()
            .map(lambda v: _FREQ_FROM_LABEL.get(v, v[:1].upper() if v else ""))
        )
        blank = work["freq"].isin(["", "N", "NAN"])
        work.loc[blank, "freq"] = work.loc[blank, "time_period"].map(infer_freq)
    else:
        work["freq"] = work["time_period"].map(infer_freq)

    for col in TIDY_COLUMNS:
        if col not in work.columns:
            work[col] = pd.NA
    work["unit_mult"] = pd.to_numeric(work["unit_mult"], errors="coerce").fillna(0).astype(int)

    out = work.loc[:, TIDY_COLUMNS].copy()
    dropped = int(out["obs_value"].isna().sum())
    if dropped:
        out = out.loc[out["obs_value"].notna()].copy()
    return out.sort_values(["ref_area", "indicator", "time_period"]).reset_index(drop=True)


def rescale(df: pd.DataFrame, target_mult: int = 0) -> pd.DataFrame:
    """Put every row on the same power-of-ten scale (SDMX UNIT_MULT)."""
    out = df.copy()
    factor = 10.0 ** (out["unit_mult"].astype(int) - target_mult)
    out["obs_value"] = out["obs_value"] * factor
    out["unit_mult"] = target_mult
    return out


def coverage(df: pd.DataFrame, areas: Iterable[str] | None = None) -> pd.DataFrame:
    """Per-country first/last period and observation count — the first sanity check."""
    work = df if areas is None else df.loc[df["ref_area"].isin(list(areas))]
    grouped = work.groupby("ref_area")["time_period"]
    return pd.DataFrame(
        {"first": grouped.min(), "last": grouped.max(), "n_obs": grouped.count()}
    ).sort_index()
