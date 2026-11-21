"""business_insights.py: the cleaning helpers its figures depend on."""
import pandas as pd

from agent.business_insights import normalize_code, parse_mixed_dates, parse_numbers


def test_parse_mixed_dates_reads_iso_and_day_first():
    out = parse_mixed_dates(pd.Series(["2025-09-30", "30-09-2025", "01-Apr-2024", "05-04-2024"]))
    assert [d.strftime("%Y-%m-%d") for d in out] == ["2025-09-30", "2025-09-30", "2024-04-01", "2024-04-05"]


def test_parse_numbers_removes_commas():
    assert parse_numbers(pd.Series(["137,112.00", "26075.6", "x"])).tolist()[:2] == [137112.0, 26075.6]
    assert parse_numbers(pd.Series(["x"])).isna().all()


def test_normalize_code():
    assert normalize_code(pd.Series([" cf-n01 ", "CFN01"]), remove_hyphens=True).tolist() == ["CFN01", "CFN01"]
    assert normalize_code(pd.Series([" stk0039 "])).tolist() == ["STK0039"]
