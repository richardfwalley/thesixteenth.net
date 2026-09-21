# oecdnz

Take an OECD dataflow that does not cover New Zealand, splice NZ in from a domestic
source, and then slice the combined panel however you like — index it, rank it, measure
it against the OECD median, and so on.

The splice is the part that can quietly mislead, so the pipeline is built around making
it visible: every row carries its `source`, spliced rows carry `spliced = True`, and
each run prints a `SpliceReport` with the conformance warnings and a ready-made footnote.

## Layout

```
config/datasets.toml   what to fetch and what to splice in — the only file you edit per job
src/oecdnz/
  sdmx.py              OECD SDMX-REST client (SDMX-CSV, on-disk cache, retry)
  sources.py           domestic readers (Stats NZ OData/CSV/xlsx, or any local extract)
  normalise.py         everything becomes the same tidy schema
  splice.py            the join, its conformance checks, and the report
  transform.py         the manipulations, plus a chainable Panel wrapper
  cli.py               python -m oecdnz build <dataset>
tests/                 63 tests, all against fixtures — no network needed
```

## Tidy schema

One row is one observation:

`ref_area, ref_area_label, indicator, unit, unit_mult, freq, time_period, obs_value,
obs_status, source, series` (+ `spliced` after a splice)

`time_period` is canonical and sortable as a string: `2023`, `2023-Q1`, `2023-01`.

## Adding a job

Describe it in `config/datasets.toml` — no code changes:

```toml
[dataset.wealth]
title = "Top 10% wealth share, with NZ"
link  = "none"        # none | ratio | level
overwrite = false     # replace the OECD's own NZL rows, if it has any

  [dataset.wealth.oecd]
  agency   = "OECD.WISE.INE"
  dataflow = "DSD_WEALTH@DF_EXAMPLE"
  key      = ""       # dotted dimension filter; "" is the whole flow
  start_period = "2000"

  [dataset.wealth.source]
  name   = "Stats NZ"
  path   = "data/raw/household-net-worth.csv"   # or url = "..."
  series = "Household net worth: share held by top 10%"

    [dataset.wealth.source.mapping]
    Period     = "time_period"
    Data_value = "obs_value"

    [dataset.wealth.source.constants]
    indicator = "SHARE_TOP10"
    unit      = "PT_B1GQ"
```

The OECD ids come from the Data Explorer's **Developer API** panel, which prints the
agency, dataflow, version and key for whatever selection is on screen.

Then:

```bash
python -m oecdnz datasets                     # list configured jobs
python -m oecdnz coverage wealth              # who has what, before you commit to anything
python -m oecdnz build wealth                 # fetch -> splice -> out/wealth-{spliced,wide}.csv
python -m oecdnz build wealth --oecd-file extract.csv   # work from a hand-downloaded file
```

## Linking, when the two series don't mean the same thing

If the OECD flow already carries some NZ observations on a different basis, the domestic
series can be chained onto them over the overlap rather than dropped in raw:

- `link = "ratio"` — multiply by the mean panel/domestic ratio across overlapping periods
- `link = "level"` — add the mean difference instead (for series already in points/percent)
- `link = "none"` — insert as published (the honest default when there is no overlap)

Either way the factor, the overlap length and the wording for a footnote come back on the
report. `compare_overlap()` prints the two sources side by side before you decide.

## Survey basis: the caveat that travels with the number

Two series can agree on units and periods and still not be comparable, because the
agencies surveyed different firms over a different window. Record each side's design in
the config and the mismatch becomes loud:

```toml
  [dataset.wealth.oecd.basis]
  survey = "National innovation surveys (CIS-type)"
  reference_period_years = 3
  size_threshold = 10

  [dataset.wealth.source.basis]
  survey = "Business Operations Survey"
  reference_period_years = 2
  size_threshold = 6
```

`splice()` then reports `ok = False`, warns per differing field, and writes the
difference — with its direction of bias, for the fields where that is known — into
`report.footnote()`. A basis recorded on only one side is itself flagged as unverified.

See `docs/business-innovation.md` for the worked case this was built for.

## Manipulating the result

Every transform takes a tidy frame and returns one, so they compose in any order:

```python
from oecdnz import read_local_sdmx_csv, load_domestic, splice, Panel

panel, report = splice(oecd_df, nz_df, area="NZL")
print(report)                       # warnings, gaps, link factor
print(report.footnote())            # the sentence that goes under the chart

out = (Panel(panel)
       .balanced()                  # drop periods where someone is missing
       .rebase("2010")              # index everyone to 100 at 2010
       .aggregate(stat="median")    # add a synthetic OECD_MEDIAN row
       .gap_to("OECD_MEDIAN", pct=True)
       .rank(ascending=False))
out.wide().to_csv("out/table.csv")  # country-by-period matrix
```

Available: `filter_areas`, `filter_periods`, `balanced`, `rebase`, `growth`, `cagr`,
`per_capita`, `deflate`, `convert` (FX/PPP), `aggregate`, `gap_to`, `rank`, `zscore`,
`smooth`, `interpolate_gaps`, `wide`.

`interpolate_gaps` only fills interior gaps and marks every filled row `obs_status = "I"`,
so invented numbers stay distinguishable from published ones.

## Network

This pipeline needs `sdmx.oecd.org` and, if it fetches the NZ side directly,
`api.stats.govt.nz` / `www.stats.govt.nz`. In a sandbox whose egress policy blocks them,
a fetch fails with `EgressBlocked` naming the hosts to allowlist — it does not pretend the
dataset is missing. Until then, `--oecd-file` and `source.path` run the whole thing from
hand-downloaded extracts.

## Tests

```bash
pip install -r requirements.txt
python -m pytest
```
