import pandas as pd
import pytest

from oecdnz.splice import splice
from oecdnz.transform import (
    Panel, aggregate, balanced, cagr, filter_areas, filter_periods, gap_to, growth,
    interpolate_gaps, per_capita, rank, rebase, smooth, wide, zscore,
)


@pytest.fixture
def merged(panel, nz):
    return splice(panel, nz)[0]


def test_filters(merged):
    assert set(filter_areas(merged, ["NZL", "AUS"])["ref_area"]) == {"NZL", "AUS"}
    assert "NZL" not in set(filter_areas(merged, ["NZL"], exclude=True)["ref_area"])
    span = filter_periods(merged, "2017", "2018")
    assert set(span["time_period"]) == {"2017", "2018"}


def test_balanced_drops_periods_nz_is_missing(merged):
    out = balanced(merged)
    assert "2019" not in set(out["time_period"])
    assert set(out["time_period"]) == {"2015", "2016", "2017", "2018", "2020"}


def test_rebase_sets_every_country_to_100_at_the_base(merged):
    out = rebase(merged, "2015")
    at_base = out.loc[out["time_period"] == "2015", "obs_value"]
    assert at_base.round(6).eq(100.0).all()
    assert out["unit"].unique().tolist() == ["IDX_2015"]
    nz_2020 = out.loc[(out["ref_area"] == "NZL") & (out["time_period"] == "2020"), "obs_value"].iloc[0]
    assert nz_2020 == pytest.approx(31.8 / 28.9 * 100)


def test_rebase_without_the_base_period_is_an_error(merged):
    with pytest.raises(ValueError, match="no observations at base period"):
        rebase(merged, "1999")


def test_growth_is_per_country_and_drops_the_first_period(merged):
    out = growth(merged)
    assert "2015" not in set(out["time_period"])
    nz = out.loc[out["ref_area"] == "NZL"].set_index("time_period")["obs_value"]
    assert nz.loc["2016"] == pytest.approx((29.4 / 28.9 - 1) * 100)
    # NZ has no 2019, so its 2020 change is measured against 2018 — the gap is not bridged.
    assert nz.loc["2020"] == pytest.approx((31.8 / 30.4 - 1) * 100)


def test_cagr_gives_one_row_per_country(merged):
    out = cagr(merged, "2015", "2020")
    assert len(out) == out["ref_area"].nunique()
    nz = out.loc[out["ref_area"] == "NZL", "obs_value"].iloc[0]
    assert nz == pytest.approx(((31.8 / 28.9) ** (1 / 5) - 1) * 100)


def test_cagr_rejects_a_backwards_window(merged):
    with pytest.raises(ValueError, match="at least a year"):
        cagr(merged, "2020", "2015")


def test_aggregate_adds_a_synthetic_median_row(merged):
    out = aggregate(merged, stat="median")
    med = out.loc[(out["ref_area"] == "OECD_MEDIAN") & (out["time_period"] == "2020"), "obs_value"]
    expected = merged.loc[merged["time_period"] == "2020", "obs_value"].median()
    assert med.iloc[0] == pytest.approx(expected)
    assert out.loc[out["ref_area"] == "OECD_MEDIAN", "source"].unique().tolist() == ["derived"]


def test_aggregate_can_exclude_the_spliced_country(merged):
    members = [a for a in merged["ref_area"].unique() if a != "NZL"]
    out = aggregate(merged, stat="mean", areas=members, label="OECD_MEAN_EXNZ")
    got = out.loc[(out["ref_area"] == "OECD_MEAN_EXNZ") & (out["time_period"] == "2020"), "obs_value"].iloc[0]
    expected = merged.loc[
        (merged["time_period"] == "2020") & (merged["ref_area"] != "NZL"), "obs_value"
    ].mean()
    assert got == pytest.approx(expected)


def test_gap_to_measures_distance_from_the_benchmark(merged):
    out = gap_to(aggregate(merged, stat="median"), "OECD_MEDIAN")
    assert "OECD_MEDIAN" not in set(out["ref_area"])
    median_2020 = merged.loc[merged["time_period"] == "2020", "obs_value"].median()
    nz = out.loc[(out["ref_area"] == "NZL") & (out["time_period"] == "2020"), "obs_value"].iloc[0]
    assert nz == pytest.approx(31.8 - median_2020)


def test_gap_to_percent(merged):
    out = gap_to(aggregate(merged, stat="median"), "OECD_MEDIAN", pct=True)
    median_2020 = merged.loc[merged["time_period"] == "2020", "obs_value"].median()
    nz = out.loc[(out["ref_area"] == "NZL") & (out["time_period"] == "2020"), "obs_value"].iloc[0]
    assert nz == pytest.approx((31.8 / median_2020 - 1) * 100)


def test_gap_to_unknown_benchmark_is_an_error(merged):
    with pytest.raises(ValueError, match="not in the frame"):
        gap_to(merged, "OECD_MEDIAN")


def test_rank_is_within_period_and_ignores_aggregates(merged):
    out = rank(aggregate(merged, stat="median"), ascending=False)
    assert "OECD_MEDIAN" not in set(out["ref_area"])
    year = out.loc[out["time_period"] == "2020"].sort_values("rank")
    assert year["rank"].tolist() == list(range(1, len(year) + 1))
    assert year.iloc[0]["obs_value"] == year["obs_value"].max()
    assert year["n_ranked"].unique().tolist() == [len(year)]


def test_zscore_standardises_within_period(merged):
    out = zscore(merged)
    year = out.loc[out["time_period"] == "2020", "obs_value"]
    assert year.mean() == pytest.approx(0, abs=1e-9)


def test_per_capita_divides_and_drops_unmatched(merged):
    pop = pd.DataFrame({
        "ref_area": ["NZL"] * 5,
        "time_period": ["2015", "2016", "2017", "2018", "2020"],
        "obs_value": [4.6e6, 4.7e6, 4.8e6, 4.9e6, 5.1e6],
    })
    out = per_capita(merged, pop, multiplier=1_000_000)
    assert set(out["ref_area"]) == {"NZL"}
    assert out.loc[out["time_period"] == "2020", "obs_value"].iloc[0] == pytest.approx(31.8 / 5.1e6 * 1e6)
    assert out["unit"].iloc[0].endswith("_PC")


def test_interpolate_fills_the_2019_hole_and_flags_it(merged):
    nz_only = filter_areas(merged, ["NZL"])
    out = interpolate_gaps(nz_only)
    row = out.loc[out["time_period"] == "2019"]
    assert len(row) == 1
    assert row["obs_value"].iloc[0] == pytest.approx((30.4 + 31.8) / 2)
    assert row["obs_status"].iloc[0] == "I"
    # only the filled row carries the flag; the real observations keep their own status
    assert out.loc[out["time_period"] != "2019", "obs_status"].dropna().tolist() == []


def test_smooth_keeps_the_series_length(merged):
    out = smooth(filter_areas(merged, ["AUS"]), window=3)
    assert len(out) == 6


def test_wide_is_a_country_by_period_matrix(merged):
    table = wide(merged)
    assert list(table.index) == ["2015", "2016", "2017", "2018", "2019", "2020"]
    assert "NZL" in table.columns
    assert pd.isna(table.loc["2019", "NZL"])


def test_panel_chains(merged):
    out = (
        Panel(merged)
        .filter_periods("2015", "2020")
        .aggregate(stat="median")
        .gap_to("OECD_MEDIAN")
        .rank(ascending=False)
    )
    assert isinstance(out, Panel)
    assert "rank" in out.df.columns
    assert "<Panel" in repr(out)


def test_panel_writes_csv(merged, tmp_path):
    target = tmp_path / "out.csv"
    Panel(merged).rebase("2015").to_csv(target)
    assert pd.read_csv(target)["ref_area"].nunique() == 6
