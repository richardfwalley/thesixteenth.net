import pytest

from oecdnz.basis import Basis, compare
from oecdnz.splice import splice

CIS = Basis(
    survey="National innovation surveys (CIS-type)", manual="Oslo Manual 2018",
    reference_period_years=3, size_threshold=10,
)
BOS = Basis(
    survey="Business Operations Survey", manual="Oslo Manual 2018",
    reference_period_years=2, size_threshold=6,
)


def test_describe_reads_as_a_footnote_clause():
    assert CIS.describe() == (
        "National innovation surveys (CIS-type), 3-year reference period, 10+ employees"
    )


def test_matching_fields_produce_nothing():
    warnings, notes = compare(CIS, CIS)
    assert warnings == [] and notes == []


def test_reference_period_and_threshold_mismatches_carry_a_direction():
    warnings, notes = compare(CIS, BOS)
    assert any("reference period years" in w for w in warnings)
    assert any("size threshold" in w for w in warnings)
    assert not any("manual" in w for w in warnings), "matching fields must stay quiet"
    assert any("depress the measured rate" in n for n in notes)


def test_unknown_field_on_one_side_is_not_a_mismatch():
    warnings, _ = compare(CIS, Basis(survey="Business Operations Survey"))
    assert len(warnings) == 1 and "survey" in warnings[0]


def test_a_missing_basis_is_itself_flagged():
    warnings, notes = compare(CIS, None)
    assert warnings and "unverified" in warnings[0]
    assert notes == []
    assert compare(None, None) == ([], [])


def test_unknown_basis_field_is_rejected_by_name():
    with pytest.raises(ValueError, match="unknown basis field"):
        Basis.from_mapping({"survey": "BOS", "sample_size": 7000})


def test_from_mapping_round_trips():
    assert Basis.from_mapping(CIS.as_dict()) == CIS
    assert Basis.from_mapping(None) is None


def test_splice_surfaces_the_basis_gap(panel, nz):
    merged, report = splice(panel, nz, panel_basis=CIS, incoming_basis=BOS)
    assert len(merged.loc[merged["ref_area"] == "NZL"]) == 5, "the splice still happens"
    assert not report.ok, "an incomparable basis must not pass silently"
    assert any("basis mismatch" in w for w in report.warnings)
    footnote = report.footnote()
    assert "3-year reference period" in footnote and "2-year reference period" in footnote
    assert "tends to depress the measured rate" in footnote


def test_source_notes_reach_the_footnote(panel, nz):
    noted = Basis(survey="Business Operations Survey", notes="BOS 2023 changed its process question.")
    _, report = splice(panel, nz, panel_basis=CIS, incoming_basis=noted)
    assert "BOS 2023 changed its process question." in report.footnote()
