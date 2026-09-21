# OECD business innovation indicators, with New Zealand spliced in

The job: take the OECD's **Business innovation statistics and indicators** (BISI), which
does not carry New Zealand, and fill the NZ row from Stats NZ's **Business Operations
Survey** (BOS) Module 1.

- OECD side: <https://www.oecd.org/en/data/datasets/business-innovation-statistics-and-indicators.html>
- NZ side: <https://www.stats.govt.nz/information-releases/business-operations-survey-2023/>

## Status

Both hosts are refused by this environment's egress proxy (`sdmx.oecd.org`,
`data-explorer.oecd.org`, `www.oecd.org`, `stats.govt.nz`, `www.stats.govt.nz`,
`nzdotstat.stats.govt.nz` — all probed, all blocked). Nothing below was read from the
sources themselves; it comes from search results and is marked accordingly. The config
entry carries `TODO`/`CONFIRM` markers wherever that matters, `oecdnz datasets` counts
them, and `oecdnz build` refuses to run while the dataflow id is one of them.

## What we know

| | Established | Still to confirm |
|---|---|---|
| **Coverage** | The April 2026 BISI release covers 2020–2022 for 33 OECD members plus 7 partner/accession economies. With 38 members, 5 are absent. | That NZ is one of the absent 5. One `oecdnz coverage business-innovation` run settles it. |
| **Dataflow id** | Ids take the form `DSD_CODE@DF_CODE` under an agency like `OECD.STI.*`. | The actual agency/dataflow/version. The Data Explorer's **Developer API** button prints them. |
| **Indicator** | BISI publishes ~80 indicators, updated roughly every two years. | Which single indicator we are filling — this decides the `key` and the BOS question that matches it. |
| **BOS 2023 break** | BOS 2023 replaced its three questions on operational, organisational and marketing process innovation with one process-innovation question. | Whether the indicator we pick is affected by that change. |

## The real problem, which is not a coding problem

An innovation "rate" is mostly an artefact of who was asked and over how long. Two
design differences are very likely to sit between BISI and BOS:

1. **Reference period.** CIS-type surveys ask about a multi-year window; BOS asks about
   its own, shorter one. Less time to have innovated in means a lower measured rate.
2. **Size threshold.** CIS-type surveys typically start at 10+ employees; BOS runs on a
   lower threshold. More small firms in the denominator also means a lower measured rate.

Both push the same way, so a naive splice would likely make New Zealand look *less*
innovative than a like-for-like comparison would. Neither is repairable by arithmetic:
there is no NZ row in the OECD flow to chain against, so `link` stays `"none"` and the
difference has to be disclosed rather than adjusted away.

That is what `basis.py` is for. The design of each side is recorded in the config; where
the two disagree, `splice()` refuses to call the result clean (`report.ok` is False) and
writes the difference, with its direction of bias, into `report.footnote()`.

If you want a like-for-like number instead of a disclosed-mismatch number, the route is
a custom BOS tabulation restricted to the OECD population (the matching size threshold
and industry scope) — a data request to Stats NZ, not a transformation of the published
totals.

## To finish this

1. Allowlist the hosts, or download two files by hand:
   - the BISI extract for the chosen indicator → `--oecd-file`
   - the BOS 2023 innovation table → `data/raw/bos-2023-innovation.csv`
2. Fill the `TODO` ids and the `CONFIRM` basis values in
   `config/datasets.toml` from the two sources' own metadata.
3. `oecdnz coverage business-innovation` — confirm NZ is genuinely absent and see what
   years the panel actually holds.
4. `oecdnz build business-innovation` — splices, reports, writes `out/*.csv`.
5. Read the printed footnote before publishing any of it.
