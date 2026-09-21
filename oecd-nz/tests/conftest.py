import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from oecdnz.normalise import to_tidy  # noqa: E402
from oecdnz.sdmx import read_local_sdmx_csv  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def panel() -> pd.DataFrame:
    """Five OECD members, 2015-2020, no NZL — the hole we are filling."""
    return read_local_sdmx_csv(FIXTURES / "oecd_panel.csv", series="DSD_WEALTH@DF_EXAMPLE")


@pytest.fixture
def nz() -> pd.DataFrame:
    """A Stats NZ style export: different column names, missing 2019."""
    raw = pd.read_csv(FIXTURES / "statsnz_series.csv")
    return to_tidy(
        raw,
        source="Stats NZ",
        mapping={"Period": "time_period", "Data_value": "obs_value"},
        constants={"ref_area": "NZL", "ref_area_label": "New Zealand",
                   "indicator": "SHARE_TOP10", "unit": "PT_B1GQ"},
        series="Household net worth: share held by top 10%",
    )
