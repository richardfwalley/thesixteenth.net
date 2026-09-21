"""Splice a non-member country series into an OECD panel, then manipulate the result.

Built for the New Zealand case: an OECD dataflow that omits NZL, backfilled from a
domestic source (Stats NZ, RBNZ, Treasury), with provenance kept on every row.

    from oecdnz import OecdClient, Query, DataflowRef, load_domestic, splice, Panel
"""

__version__ = "0.1.0"

from .normalise import TIDY_COLUMNS, coverage, rescale, to_tidy
from .sdmx import DataflowRef, EgressBlocked, OecdClient, Query, read_local_sdmx_csv
from .sources import load_domestic
from .splice import SpliceReport, compare_overlap, splice
from .transform import Panel, wide

__all__ = [
    "TIDY_COLUMNS", "coverage", "rescale", "to_tidy",
    "DataflowRef", "EgressBlocked", "OecdClient", "Query", "read_local_sdmx_csv",
    "load_domestic", "SpliceReport", "compare_overlap", "splice", "Panel", "wide",
]
