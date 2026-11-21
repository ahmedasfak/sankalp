"""run_claim_check.py: the helpers that turn graph_validate.py's output into the app's result.

graph_validate.py itself calls the model and draws its graph online, so these tests
cover the parsing, routing and error hints without importing it.
"""
import pytest

import run_claim_check as rcc


@pytest.mark.parametrize("label, node", [("NEAR EXPIRY", "near_expiry"), ("NEAR_EXPIRY", "near_expiry"), ("EXPIRED", "expiry"),
                                         ("SHORT_SUPPLY", "short_supply"), ("BREAKAGE_IN_TRANSIT", "breakage_in_transit")])
def test_route_mapping_matches_triage(label, node):
    assert rcc.ROUTE_OF.get(label.replace("_", " ")) == node


def test_window_result_is_read_from_the_printed_block():
    log = ("x\n====================output========================\n"
           "{'result': 'fail', 'detail': 'NEAR_EXPIRY: window 2026-07-02 to 2026-09-30'}\n"
           "==========================output end ===============\n")
    assert rcc._window_result(log) == {"result": "fail", "detail": "NEAR_EXPIRY: window 2026-07-02 to 2026-09-30"}


def test_no_block_means_no_window_result():
    assert rcc._window_result("inside others") is None


def test_unreadable_block_is_unknown_not_guessed():
    log = "====================output========================\nnot a dict\n==========================output end ===============\n"
    assert rcc._window_result(log)["result"] == "unknown"


@pytest.mark.parametrize("message, hint_part", [
    ("Missing credentials. Please pass an `api_key`", "OPENROUTE_API_KEY"),
    ("time data 'x' does not match format '%d-%m-%Y'", "DD-MM-YYYY"),
    ("strptime() argument 1 must be str, not None", "not found"),
])
def test_error_hints(message, hint_part):
    assert hint_part in rcc._hint(Exception(message), "")


def test_unknown_error_has_no_hint():
    assert rcc._hint(ValueError("something else"), "") is None
