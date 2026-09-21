"""Datasets are described in TOML, so naming a new one never means editing code."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .sdmx import DataflowRef, Query


@dataclass
class SourceSpec:
    """A domestic (non-OECD) series: where it comes from and how to read it."""

    name: str
    url: str | None = None
    path: str | None = None
    area: str = "NZL"
    series: str = ""
    mapping: dict[str, str] = field(default_factory=dict)
    constants: dict[str, Any] = field(default_factory=dict)
    read_options: dict[str, Any] = field(default_factory=dict)
    notes: str = ""


@dataclass
class DatasetSpec:
    """One end-to-end job: an OECD query, a domestic series, and how to join them."""

    key: str
    title: str
    flow: DataflowRef
    query_key: str = ""
    start_period: str | None = None
    end_period: str | None = None
    link: str = "none"
    overwrite: bool = False
    strict_units: bool = True
    source: SourceSpec | None = None
    notes: str = ""

    def query(self) -> Query:
        return Query(
            flow=self.flow,
            key=self.query_key,
            start_period=self.start_period,
            end_period=self.end_period,
        )


def load(path: Path | str) -> dict[str, DatasetSpec]:
    """Read a TOML file of [dataset.<key>] tables into DatasetSpecs."""
    raw = tomllib.loads(Path(path).read_text())
    specs: dict[str, DatasetSpec] = {}
    for key, block in (raw.get("dataset") or {}).items():
        oecd = block.get("oecd") or {}
        for required in ("agency", "dataflow"):
            if required not in oecd:
                raise ValueError(f"dataset.{key}.oecd is missing {required!r}")
        src = block.get("source")
        specs[key] = DatasetSpec(
            key=key,
            title=block.get("title", key),
            flow=DataflowRef(oecd["agency"], oecd["dataflow"], str(oecd.get("version", "1.0"))),
            query_key=oecd.get("key", ""),
            start_period=oecd.get("start_period"),
            end_period=oecd.get("end_period"),
            link=block.get("link", "none"),
            overwrite=bool(block.get("overwrite", False)),
            strict_units=bool(block.get("strict_units", True)),
            source=SourceSpec(**src) if src else None,
            notes=block.get("notes", ""),
        )
    return specs
