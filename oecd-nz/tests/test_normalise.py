import pandas as pd
import pytest

from oecdnz.normalise import (
    NormalisationError, canonical_period, coverage, infer_freq, period_to_timestamp,
    rescale, to_tidy,
)


def test_sdmx_csv_becomes_tidy(panel):
    assert set(panel["ref_area"]) == {"AUS", "CAN", "GBR", "JPN", "USA"}
    assert "NZL" not in set(panel["ref_area"])
    assert panel["ref_area_label"].iloc[0] in {"Australia", "Canada", "Japan", "United Kingdom", "United States"}
    assert panel["source"].unique().tolist() == ["OECD"]
    assert panel["freq"].unique().tolist() == ["A"]
    assert panel["obs_value"].dtype.kind == "f"


def test_domestic_export_becomes_tidy(nz):
    assert nz["ref_area"].unique().tolist() == ["NZL"]
    assert nz["unit"].unique().tolist() == ["PT_B1GQ"]
    assert nz["time_period"].tolist() == ["2015", "2016", "2017", "2018", "2020"]


@pytest.mark.parametrize(
    "raw,expected",
    [("2023", "2023"), ("2023-Q2", "2023-Q2"), ("2023Q2", "2023-Q2"),
     ("2023-01", "2023-01"), ("2023-1", "2023-01"), ("2023M03", "2023-03"),
     (" 2023/Q4 ", "2023-Q4")],
)
def test_canonical_period(raw, expected):
    assert canonical_period(raw) == expected


def test_canonical_period_rejects_nonsense():
    with pytest.raises(NormalisationError):
        canonical_period("last Tuesday")
    with pytest.raises(NormalisationError):
        canonical_period("2023-13")


def test_freq_inference_and_timestamps():
    assert infer_freq("2023") == "A"
    assert infer_freq("2023-Q3") == "Q"
    assert infer_freq("2023-07") == "M"
    assert period_to_timestamp("2023-Q3") == pd.Timestamp(2023, 7, 1)
    assert period_to_timestamp("2023-07") == pd.Timestamp(2023, 7, 1)


def test_label_pair_columns_are_collapsed():
    raw = pd.DataFrame({
        "REF_AREA: Reference area": ["AUS"], "TIME_PERIOD: Time period": ["2020"],
        "OBS_VALUE: Observation value": [1.5],
    })
    tidy = to_tidy(raw, source="OECD")
    assert tidy.loc[0, "ref_area"] == "AUS"
    assert tidy.loc[0, "obs_value"] == 1.5


def test_missing_required_column_is_a_clear_error():
    with pytest.raises(NormalisationError, match="missing"):
        to_tidy(pd.DataFrame({"year": [2020], "value": [1.0]}), source="Stats NZ")


def test_non_numeric_observations_are_dropped():
    raw = pd.DataFrame({
        "REF_AREA": ["AUS", "AUS"], "TIME_PERIOD": ["2019", "2020"], "OBS_VALUE": [1.0, ".."],
    })
    assert len(to_tidy(raw, source="OECD")) == 1


def test_rescale_moves_everything_to_one_power_of_ten():
    raw = pd.DataFrame({
        "REF_AREA": ["AUS"], "TIME_PERIOD": ["2020"], "OBS_VALUE": [1.5], "UNIT_MULT": [6],
    })
    out = rescale(to_tidy(raw, source="OECD"), target_mult=0)
    assert out.loc[0, "obs_value"] == 1_500_000
    assert out.loc[0, "unit_mult"] == 0


def test_coverage_summarises_each_country(panel):
    cov = coverage(panel)
    assert cov.loc["AUS", "first"] == "2015"
    assert cov.loc["AUS", "last"] == "2020"
    assert cov["n_obs"].unique().tolist() == [6]
