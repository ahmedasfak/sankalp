"""Validate one claim from the claims register (expiry_claims.csv) with a LangGraph graph.

Same shape as graph_validate.py, but the input is a claim number instead of an
email, so no model is needed: every field comes from the extracts.

    START -> load_claim --triage--> near_expiry | expiry | short_supply | breakage_in_transit | other
          -> decide -> END

* load_claim   looks the claim up in expiry_claims.csv; "not found" goes to a person
* triage       routes on claim_type (same routing as rules.triage)
* claim nodes  run the rules that apply to that claim type, with thresholds read
               from config.py (CO-POL-014 §5.1-5.7)
* decide       any fail -> REJECT; else any unknown -> NEEDS_PERSON; else APPROVE

Run from agent/:

    python claim_validate.py --claim-no CLM-2605-04488
    python claim_validate.py --claim-no CLM-2605-04488 --draw     # also saves claim_graph.png

The last printed line is JSON for app.py, prefixed with RESULT_MARKER.
"""
from __future__ import annotations

import argparse
import json
import operator
from functools import lru_cache
from typing import Annotated, TypedDict

import pandas as pd
from langgraph.graph import END, START, StateGraph

from config import format_citation, get_clause

RESULT_MARKER = "@@CLAIM_VALIDATE@@"
PASS, FAIL, UNKNOWN, INFO = "pass", "fail", "unknown", "info"
EXTRACT_END = pd.Timestamp("2026-09-30")       # last day covered by the extracts
VALUE_TOLERANCE_INR = 1.0                      # rounding tolerance for qty x PTS

# ----------------------------------------------------------------------------- rules from config.py
_WINDOWS = get_clause("CO-POL-014", "5.2")["claim_windows"]
NE_DAYS_BEFORE = _WINDOWS["near_expiry"]["days_before_expiry"]          # 90
EXP_DAYS_AFTER = _WINDOWS["expired"]["days_after_expiry"]               # 90
BREAKAGE_DAYS = _WINDOWS["breakage_in_transit"]["window_days_from_invoice"]   # 7
SHORT_SUPPLY_DAYS = _WINDOWS["short_supply"]["window_days_from_invoice"]      # 7
CN_DAYS = get_clause("CO-POL-014", "5.6")["values"]["credit_note_days_from_claim_receipt"]   # 30
AM_APPROVER = get_clause("CO-POL-014", "5.4")["values"]["written_approval_required_from"]     # Area Manager
VALUATION_NOTE = get_clause("CO-POL-014", "5.7").get("critical_note", "")

CITE = {k: format_citation("CO-POL-014", k) for k in ("5.1", "5.2", "5.3", "5.4", "5.5", "5.6", "5.7")}

# claim_type in the register -> graph node
ROUTES = {"NEAR EXPIRY": "near_expiry", "EXPIRED": "expiry", "EXPIRY": "expiry",
          "SHORT SUPPLY": "short_supply", "BREAKAGE IN TRANSIT": "breakage_in_transit"}


# ----------------------------------------------------------------------------- data
@lru_cache(maxsize=1)
def lookup() -> dict:
    """Indexes over the extracts loaded by data.py.

    data.py keeps repeated rows (its drop_duplicates() result is not saved), so
    they are dropped here. Indexes still equal the CSV position: csv row = index + 2.
    """
    from data import sales, claims, sku_df, batch_df, norm_inv

    key = ["invoice_no", "date", "cnf_code", "stockist_code", "sku_code", "batch_no",
           "ordered_qty", "invoiced_qty", "free_qty", "net_value_inr", "scheme_code"]
    s = sales.drop_duplicates(subset=key).copy()
    s["csv_row"] = s.index + 2
    s["inv"] = s.invoice_no.map(norm_inv)
    c = claims.drop_duplicates(subset=[x for x in claims.columns if x not in ("date", "exp", "cn_date")]).copy()
    c["csv_row"] = c.index + 2
    c["claim_key"] = c.claim_no.astype(str).str.strip().str.upper()

    sb = s[s.batch_no.notna()].groupby(["stockist_code", "batch_no"])
    sold = pd.DataFrame({"packs": sb.invoiced_qty.sum() + sb.free_qty.sum(),
                         "cnfs": sb.cnf_code.agg(lambda x: sorted(set(x))),
                         "rows": sb.csv_row.agg(list)})
    inv = s.groupby("inv")
    invoices = pd.DataFrame({"invoice_date": inv.date.first(), "stockist_code": inv.stockist_code.first(),
                             "batches": inv.batch_no.agg(lambda x: sorted(set(x.dropna()))),
                             "csv_row": inv.csv_row.first()})
    return {"claims": c, "sold": sold, "invoices": invoices, "norm_inv": norm_inv,
            "batch": batch_df.drop_duplicates("batch_no").set_index("batch_no"),
            "pts": sku_df.drop_duplicates("sku_code").set_index("sku_code").pts,
            "groups": c.groupby(["stockist_code", "batch_no"]).groups}


def _d(v):
    return None if v is None or pd.isna(v) else pd.Timestamp(v)


def _s(v):
    return None if v is None or (not isinstance(v, str) and pd.isna(v)) else str(v)


def _f(v):
    return None if v is None or pd.isna(v) else float(v)


def _check(rule, result, detail, clause, evidence=None) -> dict:
    return {"rule": rule, "result": result, "detail": detail, "clause": clause, "evidence": evidence or []}


def _row(state) -> pd.Series:
    return lookup()["claims"].loc[state["row_index"]]


def _earlier(c: pd.Series) -> pd.DataFrame:
    """Claims on the same stockist + batch logged before this one, not rejected."""
    L = lookup()
    idx = L["groups"].get((c.stockist_code, c.batch_no))
    if idx is None:
        return L["claims"].iloc[0:0]
    e = L["claims"].loc[idx]
    e = e[(e.claim_key != c.claim_key) & (e.status != "Rejected")]
    return e[(e.date < c.date) | ((e.date == c.date) & (e.claim_key < c.claim_key))].sort_values(["date", "claim_key"])


# ----------------------------------------------------------------------------- rules (one function each)
def rule_batch(c) -> dict:
    """§5.3(1): the batch on the claim exists and belongs to the claimed SKU."""
    L = lookup()
    if c.batch_no not in L["batch"].index:
        return _check("batch_exists", UNKNOWN, f"batch {c.batch_no} is not in batch_master.csv (batches before Oct 2023 "
                                               f"were archived at the ERP migration)", CITE["5.3"])
    b = L["batch"].loc[c.batch_no]
    if b.sku_code != c.sku_code:
        return _check("batch_exists", FAIL, f"batch {c.batch_no} belongs to {b.sku_code}, not {c.sku_code}", CITE["5.3"])
    return _check("batch_exists", PASS, f"batch {c.batch_no} is {b.sku_code}, expiry {b.exp.date()}", CITE["5.3"],
                  ["batch_master.csv"])


def rule_expiry_matches(c) -> dict:
    """§5.3(1): expiry date on the claim matches the batch master."""
    L = lookup()
    if c.batch_no not in L["batch"].index:
        return _check("expiry_matches", UNKNOWN, "no batch record to compare the expiry with", CITE["5.3"])
    exp = L["batch"].loc[c.batch_no].exp
    if pd.isna(c.exp):
        return _check("expiry_matches", UNKNOWN, "claim has no expiry date", CITE["5.3"])
    ok = c.exp.normalize() == exp.normalize()
    return _check("expiry_matches", PASS if ok else FAIL,
                  f"claimed expiry {c.exp.date()} vs batch master {exp.date()}", CITE["5.3"])


def rule_window_expiry(c, kind: str) -> dict:
    """§5.2: near expiry = [expiry - 90, expiry]; expired = [expiry, expiry + 90]."""
    L = lookup()
    exp = L["batch"].loc[c.batch_no].exp if c.batch_no in L["batch"].index else c.exp
    if exp is None or pd.isna(exp):
        return _check("window", UNKNOWN, "no expiry date in batch_master or on the claim", CITE["5.2"])
    d = c.date
    lo = exp - pd.Timedelta(days=NE_DAYS_BEFORE if kind == "near_expiry" else 0)
    hi = exp + pd.Timedelta(days=0 if kind == "near_expiry" else EXP_DAYS_AFTER)
    label = "near expiry" if kind == "near_expiry" else "expired"
    if lo <= d <= hi:
        return _check("window", PASS, f"{label} claim dated {d.date()} is inside {lo.date()} to {hi.date()}", CITE["5.2"])
    if exp - pd.Timedelta(days=NE_DAYS_BEFORE) <= d <= exp + pd.Timedelta(days=EXP_DAYS_AFTER):
        return _check("window", UNKNOWN, f"claim dated {d.date()} is outside the {label} window ({lo.date()} to {hi.date()}) "
                                         f"but inside the other expiry window: the claim type may be wrong", CITE["5.2"])
    return _check("window", FAIL, f"claim dated {d.date()} is {abs((d - exp).days)} days {'before' if d < exp else 'after'} "
                                  f"expiry {exp.date()}: outside every window", CITE["5.2"])


def rule_window_invoice(c, kind: str) -> dict:
    """§5.2: breakage / short supply within 7 days of the invoice."""
    L = lookup()
    limit = BREAKAGE_DAYS if kind == "breakage_in_transit" else SHORT_SUPPLY_DAYS
    ref = L["norm_inv"](c.inv)
    if ref is None or ref not in L["invoices"].index:
        return _check("window", UNKNOWN, "no invoice in primary_sales.csv to date the claim", CITE["5.2"])
    inv = L["invoices"].loc[ref]
    days = (c.date - inv.invoice_date).days
    return _check("window", PASS if 0 <= days <= limit else FAIL,
                  f"claimed {days} days after invoice {ref} dated {inv.invoice_date.date()} (limit {limit})",
                  CITE["5.2"], [f"primary_sales.csv row {inv.csv_row}"])


def rule_invoice_ref(c) -> dict:
    """§5.3(2) / §5.4: the original invoice is quoted, exists, was billed to this stockist and carried this batch."""
    L = lookup()
    ref = L["norm_inv"](c.inv)
    if ref is None:
        return _check("invoice_ref", UNKNOWN, f"no invoice reference: §5.4 allows ledger verification only with written "
                                              f"{AM_APPROVER} approval; confirm what was checked", CITE["5.4"])
    if ref not in L["invoices"].index:
        return _check("invoice_ref", UNKNOWN, f"invoice {ref} is not in primary_sales.csv (extract starts Apr 2024)", CITE["5.3"])
    inv = L["invoices"].loc[ref]
    ev = [f"primary_sales.csv row {inv.csv_row}"]
    if inv.stockist_code != c.stockist_code:
        return _check("invoice_ref", FAIL, f"invoice {ref} was billed to {inv.stockist_code}, not {c.stockist_code}", CITE["5.3"], ev)
    if c.batch_no not in inv.batches:
        return _check("invoice_ref", FAIL, f"batch {c.batch_no} was not supplied on invoice {ref}", CITE["5.3"], ev)
    return _check("invoice_ref", PASS, f"invoice {ref} dated {inv.invoice_date.date()} supplied this batch to this stockist",
                  CITE["5.3"], ev)


def rule_quantity(c) -> dict:
    """§5.5: packs claimed (this + earlier non-rejected claims) <= packs invoiced to this stockist, free included."""
    L = lookup()
    key = (c.stockist_code, c.batch_no)
    if pd.isna(c.qty):
        return _check("quantity", UNKNOWN, "claimed quantity missing", CITE["5.5"])
    if key not in L["sold"].index:
        return _check("quantity", UNKNOWN, f"no sale of batch {c.batch_no} to {c.stockist_code} in primary_sales.csv", CITE["5.5"])
    sold, earlier = L["sold"].loc[key], _earlier(c)
    prior = float(earlier.qty.sum())
    total = prior + float(c.qty)
    ev = [f"primary_sales.csv rows {sold.rows[:6]}{' ...' if len(sold.rows) > 6 else ''}"]
    if len(earlier):
        ev.append(f"expiry_claims.csv rows {earlier.csv_row.tolist()}")
    detail = f"claimed {c.qty:.0f} + earlier claims {prior:.0f} = {total:.0f}; invoiced incl. free {sold.packs:.0f}"
    if total <= sold.packs:
        return _check("quantity", PASS, detail, CITE["5.5"], ev)
    return _check("quantity", FAIL, detail + f"; over by {total - sold.packs:.0f}", CITE["5.5"], ev)


def rule_duplicate(c) -> dict:
    """§5.6 step 3: an earlier claim with the same stockist, batch and quantity is the same goods claimed twice."""
    earlier = _earlier(c)
    same = earlier[earlier.qty == c.qty]
    if len(same):
        r = same.iloc[0]
        cn = r.credit_note_no if isinstance(r.credit_note_no, str) else "no CN"
        return _check("duplicate", FAIL, f"same stockist, batch and quantity already claimed as {r.claim_no} on "
                                         f"{r.date.date()} ({r.status}, {cn})", CITE["5.6"], [f"expiry_claims.csv row {r.csv_row}"])
    if len(earlier):
        return _check("duplicate", PASS, f"{len(earlier)} earlier claim(s) on this batch with a different quantity "
                                         f"({earlier.claim_no.tolist()}); the total is checked by the quantity rule", CITE["5.6"])
    return _check("duplicate", PASS, "no earlier claim on this stockist + batch", CITE["5.6"])


def rule_value(c) -> dict:
    """§5.7: claim value = quantity x PTS (sku_master.csv, per the Company overview §5.1)."""
    pts = lookup()["pts"].get(c.sku_code)
    if pts is None or pd.isna(pts):
        return _check("value", UNKNOWN, f"SKU {c.sku_code} not in sku_master.csv", CITE["5.7"])
    if pd.isna(c.qty):
        return _check("value", UNKNOWN, "claimed quantity missing", CITE["5.7"])
    expected = round(float(c.qty) * float(pts), 2)
    ev = [f"sku_master.csv {c.sku_code} pts_inr = {pts}"]
    if pd.isna(c.val):
        return _check("value", UNKNOWN, f"claim value is blank; expected {c.qty:.0f} x {pts} = INR {expected:,.2f}", CITE["5.7"], ev)
    ok = abs(float(c.val) - expected) <= VALUE_TOLERANCE_INR
    return _check("value", PASS if ok else FAIL, f"claimed INR {c.val:,.2f} vs {c.qty:.0f} x PTS {pts} = INR {expected:,.2f}",
                  CITE["5.7"], ev)


def rule_billing_cfa(c) -> dict:
    """§5.1: returns are received only at the C&F that billed the stock."""
    L = lookup()
    key = (c.stockist_code, c.batch_no)
    if key not in L["sold"].index:
        return _check("billing_cfa", UNKNOWN, "no sale found to confirm the billing C&F", CITE["5.1"])
    cnfs = L["sold"].loc[key].cnfs
    return _check("billing_cfa", PASS if c.cnf_code in cnfs else FAIL,
                  f"claim received at {c.cnf_code}; batch billed to this stockist from {cnfs}", CITE["5.1"])


def info_settlement(c) -> dict:
    """§5.6: credit note within 30 days of the claim. Information only: it does not change the verdict."""
    if c.status == "Credited" and not pd.isna(c.cn_date):
        days = (c.cn_date - c.date).days
        late = "late" if days > CN_DAYS else "on time"
        return _check("settlement", INFO, f"register: Credited, {c.credit_note_no} for INR {c.cval:,.2f} after {days} days "
                                          f"({late}; policy {CN_DAYS})", CITE["5.6"])
    if c.status == "Pending":
        days = (EXTRACT_END - c.date).days
        return _check("settlement", INFO, f"register: Pending for {days} days at {EXTRACT_END.date()} (policy {CN_DAYS})", CITE["5.6"])
    return _check("settlement", INFO, f"register: {c.status}" + (f" ({c.remarks})" if isinstance(c.remarks, str) else ""), CITE["5.6"])


# The rules each claim type gets
RULES_BY_ROUTE = {
    "near_expiry": [rule_batch, rule_expiry_matches, lambda c: rule_window_expiry(c, "near_expiry"), rule_invoice_ref,
                    rule_quantity, rule_duplicate, rule_value, rule_billing_cfa],
    "expiry": [rule_batch, rule_expiry_matches, lambda c: rule_window_expiry(c, "expiry"), rule_invoice_ref,
               rule_quantity, rule_duplicate, rule_value, rule_billing_cfa],
    "short_supply": [rule_batch, lambda c: rule_window_invoice(c, "short_supply"), rule_invoice_ref,
                     rule_quantity, rule_duplicate, rule_value, rule_billing_cfa],
    "breakage_in_transit": [rule_batch, lambda c: rule_window_invoice(c, "breakage_in_transit"), rule_invoice_ref,
                            rule_quantity, rule_duplicate, rule_value, rule_billing_cfa],
}


# ----------------------------------------------------------------------------- graph
class ClaimState(TypedDict, total=False):
    claim_no: str
    found: bool
    row_index: int
    claim: dict                                    # register fields, as plain values
    route: str
    checks: Annotated[list, operator.add]
    verdict: str
    summary: str


def load_claim(state: ClaimState) -> dict:
    claim_no = (state.get("claim_no") or "").strip().upper()
    reg = lookup()["claims"]
    hit = reg[reg.claim_key == claim_no]
    if hit.empty:
        return {"claim_no": claim_no, "found": False,
                "checks": [_check("found", UNKNOWN, f"claim {claim_no or '(blank)'} is not in expiry_claims.csv; "
                                                    f"expected format CLM-YYMM-NNNNN", "-")]}
    c = hit.iloc[0]
    claim = {
        "claim_no": c.claim_no, "claim_date": str(c.date.date()), "claim_type": c.claim_type,
        "stockist_code": c.stockist_code, "cnf_code": c.cnf_code, "sku_code": c.sku_code, "batch_no": c.batch_no,
        "expiry_date_as_claimed": None if pd.isna(c.exp) else str(c.exp.date()), "qty_claimed": _f(c.qty),
        "claim_value_inr": _f(c.val), "original_invoice_ref": _s(c.original_invoice_ref), "status": c.status,
        "verified_by": _s(c.verified_by), "credit_note_no": _s(c.credit_note_no), "credit_value_inr": _f(c.cval),
        "remarks": _s(c.remarks), "csv_row": int(c.csv_row),
    }
    return {"claim_no": claim_no, "found": True, "row_index": int(hit.index[0]), "claim": claim}


def triage_claim(state: ClaimState) -> str:
    """Same routing as rules.triage: the claim type decides the node."""
    if not state.get("found"):
        return "other"
    return ROUTES.get(str(state["claim"]["claim_type"]).upper().replace("_", " ").strip(), "other")


def _make_claim_node(route: str):
    def node(state: ClaimState) -> dict:
        c = _row(state)
        checks = [rule(c) for rule in RULES_BY_ROUTE[route]] + [info_settlement(c)]
        return {"route": route, "checks": checks}
    node.__name__ = route
    return node


near_expiry = _make_claim_node("near_expiry")
expiry = _make_claim_node("expiry")
short_supply = _make_claim_node("short_supply")
breakage_in_transit = _make_claim_node("breakage_in_transit")


def other(state: ClaimState) -> dict:
    if not state.get("found"):
        return {"route": "other"}
    return {"route": "other", "checks": [_check("claim_type", UNKNOWN, f"claim type {state['claim']['claim_type']!r} has "
                                                                        f"no rule set", CITE["5.2"])]}


def decide(state: ClaimState) -> dict:
    results = {k["result"] for k in state.get("checks", [])}
    verdict = "REJECT" if FAIL in results else "NEEDS_PERSON" if UNKNOWN in results else "APPROVE"
    reasons = [f"{k['rule']}: {k['detail']}" for k in state.get("checks", []) if k["result"] in (FAIL, UNKNOWN)]
    summary = f"{verdict}" + (" - " + " | ".join(reasons) if reasons else " - every rule passed")
    if state.get("found"):
        status = state["claim"]["status"]
        if status == "Credited" and verdict == "REJECT":
            summary += f" | already credited INR {state['claim']['credit_value_inr'] or 0:,.2f}: candidate for recovery"
    return {"verdict": verdict, "summary": summary}


graph = StateGraph(ClaimState)
graph.add_node("load_claim", load_claim)
graph.add_node("near_expiry", near_expiry)
graph.add_node("expiry", expiry)
graph.add_node("short_supply", short_supply)
graph.add_node("breakage_in_transit", breakage_in_transit)
graph.add_node("other", other)
graph.add_node("decide", decide)
graph.add_edge(START, "load_claim")
graph.add_conditional_edges("load_claim", triage_claim,
                            ["near_expiry", "expiry", "short_supply", "breakage_in_transit", "other"])
for _node in ["near_expiry", "expiry", "short_supply", "breakage_in_transit", "other"]:
    graph.add_edge(_node, "decide")        # one edge each: a list here would make decide wait for all five
graph.add_edge("decide", END)
app = graph.compile()


def validate(claim_no: str) -> dict:
    out = app.invoke({"claim_no": claim_no, "checks": []})
    return {k: out.get(k) for k in ("claim_no", "found", "claim", "route", "checks", "verdict", "summary")}


def print_result(r: dict):
    print("=" * 78)
    print(f"CLAIM {r['claim_no']}  ->  {r['verdict']}")
    print("=" * 78)
    if r.get("claim"):
        c = r["claim"]
        print(f"{c['claim_type']} | {c['stockist_code']} | {c['cnf_code']} | {c['sku_code']} | batch {c['batch_no']} | "
              f"qty {c['qty_claimed']:.0f} | INR {c['claim_value_inr'] or 0:,.2f} | claimed {c['claim_date']} | "
              f"expiry_claims.csv row {c['csv_row']}")
    print(f"path: load_claim -> {r.get('route')} -> decide")
    for k in r.get("checks") or []:
        ev = ("  | " + "; ".join(k["evidence"])) if k["evidence"] else ""
        print(f"  [{k['result']:7s}] {k['rule']:15s} {k['detail']}  <{k['clause']}>{ev}")
    print(f"\n{r['summary']}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Validate one claim from expiry_claims.csv.")
    p.add_argument("--claim-no", required=True, help="claim number, e.g. CLM-2605-04488")
    p.add_argument("--draw", action="store_true", help="also save the graph as claim_graph.png (needs internet)")
    a = p.parse_args(argv)
    if a.draw:
        try:
            with open("claim_graph.png", "wb") as f:
                f.write(app.get_graph().draw_mermaid_png())
        except Exception as e:                       # drawing uses mermaid.ink; never block validation on it
            print(f"(could not draw the graph: {e})")
    r = validate(a.claim_no)
    print_result(r)
    print(RESULT_MARKER + json.dumps(r, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
