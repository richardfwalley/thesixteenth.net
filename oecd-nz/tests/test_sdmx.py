from pathlib import Path

import pandas as pd
import pytest
import requests

from oecdnz.sdmx import DataflowRef, EgressBlocked, OecdClient, Query, members

FIXTURES = Path(__file__).resolve().parent / "fixtures"
FLOW = DataflowRef("OECD.WISE.INE", "DSD_WEALTH@DF_EXAMPLE", "1.0")


class FakeResponse:
    def __init__(self, status_code=200, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class FakeSession:
    def __init__(self, response=None, raises=None):
        self.headers = {}
        self.response = response
        self.raises = raises
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        if self.raises:
            raise self.raises
        return self.response


def test_query_url_and_params():
    query = Query(FLOW, key="AUS+CAN.SHARE_TOP10", start_period="2015", end_period="2020")
    assert query.url().endswith("/data/OECD.WISE.INE,DSD_WEALTH@DF_EXAMPLE,1.0/AUS+CAN.SHARE_TOP10")
    params = query.params()
    assert params["startPeriod"] == "2015" and params["endPeriod"] == "2020"
    assert params["format"] == "csvfilewithlabels"


def test_cache_key_is_stable_and_query_specific():
    a = Query(FLOW, key="AUS", start_period="2015")
    b = Query(FLOW, key="AUS", start_period="2015")
    c = Query(FLOW, key="CAN", start_period="2015")
    assert a.cache_key() == b.cache_key()
    assert a.cache_key() != c.cache_key()


def test_fetch_parses_and_then_serves_from_cache(tmp_path):
    csv_text = (FIXTURES / "oecd_panel.csv").read_text()
    session = FakeSession(FakeResponse(200, csv_text))
    client = OecdClient(cache_dir=tmp_path, session=session)

    frame = client.fetch(Query(FLOW))
    assert len(session.calls) == 1
    assert frame["ref_area"].nunique() == 5
    assert frame["source"].unique().tolist() == ["OECD"]

    again = client.fetch(Query(FLOW))
    assert len(session.calls) == 1, "second fetch should hit the on-disk cache"
    pd.testing.assert_frame_equal(frame, again)

    client.fetch(Query(FLOW), refresh=True)
    assert len(session.calls) == 2, "--refresh must bypass the cache"


def test_proxy_refusal_is_reported_as_egress_not_a_missing_dataset(tmp_path):
    session = FakeSession(raises=requests.exceptions.ProxyError("CONNECT tunnel failed"))
    client = OecdClient(cache_dir=tmp_path, session=session, retries=1)
    with pytest.raises(EgressBlocked, match="Allowlist"):
        client.fetch(Query(FLOW))


def test_404_names_the_dataflow(tmp_path):
    session = FakeSession(FakeResponse(404, "not found"))
    client = OecdClient(cache_dir=tmp_path, session=session)
    with pytest.raises(ValueError, match="no such dataflow"):
        client.fetch(Query(FLOW, key="BAD"))


def test_server_errors_are_retried_then_surfaced(tmp_path, monkeypatch):
    monkeypatch.setattr("oecdnz.sdmx.time.sleep", lambda _s: None)
    session = FakeSession(FakeResponse(503, "busy"))
    client = OecdClient(cache_dir=tmp_path, session=session, retries=3)
    with pytest.raises(RuntimeError, match="failed after 3 attempts"):
        client.fetch(Query(FLOW))
    assert len(session.calls) == 3


def test_members_drops_aggregates(panel):
    extra = pd.concat([panel, panel.head(1).assign(ref_area="EU27")], ignore_index=True)
    assert "EU27" not in members(extra)
    assert members(extra, exclude=["JPN"]) == ["AUS", "CAN", "GBR", "USA"]
