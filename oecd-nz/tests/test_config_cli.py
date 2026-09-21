from pathlib import Path

import pytest

from oecdnz import config as config_module
from oecdnz.cli import main

REPO = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_shipped_config_parses():
    specs = config_module.load(REPO / "config" / "datasets.toml")
    spec = specs["business-innovation"]
    assert spec.source.name == "Stats NZ"
    assert spec.oecd_basis.reference_period_years == 3
    assert spec.source.basis.reference_period_years == 2


def test_shipped_config_is_flagged_as_unfinished():
    spec = config_module.load(REPO / "config" / "datasets.toml")["business-innovation"]
    assert not spec.ready
    placeholders = spec.placeholders()
    assert "dataset.business-innovation.oecd.dataflow" in placeholders
    assert any(".basis." in p for p in placeholders)


def test_build_refuses_placeholder_ids(capsys):
    code = main(["--config", str(REPO / "config" / "datasets.toml"), "build", "business-innovation"])
    assert code == 2
    assert "placeholder OECD ids" in capsys.readouterr().err


def test_missing_dataflow_id_is_a_clear_error(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text('[dataset.x]\ntitle = "x"\n[dataset.x.oecd]\nagency = "OECD"\n')
    with pytest.raises(ValueError, match="missing 'dataflow'"):
        config_module.load(bad)


def _job_config(tmp_path) -> Path:
    path = tmp_path / "job.toml"
    path.write_text(f"""
[dataset.wealth]
title = "Top 10% wealth share, with NZ"

  [dataset.wealth.oecd]
  agency = "OECD.WISE.INE"
  dataflow = "DSD_WEALTH@DF_EXAMPLE"

  [dataset.wealth.source]
  name = "Stats NZ"
  path = "{FIXTURES / 'statsnz_series.csv'}"
  series = "Household net worth: share held by top 10%"

    [dataset.wealth.source.mapping]
    Period = "time_period"
    Data_value = "obs_value"

    [dataset.wealth.source.constants]
    indicator = "SHARE_TOP10"
    unit = "PT_B1GQ"
""")
    return path


def test_build_end_to_end_from_local_files(tmp_path, capsys):
    out = tmp_path / "out"
    code = main([
        "--config", str(_job_config(tmp_path)), "build", "wealth",
        "--oecd-file", str(FIXTURES / "oecd_panel.csv"), "--out", str(out),
    ])
    assert code == 0
    printed = capsys.readouterr().out
    assert "splice: NZL  +5 rows" in printed
    assert "footnote:" in printed

    import pandas as pd
    tidy = pd.read_csv(out / "wealth-spliced.csv")
    assert set(tidy["ref_area"]) == {"AUS", "CAN", "GBR", "JPN", "NZL", "USA"}
    assert tidy.loc[tidy["ref_area"] == "NZL", "spliced"].all()
    wide = pd.read_csv(out / "wealth-wide.csv", index_col=0)
    assert "NZL" in wide.columns


def test_datasets_command_lists_jobs(tmp_path, capsys):
    assert main(["--config", str(_job_config(tmp_path)), "datasets"]) == 0
    assert "wealth" in capsys.readouterr().out


def test_unknown_dataset_exits_nonzero(tmp_path, capsys):
    assert main(["--config", str(_job_config(tmp_path)), "build", "nope"]) == 2
    assert "unknown dataset" in capsys.readouterr().err
