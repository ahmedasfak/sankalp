import re
from typing import Literal
from datetime import datetime
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from datetime import date, timedelta

from llm import llm
from state import Message

def triage(state: Message):
    analysis = str(state["analysis"]).upper()
    print(f"analysis value is {analysis}")
    if analysis == "NEAR EXPIRY":
        return "near_expiry"
    if analysis in {"EXPIRY", "EXPIRED"}:
        return "expiry"
    if analysis == "SHORT_SUPPLY":
        return "short_supply"
    if analysis == "BREAKAGE_IN_TRANSIT":
        return "breakage_in_transit"
    return "other"
#################################################################################
#Claims_precheck
#################################################################################

def claim_precheck_validation(state : Message) :
    if state["batch_no"] != None and state['invoice_no'] != None and state["Expiry"] != None and state["Qty"]  != None :
        return ["NEAR EXPIRY","EXPIRY","SHORT SUPPLY","BREAKAGE IN TRANSIT"]
    return "invalid_node"

#########################################################################


# Claim windows (calendar days)
CLAIM_WINDOWS = {
    "NEAR EXPIRY":         {"anchor": "expiry",  "days_before": 90, "days_after": 0},   # 90 days before expiry up to the expiry date
    "EXPIRY":             {"anchor": "expiry",  "days_before": 0,  "days_after": 90},  # expiry date up to 90 days after expiry
    "EXPIRED":             {"anchor": "expiry",  "days_before": 0,  "days_after": 90},  # expiry date up to 90 days after expiry
    "BREAKAGE_IN_TRANSIT": {"anchor": "invoice", "max_days_after_invoice": 7},         # damage found on receipt
    "SHORT_SUPPLY":        {"anchor": "invoice", "max_days_after_invoice": 7},         # fewer packs received than invoiced
}


def check_claim_window(claim_type: str, claim_date: date, expiry_date: date | None = None, invoice_date: date | None = None) -> dict:
    """Return {'result': 'pass' | 'fail' | 'unknown', 'detail': str} for one claim."""
    expiry_date = datetime.strptime(expiry_date, '%Y-%m-%d').date()
    claim_date = datetime.strptime(claim_date, '%d-%m-%Y').date()
    invoice_date = datetime.strptime(invoice_date, '%d-%m-%Y').date()
    print(expiry_date,claim_date,invoice_date)
    rule = CLAIM_WINDOWS.get(claim_type)
    print(rule)
    if rule is None:
        return {"result": "unknown", "detail": f"unknown claim type {claim_type!r}"}

    if rule["anchor"] == "expiry":
        if expiry_date is None:
            return {"result": "unknown", "detail": "expiry date missing"}
        start = expiry_date - timedelta(days=rule["days_before"])
        end = expiry_date + timedelta(days=rule["days_after"])
        ok = start <= claim_date <= end
        return {"result": "pass" if ok else "fail",
                "detail": f"{claim_type}: window {start} to {end}; claim dated {claim_date}"}

    if invoice_date is None:
        return {"result": "unknown", "detail": "invoice date missing"}
    days = (claim_date - invoice_date).days
    ok = 0 <= days <= rule["max_days_after_invoice"]
    return {"result": "pass" if ok else "fail",
            "detail": f"{claim_type}: {days} days after invoice; limit {rule['max_days_after_invoice']} days"}