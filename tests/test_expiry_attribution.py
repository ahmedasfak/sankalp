"""agent/Discovery/expiry_attribution.py: the scheme-link and tier analysis behind the insight screen.

Expected values were checked by hand against the raw CSVs.
"""
import pandas as pd
import pytest

import agent.Discovery.expiry_attribution as ea


@pytest.fixture(scope="module")
def r():
    return ea.run("2025-10-01")


def test_tiers_from_annexure_b():
    t = ea.scheme_tiers()
    assert len(t["Tier A"]) == 10 and len(t["Tier B"]) == 5
    assert "PFL1101" in t["Tier A"] and "PFL1401" in t["Tier B"]


def test_cleaning(r):
    assert r["raw_rows"] == (93809, 4526) and r["clean_rows"] == (93064, 4503)


def test_claims_in_scope(r):
    assert r["claims_in_scope"]["claims"] == 2171 and round(r["claims_in_scope"]["value_cr"], 2) == 5.29


def test_headline_91_3(r):
    assert round(r["link"].loc["Bought at least once on a scheme line", "share_pct"], 1) == 91.3


def test_caveat_overlap(r):
    assert r["overlap"]["pair_also_bought_off_scheme"] == 1547


def test_pack_weighted_and_baseline(r):
    assert round(r["pack_weighted_pct"], 1) == 51.4
    assert round(r["baseline"]["sales_value_in_scheme_pairs_pct"], 1) == 41.4


def test_claim_rates(r):
    rates = r["claim_rates"].set_index(["scope", "pairs"]).claim_rate_pct.round(2)
    assert rates[("All SKUs", "Bought on a scheme line")] == 2.92
    assert rates[("All SKUs", "Never on a scheme line")] == 0.27
    assert rates[("Tier A only", "Never on a scheme line")] == 0.58


def test_tier_a_82(r):
    assert round(r["tiers_all"].loc["Tier A", "share_of_claims_pct"], 1) == 82.1
    assert round(r["tiers_all"].loc["Tier A", "share_of_sales_pct"], 1) == 44.0


def test_pack_weighting_on_a_toy_pair():
    pairs = pd.DataFrame({"any_scheme": [True], "scheme_share": [0.25], "packs": [100], "scheme_packs": [25], "lines": [2]},
                         index=pd.MultiIndex.from_tuples([("S1", "B1")], names=["stockist_code", "batch_no"]))
    m = pd.DataFrame({"stockist_code": ["S1"], "batch_no": ["B1"], "val": [1000.0]}).merge(
        pairs, left_on=["stockist_code", "batch_no"], right_index=True)
    assert ea.a_pack_weighted_share(m) == 25.0
