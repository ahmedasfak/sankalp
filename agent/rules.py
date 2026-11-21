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
    label = analysis.replace("_", " ").strip()      # model returns NEAR_EXPIRY; older code used NEAR EXPIRY
    if label == "NEAR EXPIRY":
        return "near_expiry"
    if label in {"EXPIRY", "EXPIRED"}:
        return "expiry"
    if label == "SHORT SUPPLY":
        return "short_supply"
    if label == "BREAKAGE IN TRANSIT":
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


# Date formats found in the extracts: batch_master and primary_sales mix
# DD-MM-YYYY, YYYY-MM-DD and DD-Mon-YYYY (e.g. 30-09-2025, 2025-09-30, 01-Apr-2024).
DATE_FORMATS = ("%d-%m-%Y", "%Y-%m-%d", "%d-%b-%Y", "%d/%m/%Y")


def to_date(value) -> date | None:
    """Parse a date in any format used by the extracts; None if missing or unreadable."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text or text.lower() in {"nan", "nat", "none"}:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def check_claim_window(claim_type: str, claim_date: date, expiry_date: date | None = None, invoice_date: date | None = None) -> dict:
    """Return {'result': 'pass' | 'fail' | 'unknown', 'detail': str} for one claim."""
    expiry_date = to_date(expiry_date)
    claim_date = to_date(claim_date)
    invoice_date = to_date(invoice_date)
    print(expiry_date,claim_date,invoice_date)
    windows = {k.replace("_", " "): v for k, v in CLAIM_WINDOWS.items()}
    rule = windows.get(str(claim_type).upper().replace("_", " ").strip())
    print(rule)
    if rule is None:
        return {"result": "unknown", "detail": f"unknown claim type {claim_type!r}"}
    if claim_date is None:
        return {"result": "unknown", "detail": "claim (received) date missing or unreadable"}

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