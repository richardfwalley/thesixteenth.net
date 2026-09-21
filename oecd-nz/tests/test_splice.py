import pandas as pd
import pytest

from oecdnz.splice import compare_overlap, splice


def test_nz_is_added_with_provenance(panel, nz):
    merged, report = splice(panel, nz)
    assert "NZL" in set(merged["ref_area"])
    added = merged.loc[merged["ref_area"] == "NZL"]
    assert len(added) == 5
    assert added["spliced"].all()
    assert added["source"].unique().tolist() == ["Stats NZ"]
    assert not merged.loc[merged["ref_area"] != "NZL", "spliced"].any()
    assert report.n_rows_added == 5
    assert report.ok


def test_report_names_the_gap_against_the_panel(panel, nz):
    _, report = splice(panel, nz)
    assert report.missing_vs_panel == ("2019",)
    assert "2019" not in report.periods_added
    assert "no observation for 1 period" in report.footnote()


def test_footnote_states_the_splice(panel, nz):
    _, report = splice(panel, nz)
    note = report.footnote()
    assert "NZL" in note and "2015–2020" in note and "not published" in note


def test_unit_mismatch_is_fatal_by_default(panel, nz):
    wrong = nz.copy()
    wrong["unit"] = "USD_PPP"
    with pytest.raises(ValueError, match="unit mismatch"):
        splice(panel, wrong)
    merged, report = splice(panel, wrong, strict_units=False)
    assert any("unit mismatch" in w for w in report.warnings)
    assert len(merged.loc[merged["ref_area"] == "NZL"]) == 5


def test_scale_mismatch_warns(panel, nz):
    scaled = nz.copy()
    scaled["unit_mult"] = 3
    _, report = splice(panel, scaled)
    assert any("scale mismatch" in w for w in report.warnings)


def test_frequency_mismatch_warns(panel, nz):
    quarterly = nz.copy()
    quarterly["freq"] = "Q"
    _, report = splice(panel, quarterly)
    assert any("frequency mismatch" in w for w in report.warnings)


def test_missing_area_in_incoming_is_an_error(panel, nz):
    with pytest.raises(ValueError, match="no rows for ref_area"):
        splice(panel, nz, area="AUS")


def test_untidy_input_is_rejected(panel, nz):
    with pytest.raises(ValueError, match="not tidy"):
        splice(panel.drop(columns=["unit"]), nz)


def _panel_with_partial_nz(panel, values):
    rows = [
        {**panel.iloc[0].to_dict(), "ref_area": "NZL", "ref_area_label": "New Zealand",
         "time_period": period, "obs_value": value}
        for period, value in values.items()
    ]
    return pd.concat([panel, pd.DataFrame(rows)], ignore_index=True)


def test_existing_rows_block_a_silent_splice(panel, nz):
    with_nz = _panel_with_partial_nz(panel, {"2015": 33.0, "2016": 33.5})
    _, report = splice(with_nz, nz)
    assert any("already has 2 period" in w for w in report.warnings)
    assert not report.ok


def test_overwrite_replaces_the_oecd_rows(panel, nz):
    with_nz = _panel_with_partial_nz(panel, {"2015": 33.0, "2016": 33.5})
    merged, report = splice(with_nz, nz, overwrite=True)
    nz_rows = merged.loc[merged["ref_area"] == "NZL"].set_index("time_period")
    assert len(nz_rows) == 5
    assert nz_rows.loc["2015", "obs_value"] == 28.9
    assert report.ok


def test_ratio_link_puts_the_domestic_series_on_the_oecd_basis(panel, nz):
    with_nz = _panel_with_partial_nz(panel, {"2015": 33.0, "2016": 34.0})
    merged, report = splice(with_nz, nz, link="ratio", overwrite=True)
    expected = ((33.0 / 28.9) + (34.0 / 29.4)) / 2
    assert report.link_method == "ratio"
    assert report.link_factor == pytest.approx(expected)
    value_2020 = merged.loc[
        (merged["ref_area"] == "NZL") & (merged["time_period"] == "2020"), "obs_value"
    ].iloc[0]
    assert value_2020 == pytest.approx(31.8 * expected)
    assert "scaled onto the OECD basis" in report.footnote()


def test_level_link_shifts_instead_of_scaling(panel, nz):
    with_nz = _panel_with_partial_nz(panel, {"2015": 33.0, "2016": 34.0})
    merged, report = splice(with_nz, nz, link="level", overwrite=True)
    expected = ((33.0 - 28.9) + (34.0 - 29.4)) / 2
    assert report.link_factor == pytest.approx(expected)
    value_2017 = merged.loc[
        (merged["ref_area"] == "NZL") & (merged["time_period"] == "2017"), "obs_value"
    ].iloc[0]
    assert value_2017 == pytest.approx(30.1 + expected)


def test_link_without_an_anchor_warns_and_inserts_unadjusted(panel, nz):
    merged, report = splice(panel, nz, link="ratio")
    assert report.link_method == "none"
    assert any("no NZL observations to anchor" in w for w in report.warnings)
    assert merged.loc[
        (merged["ref_area"] == "NZL") & (merged["time_period"] == "2015"), "obs_value"
    ].iloc[0] == 28.9


def test_thin_coverage_warns_about_unbalanced_comparisons(panel, nz):
    thin = nz.loc[nz["time_period"].isin(["2015", "2016"])]
    _, report = splice(panel, thin)
    assert any("unbalanced" in w for w in report.warnings)


def test_compare_overlap_shows_both_sources(panel, nz):
    with_nz = _panel_with_partial_nz(panel, {"2015": 33.0, "2016": 34.0})
    table = compare_overlap(with_nz, nz)
    assert table.loc["2015", "panel"] == 33.0
    assert table.loc["2015", "incoming"] == 28.9
    assert table.loc["2015", "diff"] == pytest.approx(-4.1)
    assert table.loc["2020", "panel"] != table.loc["2020", "panel"]  # NaN: OECD has no 2020
