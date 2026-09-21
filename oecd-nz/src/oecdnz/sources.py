"""Readers for the domestic side of the splice.

Generic CSV first; a Stats NZ OData helper on top of it. Anything odd (an Infoshare
export with a preamble, an xlsx with merged headers) is handled by read_options, which
is passed straight through to pandas.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pandas as pd
import requests

from .config import SourceSpec
from .normalise import to_tidy
from .sdmx import EgressBlocked

STATSNZ_ODATA = "https://api.stats.govt.nz/opendata/v1"


def load_domestic(spec: SourceSpec, *, timeout: int = 120) -> pd.DataFrame:
    """Read a domestic series described by a SourceSpec into the tidy schema."""
    if spec.path:
        raw = _read_any(Path(spec.path), spec.read_options)
    elif spec.url:
        raw = _read_any(spec.url, spec.read_options, timeout=timeout)
    else:
        raise ValueError(f"source {spec.name!r} has neither a path nor a url")

    constants = {"ref_area": spec.area, **spec.constants}
    return to_tidy(
        raw,
        source=spec.name,
        mapping=spec.mapping,
        constants=constants,
        series=spec.series or spec.name,
    )


def _read_any(target: Path | str, options: dict, *, timeout: int = 120) -> pd.DataFrame:
    opts = dict(options or {})
    if isinstance(target, Path) or not str(target).startswith("http"):
        path = Path(target)
        if path.suffix.lower() in {".xlsx", ".xls"}:
            return pd.read_excel(path, **opts)
        return pd.read_csv(path, **opts)

    try:
        response = requests.get(str(target), timeout=timeout)
    except requests.exceptions.ProxyError as exc:
        raise EgressBlocked(
            f"the egress proxy refused {target}. Allowlist the host for this environment, "
            "or download the file by hand and point `path` at it instead."
        ) from exc
    response.raise_for_status()
    if "json" in response.headers.get("Content-Type", ""):
        payload = response.json()
        rows = payload.get("value", payload) if isinstance(payload, dict) else payload
        return pd.DataFrame(rows)
    return pd.read_csv(StringIO(response.text), **opts)


def statsnz_odata_url(resource: str, *, filter_: str | None = None, select: str | None = None) -> str:
    """Build a Stats NZ OData v4 request (an API key goes in the session headers)."""
    params = []
    if filter_:
        params.append(f"$filter={filter_}")
    if select:
        params.append(f"$select={select}")
    query = "&".join(params)
    return f"{STATSNZ_ODATA}/{resource.lstrip('/')}" + (f"?{query}" if query else "")
