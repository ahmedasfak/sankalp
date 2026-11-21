"""graph_schema.py: scheme register, policy values and each analysis node (CO-POL-014 §4, §5.6, §7.1, Annex B).

Expected values were checked against the raw CSVs and the QBR pack.
"""
import pandas as pd
import pytest

import graph_schema as gs


@pytest.fixture(scope="module")
def f():
    return gs.frames()


# ---------------------------------------------------------------- policy values come from config.py
def test_policy_values_from_config():
    assert gs.CAP_PCT == 3                  # §4.4 free goods cap
    assert gs.STOCK_NORM_MONTHS == 2.5      # §4.5 stock norm for schemes
    assert gs.MIN_RSL_PCT == 60             # §7.1 minimum shelf life at dispatch
    assert gs.CN_DAYS == 30                 # §5.6 credit note
    assert (gs.VALID_FROM_DAY, gs.MOQ_MULTIPLE) == (22, 1.5)   # Annexure B


# ---------------------------------------------------------------- Annexure B circular register
def test_register_has_every_circular():
    reg = gs.scheme_register()
    assert len(reg) == 18 and set(reg.tier) == {"A", "B"}


@pytest.mark.parametrize("code, ratio", [("QS-FY25Q1-A", 0.1), ("QS-FY25Q2-A", 0.1), ("QS-FY25Q3-A", 0.2),
                                         ("QS-FY27Q2-A", 0.2), ("QS-FY25Q3-B", 0.1), ("QS-FY27Q2-B", 0.1)])
def test_free_ratio_per_circular(code, ratio):
    assert gs.scheme_register().loc[code, "free_per_pack"] == ratio


def test_as_references_resolve_to_sku_lists():
    reg = gs.scheme_register()
    assert len(reg.loc["QS-FY27Q2-A", "skus"]) == 10
    assert reg.loc["QS-FY27Q2-B", "skus"] == ["PFL1004", "PFL1104", "PFL1201", "PFL1302", "PFL1401"]


@pytest.mark.parametrize("code, start, end", [("QS-FY25Q1-A", "2024-06-22", "2024-06-30"),
                                              ("QS-FY25Q3-A", "2024-12-22", "2024-12-31"),
                                              ("QS-FY26Q4-B", "2026-03-22", "2026-03-31")])
def test_validity_window_22nd_to_month_end(code, start, end):
    reg = gs.scheme_register()
    assert str(reg.loc[code, "valid_from"].date()) == start and str(reg.loc[code, "valid_to"].date()) == end


def test_tier_of():
    s = pd.Series(["PFL1101", "PFL1401", "PFL1603"])
    assert gs.tier_of(s).tolist() == ["Tier A", "Tier B", "No scheme"]


@pytest.mark.parametrize("day, fq", [("2024-04-01", "FY25Q1"), ("2024-12-31", "FY25Q3"), ("2025-03-31", "FY25Q4"), ("2026-09-30", "FY27Q2")])
def test_financial_year_quarter(day, fq):
    assert gs.fy_quarter(pd.Series(pd.to_datetime([day]))).iloc[0] == fq


# ---------------------------------------------------------------- data checks
def test_repeated_rows_are_dropped(f):
    assert f["raw_sales_rows"] - len(f["sales"]) == 745
    assert f["raw_claim_rows"] - len(f["claims"]) == 23


# ---------------------------------------------------------------- §4.4 cap, by quarter
def test_quarterly_figures_match_the_qbr(f):
    q = gs.quarterly_claims_foc(f["sales"], f["claims"])
    assert round(q.loc["FY26Q1", "primary_cr"], 2) == 52.52 and round(q.loc["FY26Q1", "foc_pct"], 2) == 4.68


def test_free_goods_above_cap(f):
    q = gs.quarterly_claims_foc(f["sales"], f["claims"])
    assert (q.foc_above_cap_cr > 0).sum() == 7
    assert round(q.foc_above_cap_cr.sum(), 2) == 3.95
    assert q.loc["FY27Q2", "foc_above_cap_cr"] == 0          # 2.82%: below the cap


# ---------------------------------------------------------------- scheme link and tiers
def test_scheme_link(f):
    t = gs.scheme_link(f["sales"], f["claims"], "2025-10-01").loc["Since 2025-10-01"]
    assert round(t.loc["Bought on a quarter-end scheme", "share_pct"], 1) == 91.3


def test_tier_rates(f):
    t, ta = gs.tier_rates(f["sales"], f["claims"], f["sku"])
    assert round(t.loc["Tier A", "claims_pct_of_sales"], 2) == 2.85 and round(t.loc["No scheme", "claims_pct_of_sales"], 2) == 0.31
    assert ta.index[0] == "Vitamins and nutrition"


# ---------------------------------------------------------------- §7.1 shelf life and FEFO by C&F
def test_fefo_and_rsl_by_cfa(f):
    t = gs.fefo_dispatch(f["sales"], f["batch"], f["stock"], "2026-04-01")
    assert t.non_fefo_pct_proxy.idxmax() == "CF-E01" and t.loc["CF-E01", "non_fefo_pct_proxy"] > 75
    assert t.below_min_rsl_pct.idxmax() == "CF-E01"


# ---------------------------------------------------------------- §5.6 settlement
def test_settlement(f):
    summary, by_q = gs.settlement(f["claims"])
    assert summary["pending_claims"] == 360 and summary["pending_value_lakh"] == 94.4
    assert summary["policy_days"] == 30 and round(summary["avg_days_claim_to_cn"]) == 45


# ---------------------------------------------------------------- circular compliance (§4.2, Annex B)
def test_every_scheme_line_is_in_scope_and_in_window(f):
    t = gs.scheme_compliance(f["sales"])
    assert len(t) == 18
    assert int(t.sku_out_of_scope.sum()) == 0 and int(t.outside_window.sum()) == 0


# ---------------------------------------------------------------- the graph
def test_graph_runs_all_six_analyses():
    out = gs.run_scheme_pipeline()
    assert {s["key"] for s in out["sections"]} == set(gs.ORDER)
    assert all(s["sources"] for s in out["sections"]) and out["report"].startswith("# Scheme pipeline report")
