"""Thin OECD SDMX REST client: build a query, fetch it, cache it, parse it.

The OECD public endpoint speaks SDMX 2.1 REST. We ask for SDMX-CSV because it maps
straight onto a DataFrame without an XML dependency.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd
import requests

from .normalise import to_tidy

OECD_BASE = "https://sdmx.oecd.org/public/rest"
CSV_FORMAT = "csvfilewithlabels"
DEFAULT_CACHE = Path(__file__).resolve().parents[2] / "data" / "cache"

# Hosts this pipeline needs. The sandbox blocks them by default; see README.
REQUIRED_HOSTS = ("sdmx.oecd.org", "api.stats.govt.nz", "www.stats.govt.nz")


class EgressBlocked(RuntimeError):
    """The environment's proxy refused the host, rather than the server refusing us."""


@dataclass(frozen=True)
class DataflowRef:
    """Identifies an OECD dataflow, e.g. OECD.SDD.TPS / DSD_LFS@DF_IALFS_UNE_M / 1.0."""

    agency: str
    dataflow: str
    version: str = "1.0"

    def __str__(self) -> str:
        return f"{self.agency},{self.dataflow},{self.version}"


@dataclass
class Query:
    """An SDMX data query. `key` is the dotted dimension filter; '' means everything."""

    flow: DataflowRef
    key: str = ""
    start_period: str | None = None
    end_period: str | None = None
    dimension_at_observation: str = "AllDimensions"
    extra_params: Mapping[str, str] = field(default_factory=dict)

    def url(self, base: str = OECD_BASE) -> str:
        return f"{base}/data/{self.flow}/{self.key}"

    def params(self) -> dict[str, str]:
        params = {"format": CSV_FORMAT, "dimensionAtObservation": self.dimension_at_observation}
        if self.start_period:
            params["startPeriod"] = self.start_period
        if self.end_period:
            params["endPeriod"] = self.end_period
        params.update(self.extra_params)
        return params

    def cache_key(self) -> str:
        raw = f"{self.url()}?{sorted(self.params().items())}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


class OecdClient:
    """Fetches SDMX-CSV with on-disk caching and a clear story when egress is blocked."""

    def __init__(
        self,
        base: str = OECD_BASE,
        cache_dir: Path | str = DEFAULT_CACHE,
        timeout: int = 120,
        retries: int = 4,
        session: requests.Session | None = None,
    ) -> None:
        self.base = base.rstrip("/")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.retries = retries
        self.session = session or requests.Session()
        self.session.headers.update({"Accept": "application/vnd.sdmx.data+csv; version=1.0.0"})

    def fetch_csv(self, query: Query, *, refresh: bool = False) -> str:
        cached = self.cache_dir / f"{query.flow.dataflow}-{query.cache_key()}.csv"
        if cached.exists() and not refresh:
            return cached.read_text()

        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                response = self.session.get(
                    query.url(self.base), params=query.params(), timeout=self.timeout
                )
            except requests.exceptions.ProxyError as exc:  # CONNECT refused by egress policy
                raise EgressBlocked(
                    f"the egress proxy refused {query.url(self.base)}. "
                    f"Allowlist {', '.join(REQUIRED_HOSTS)} for this environment, "
                    "or pass a hand-downloaded extract with `--oecd-file`."
                ) from exc
            except requests.exceptions.RequestException as exc:
                last_error = exc
                time.sleep(2 ** (attempt + 1))
                continue

            if response.status_code == 404:
                raise ValueError(
                    f"no such dataflow/key: {query.flow} key={query.key!r}. "
                    "Check the dataflow id in the OECD Data Explorer's developer API panel."
                )
            if response.status_code in (403, 407) and "proxy" in response.text.lower():
                raise EgressBlocked(f"proxy denied {query.url(self.base)} ({response.status_code})")
            if response.status_code >= 500 or response.status_code == 429:
                last_error = requests.HTTPError(f"{response.status_code} from OECD")
                time.sleep(2 ** (attempt + 1))
                continue
            response.raise_for_status()

            cached.write_text(response.text)
            return response.text

        raise RuntimeError(f"OECD fetch failed after {self.retries} attempts: {last_error}")

    def fetch(self, query: Query, *, refresh: bool = False, series: str | None = None) -> pd.DataFrame:
        from io import StringIO

        csv_text = self.fetch_csv(query, refresh=refresh)
        raw = pd.read_csv(StringIO(csv_text))
        return to_tidy(raw, source="OECD", series=series or str(query.flow))


def read_local_sdmx_csv(path: Path | str, *, series: str | None = None) -> pd.DataFrame:
    """Parse an SDMX-CSV file downloaded by hand from the OECD Data Explorer."""
    raw = pd.read_csv(path)
    return to_tidy(raw, source="OECD", series=series or Path(path).name)


def members(df: pd.DataFrame, exclude: Sequence[str] = ()) -> list[str]:
    """Country codes present in a panel, minus aggregates like OECD/EU27."""
    drop = {"OECD", "EU27", "EU28", "EA19", "EA20", "G7", "G20", "WLD", *map(str.upper, exclude)}
    return sorted(set(df["ref_area"]) - drop)
