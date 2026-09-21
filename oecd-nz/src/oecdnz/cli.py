"""Command line: `python -m oecdnz build <dataset>` runs fetch -> splice -> transform."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from . import config as config_module
from .normalise import coverage
from .sdmx import EgressBlocked, OecdClient, read_local_sdmx_csv
from .sources import load_domestic
from .splice import compare_overlap, splice
from .transform import Panel

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "datasets.toml"
DEFAULT_OUT = Path(__file__).resolve().parents[2] / "out"


def _load_panel(spec, args) -> pd.DataFrame:
    if args.oecd_file:
        return read_local_sdmx_csv(args.oecd_file, series=str(spec.flow))
    return OecdClient().fetch(spec.query(), refresh=args.refresh)


def cmd_build(args) -> int:
    specs = config_module.load(args.config)
    if args.dataset not in specs:
        print(f"unknown dataset {args.dataset!r}; config has: {', '.join(specs)}", file=sys.stderr)
        return 2
    spec = specs[args.dataset]

    panel = _load_panel(spec, args)
    print(f"OECD panel: {len(panel)} obs, {panel['ref_area'].nunique()} areas")

    if spec.source is None:
        print("no domestic source configured; nothing to splice", file=sys.stderr)
        return 2
    incoming = load_domestic(spec.source)
    print(f"{spec.source.name}: {len(incoming)} obs")

    overlap = compare_overlap(panel, incoming, spec.source.area)
    if not overlap.empty and overlap["panel"].notna().any():
        print("\noverlap with the OECD's own figures:")
        print(overlap.to_string())

    merged, report = splice(
        panel,
        incoming,
        area=spec.source.area,
        link=spec.link,
        overwrite=spec.overwrite,
        strict_units=spec.strict_units,
    )
    print("\n" + str(report))
    print("\nfootnote: " + report.footnote())

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    tidy_path = out_dir / f"{spec.key}-spliced.csv"
    merged.to_csv(tidy_path, index=False)
    wide_path = out_dir / f"{spec.key}-wide.csv"
    Panel(merged).wide().to_csv(wide_path)
    print(f"\nwrote {tidy_path}\nwrote {wide_path}")
    return 0 if report.ok or args.allow_warnings else 1


def cmd_coverage(args) -> int:
    specs = config_module.load(args.config)
    spec = specs[args.dataset]
    panel = _load_panel(spec, args)
    print(coverage(panel).to_string())
    return 0


def cmd_datasets(args) -> int:
    for key, spec in config_module.load(args.config).items():
        source = spec.source.name if spec.source else "— no domestic source —"
        print(f"{key:20} {spec.flow}  <- {source}\n{'':20} {spec.title}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oecdnz", description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    sub = parser.add_subparsers(dest="command", required=True)

    for name, func, needs_dataset in (
        ("build", cmd_build, True),
        ("coverage", cmd_coverage, True),
        ("datasets", cmd_datasets, False),
    ):
        p = sub.add_parser(name, help=func.__doc__)
        if needs_dataset:
            p.add_argument("dataset")
            p.add_argument("--oecd-file", help="use a hand-downloaded SDMX-CSV instead of the API")
            p.add_argument("--refresh", action="store_true", help="bypass the on-disk cache")
        p.add_argument("--out", default=str(DEFAULT_OUT))
        p.add_argument("--allow-warnings", action="store_true", help="exit 0 even if the splice warns")
        p.set_defaults(func=func)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except EgressBlocked as exc:
        print(f"\nnetwork blocked: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
