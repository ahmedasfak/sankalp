"""claim_validate.py: every rule, the routing, the decision, and real register claims.

Unit tests change one field of a real, clean claim (CLM-2603-01616) so each rule is
tested in isolation. Expected outcomes for real claims were agreed by reading the raw
CSV rows by hand.
"""
import pandas as pd
import pytest

import claim_validate as cv

PASS, FAIL, UNKNOWN, INFO = cv.PASS, cv.FAIL, cv.UNKNOWN, cv.INFO


@pytest.fixture()
def clean(register):
    """CLM-2603-01616: near expiry, STK0025, batch F2440122 (PFL1401), 272 packs, valid on every rule."""
    return register[register.claim_key == "CLM-2603-01616"].iloc[0].copy()


def changed(row, **kw):
    r = row.copy()
    for k, v in kw.items():
        r[k] = v
    return r


# ---------------------------------------------------------------- policy values come from config.py
def test_policy_values_come_from_config():
    assert (cv.NE_DAYS_BEFORE, cv.EXP_DAYS_AFTER, cv.BREAKAGE_DAYS, cv.SHORT_SUPPLY_DAYS, cv.CN_DAYS) == (90, 90, 7, 7, 30)
    assert cv.AM_APPROVER == "Area Manager"


# ---------------------------------------------------------------- §5.3 batch exists and belongs to the SKU
def test_batch_exists_pass(clean):
    assert cv.rule_batch(clean)["result"] == PASS


def test_batch_of_another_sku_fails(clean):
    assert cv.rule_batch(changed(clean, sku_code="PFL1001"))["result"] == FAIL


def test_batch_not_in_master_needs_a_person(clean):
    assert cv.rule_batch(changed(clean, batch_no="Z9999999"))["result"] == UNKNOWN


# ---------------------------------------------------------------- §5.3 claimed expiry matches the batch master
def test_expiry_matches_pass(clean):
    assert cv.rule_expiry_matches(clean)["result"] == PASS


def test_expiry_mismatch_fails(clean):
    assert cv.rule_expiry_matches(changed(clean, exp=pd.Timestamp("2027-05-31")))["result"] == FAIL


def test_expiry_missing_is_unknown(clean):
    assert cv.rule_expiry_matches(changed(clean, exp=pd.NaT))["result"] == UNKNOWN


# ---------------------------------------------------------------- §5.2 window on the expiry date (expiry 31-May-2026)
@pytest.mark.parametrize("kind, claim_date, expected", [
    ("near_expiry", "2026-03-02", PASS),     # exactly 90 days before
    ("near_expiry", "2026-03-01", FAIL),     # 91 days before
    ("near_expiry", "2026-05-31", PASS),
    ("near_expiry", "2026-06-10", UNKNOWN),  # after expiry: inside the expired window, so the type may be wrong
    ("expiry", "2026-08-29", PASS),          # 90 days after
    ("expiry", "2026-08-30", FAIL),          # 91 days after
    ("expiry", "2026-05-20", UNKNOWN),       # before expiry: inside the near-expiry window
])
def test_expiry_window(clean, kind, claim_date, expected):
    assert cv.rule_window_expiry(changed(clean, date=pd.Timestamp(claim_date)), kind)["result"] == expected


# ---------------------------------------------------------------- §5.2 window on the invoice date (invoice 30-Dec-2024)
@pytest.mark.parametrize("kind", ["breakage_in_transit", "short_supply"])
@pytest.mark.parametrize("claim_date, expected", [("2024-12-30", PASS), ("2025-01-06", PASS), ("2025-01-07", FAIL), ("2024-12-29", FAIL)])
def test_invoice_window(clean, kind, claim_date, expected):
    assert cv.rule_window_invoice(changed(clean, date=pd.Timestamp(claim_date)), kind)["result"] == expected


def test_invoice_window_without_invoice_is_unknown(clean):
    assert cv.rule_window_invoice(changed(clean, inv=None), "short_supply")["result"] == UNKNOWN


# ---------------------------------------------------------------- §5.3-5.4 invoice reference
def test_invoice_ref_pass(clean):
    r = cv.rule_invoice_ref(clean)
    assert r["result"] == PASS and r["evidence"]


def test_missing_invoice_ref_needs_area_manager_evidence(clean):
    r = cv.rule_invoice_ref(changed(clean, inv=None))
    assert r["result"] == UNKNOWN and "Area Manager" in r["detail"]


def test_invoice_not_in_extract_is_unknown(clean):
    assert cv.rule_invoice_ref(changed(clean, inv="INV/N01/2311/000001"))["result"] == UNKNOWN


def test_invoice_of_another_stockist_fails(clean):
    assert cv.rule_invoice_ref(changed(clean, stockist_code="STK0001"))["result"] == FAIL


def test_batch_not_on_the_invoice_fails(clean):
    assert cv.rule_invoice_ref(changed(clean, batch_no="K2300101"))["result"] == FAIL


def test_invoice_written_with_hyphens_is_still_found(clean):
    assert cv.rule_invoice_ref(changed(clean, inv="INV-N01/2412/022066"))["result"] == PASS


# ---------------------------------------------------------------- §5.5 quantity limit (2,457 packs invoiced incl. free)
def test_quantity_within_limit_passes(clean):
    assert cv.rule_quantity(changed(clean, qty=2457))["result"] == PASS


def test_quantity_one_pack_over_fails(clean):
    r = cv.rule_quantity(changed(clean, qty=2458))
    assert r["result"] == FAIL and "over by 1" in r["detail"]


def test_quantity_adds_earlier_claims(register):
    later = register[register.claim_key == "CLM-2605-04488"].iloc[0]
    assert "272 + earlier claims 272 = 544" in cv.rule_quantity(later)["detail"]


def test_quantity_without_a_sale_is_unknown(clean):
    assert cv.rule_quantity(changed(clean, stockist_code="STK0156"))["result"] == UNKNOWN


# ---------------------------------------------------------------- §5.6 duplicate
def test_duplicate_same_stockist_batch_qty_fails(register):
    later = register[register.claim_key == "CLM-2605-04488"].iloc[0]
    r = cv.rule_duplicate(later)
    assert r["result"] == FAIL and "CLM-2603-01616" in r["detail"]


def test_first_claim_is_not_a_duplicate(clean):
    assert cv.rule_duplicate(clean)["result"] == PASS


def test_different_quantity_is_not_a_duplicate(register):
    later = register[register.claim_key == "CLM-2605-04488"].iloc[0]
    assert cv.rule_duplicate(changed(later, qty=100))["result"] == PASS


def test_rejected_earlier_claims_do_not_count(register):
    rejected = register[register.status == "Rejected"].iloc[0]
    probe = changed(rejected, claim_key="CLM-9999-99999", date=rejected.date + pd.Timedelta(days=1))
    assert (cv._earlier(probe).status != "Rejected").all()


# ---------------------------------------------------------------- §5.7 value = quantity x PTS (PFL1401 PTS 98.7)
def test_value_pass(clean):
    assert cv.rule_value(clean)["result"] == PASS


def test_value_within_one_rupee_passes(clean):
    assert cv.rule_value(changed(clean, val=clean.val + 0.9))["result"] == PASS


def test_value_mismatch_fails(clean):
    assert cv.rule_value(changed(clean, val=clean.val + 10))["result"] == FAIL


def test_blank_value_is_unknown_with_expected_amount(clean):
    r = cv.rule_value(changed(clean, val=float("nan")))
    assert r["result"] == UNKNOWN and "26,846.40" in r["detail"]


# ---------------------------------------------------------------- §5.1 billing C&F
def test_billing_cfa_pass(clean):
    assert cv.rule_billing_cfa(clean)["result"] == PASS


def test_claim_at_another_cfa_fails(clean):
    assert cv.rule_billing_cfa(changed(clean, cnf_code="CF-S01"))["result"] == FAIL


# ---------------------------------------------------------------- §5.6 settlement (information only)
def test_settlement_is_information_only(clean):
    r = cv.info_settlement(clean)
    assert r["result"] == INFO and "32 days (late" in r["detail"]


# ---------------------------------------------------------------- routing and decision
@pytest.mark.parametrize("claim_type, node", [("Near expiry", "near_expiry"), ("Expired", "expiry"),
                                              ("Short supply", "short_supply"), ("Breakage in transit", "breakage_in_transit"),
                                              ("Price difference", "other")])
def test_triage_claim(claim_type, node):
    assert cv.triage_claim({"found": True, "claim": {"claim_type": claim_type}}) == node


def test_not_found_routes_to_other():
    assert cv.triage_claim({"found": False}) == "other"


@pytest.mark.parametrize("results, verdict", [
    ([PASS, PASS, INFO], "APPROVE"), ([PASS, UNKNOWN, INFO], "NEEDS_PERSON"),
    ([PASS, UNKNOWN, FAIL], "REJECT"), ([], "APPROVE")])
def test_decide(results, verdict):
    checks = [{"rule": f"r{i}", "result": r, "detail": "", "clause": "", "evidence": []} for i, r in enumerate(results)]
    assert cv.decide({"found": False, "checks": checks})["verdict"] == verdict


# ---------------------------------------------------------------- check set: real register claims, agreed by hand
CHECK_SET = [
    ("CLM-2605-04488", "REJECT", "duplicate of CLM-2603-01616, already credited"),
    ("CLM-2603-01616", "APPROVE", "near expiry 72 days before expiry, every rule passes"),
    ("CLM-2609-03036", "REJECT", "filed 92 days before expiry"),
    ("CLM-2609-02954", "REJECT", "filed 92 days before expiry (value also blank)"),
    ("CLM-2609-02999", "REJECT", "2,338 packs claimed, 2,336 invoiced"),
    ("CLM-2609-04352", "REJECT", "breakage reported 8 days after invoice"),
    ("CLM-2609-02810", "NEEDS_PERSON", "expired, no invoice reference"),
    ("CLM-2503-03253", "NEEDS_PERSON", "batch archived before Oct 2023"),
    ("CLM-2609-04310", "APPROVE", "breakage reported 4 days after invoice"),
    ("CLM-2609-02118", "APPROVE", "expired 30 days ago, within 90"),
]


@pytest.mark.parametrize("claim_no, verdict, why", CHECK_SET)
def test_check_set(claim_no, verdict, why):
    assert cv.validate(claim_no)["verdict"] == verdict, why


def test_recovery_flag_on_credited_duplicate():
    assert "candidate for recovery" in cv.validate("CLM-2605-04488")["summary"]


def test_unknown_claim_number_is_not_guessed():
    r = cv.validate("CLM-0000-00000")
    assert r["found"] is False and r["verdict"] == "NEEDS_PERSON"


def test_claim_number_is_case_and_space_insensitive():
    assert cv.validate("  clm-2603-01616 ")["verdict"] == "APPROVE"


def test_breakage_skips_the_expiry_rule():
    rules = {k["rule"] for k in cv.validate("CLM-2609-04310")["checks"]}
    assert "expiry_matches" not in rules and "window" in rules
