"""rules.py: triage, claim pre-check, date reading and the CO-POL-014 §5.2 claim window."""
from datetime import date, datetime

import pytest

import rules
from rules import check_claim_window, claim_precheck_validation, to_date, triage


# ---------------------------------------------------------------- triage (routing by claim type)
@pytest.mark.parametrize("label, node", [
    ("NEAR_EXPIRY", "near_expiry"), ("NEAR EXPIRY", "near_expiry"), ("near_expiry", "near_expiry"),
    ("EXPIRED", "expiry"), ("EXPIRY", "expiry"),
    ("SHORT_SUPPLY", "short_supply"), ("SHORT SUPPLY", "short_supply"),
    ("BREAKAGE_IN_TRANSIT", "breakage_in_transit"), ("BREAKAGE IN TRANSIT", "breakage_in_transit"),
    ("OTHER", "other"), ("", "other"), ("price query", "other"),
])
def test_triage_routes_every_label(label, node):
    assert triage({"analysis": label}) == node


# ---------------------------------------------------------------- pre-check: all four fields present
def test_precheck_passes_when_all_fields_present():
    msg = {"batch_no": "L2420268", "invoice_no": "INV/N02/2505/036911", "Expiry": "Oct-2026", "Qty": "43 boxes"}
    assert isinstance(claim_precheck_validation(msg), list)


@pytest.mark.parametrize("missing", ["batch_no", "invoice_no", "Expiry", "Qty"])
def test_precheck_fails_when_a_field_is_missing(missing):
    msg = {"batch_no": "L2420268", "invoice_no": "INV/N02/2505/036911", "Expiry": "Oct-2026", "Qty": "43 boxes"}
    msg[missing] = None
    assert claim_precheck_validation(msg) == "invalid_node"


# ---------------------------------------------------------------- to_date: the three formats in the extracts
@pytest.mark.parametrize("text", ["30-09-2025", "2025-09-30", "30-Sep-2025", "30/09/2025", " 30-09-2025 "])
def test_to_date_reads_every_extract_format(text):
    assert to_date(text) == date(2025, 9, 30)


@pytest.mark.parametrize("value", [None, "", "nan", "NaT", "None", "not a date", "2025/30/09"])
def test_to_date_returns_none_instead_of_guessing(value):
    assert to_date(value) is None


def test_to_date_passes_dates_through():
    assert to_date(date(2026, 1, 5)) == date(2026, 1, 5)
    assert to_date(datetime(2026, 1, 5, 10, 30)) == date(2026, 1, 5)


# ---------------------------------------------------------------- claim window (CO-POL-014 §5.2)
EXP = "31-12-2026"


def window(*args):
    return check_claim_window(*args)["result"]


def test_windows_match_policy_values():
    assert rules.CLAIM_WINDOWS["NEAR EXPIRY"]["days_before"] == 90
    assert rules.CLAIM_WINDOWS["EXPIRED"]["days_after"] == 90
    assert rules.CLAIM_WINDOWS["BREAKAGE_IN_TRANSIT"]["max_days_after_invoice"] == 7
    assert rules.CLAIM_WINDOWS["SHORT_SUPPLY"]["max_days_after_invoice"] == 7


@pytest.mark.parametrize("claim_date, expected", [
    ("02-10-2026", "pass"),    # 90 days before expiry: first day of the window
    ("01-10-2026", "fail"),    # 91 days before
    ("31-12-2026", "pass"),    # expiry day
    ("01-01-2027", "fail"),    # day after expiry: a near-expiry claim is too late
])
def test_near_expiry_window_boundaries(claim_date, expected):
    assert window("NEAR_EXPIRY", claim_date, EXP, None) == expected


@pytest.mark.parametrize("claim_date, expected", [
    ("31-12-2026", "pass"),    # expiry day
    ("31-03-2027", "pass"),    # 90 days after
    ("01-04-2027", "fail"),    # 91 days after: rejected under any circumstances
    ("30-12-2026", "fail"),    # before expiry is not "expired"
])
def test_expired_window_boundaries(claim_date, expected):
    assert window("EXPIRED", claim_date, EXP, None) == expected


@pytest.mark.parametrize("claim_type", ["BREAKAGE_IN_TRANSIT", "SHORT_SUPPLY", "SHORT SUPPLY"])
@pytest.mark.parametrize("claim_date, expected", [("01-06-2026", "pass"), ("08-06-2026", "pass"),
                                                  ("09-06-2026", "fail"), ("31-05-2026", "fail")])
def test_invoice_window_is_seven_days(claim_type, claim_date, expected):
    assert window(claim_type, claim_date, None, "01-06-2026") == expected


def test_window_accepts_mixed_date_formats():
    assert window("NEAR_EXPIRY", "01-12-2026", "2026-12-31", None) == "pass"
    assert window("BREAKAGE_IN_TRANSIT", "03-06-2026", None, "01-Jun-2026") == "pass"


@pytest.mark.parametrize("args, why", [
    (("NEAR_EXPIRY", "01-12-2026", None, None), "expiry date missing"),
    (("SHORT_SUPPLY", "01-12-2026", None, None), "invoice date missing"),
    (("NEAR_EXPIRY", None, EXP, None), "claim (received) date"),
    (("PRICE_DIFFERENCE", "01-12-2026", EXP, None), "unknown claim type"),
])
def test_window_is_unknown_when_a_fact_is_missing(args, why):
    out = check_claim_window(*args)
    assert out["result"] == "unknown" and why in out["detail"]
