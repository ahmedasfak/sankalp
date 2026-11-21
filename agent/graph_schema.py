"""Scheme pipeline: a LangGraph graph that rebuilds the expiry-returns evidence.

    validate_data -> (in parallel)
        quarterly_claims_foc   Expiry claims and free goods as % of primary, by FY quarter
        scheme_link            Were the expired batches bought on a quarter-end scheme?
        tier_rates             Expiry rate by scheme tier (same forecast, different outcomes)
        fefo_dispatch          Short-dated dispatches and FEFO, by C&F
        settlement             Claim-to-credit-note time and the backlog
        scheme_compliance      Each circular against CO-POL-014 §4 and Annexure B
    -> build_report

Every node is plain pandas; no model is called. Each section carries the
files and clauses its numbers come from. Run from agent/:

    python scheme_pipeline.py                      # full report
    python scheme_pipeline.py --since 2025-10-01   # change the "last 12 months" start

The state holds only plain dicts and lists (see state.py); data frames stay in
module memory, loaded once from data.py.
"""
from __future__ import annotations

import argparse
import operator
import re
from functools import lru_cache
from typing import Annotated, TypedDict
from state import SchemeState

import numpy as np
import pandas as pd
from langgraph.graph import END, START, StateGraph

from config import SCHEME_CIRCULARS, format_citation, get_clause

NE_TYPES = ["Near expiry", "Expired"]
DEFAULT_SINCE = "2025-10-01"        # last 12 months of the extract (ends 30-Sep-2026)
DEFAULT_FEFO_FROM = "2026-04-01"    # snapshots are monthly from Apr 2026
CRORE, LAKH = 1e7, 1e5

# Policy numbers read from config.py, never typed twice.
CAP_PCT = get_clause("CO-POL-014", "4.4")["values"]["maximum_quarterly_free_goods_value_percent_of_portfolio_primary_sales"]
STOCK_NORM_MONTHS = get_clause("CO-POL-014", "4.5")["values"]["maximum_closing_stock_months_of_average_secondary"]
MIN_RSL_PCT = get_clause("CO-POL-014", "7.1")["values"]["minimum_rsl_percent_of_total_shelf_life_at_invoice"]
CN_DAYS = get_clause("CO-POL-014", "5.6")["values"]["credit_note_days_from_claim_receipt"]
ANNEX_B = get_clause("CO-POL-014", "Annexure B")["values"]
VALID_FROM_DAY = ANNEX_B["circular_validity_start_day"]
MOQ_MULTIPLE = ANNEX_B["minimum_order_multiple_of_prior_3_month_average_monthly_sku_purchase"]


# --------------------------------------------------------------------------- scheme register
def scheme_register() -> pd.DataFrame:
    """CO-POL-014 Annexure B as a table: one row per scheme code.

    Resolves "As QS-FY25Q3-A" chains to SKU lists and "10 + 2 free" to a free
    ratio. Validity runs from the 22nd to the last day of the quarter's last month.
    """
    by_code = {c["scheme_codes"][0]: c for c in SCHEME_CIRCULARS}

    def skus(code, seen=()):
        scope = by_code[code]["sku_scope"]
        m = re.match(r"As (\S+)", scope)
        if m and m.group(1) not in seen:
            return skus(m.group(1), seen + (code,))
        return [s.strip() for s in scope.split(",")]

    rows = []
    for code, c in by_code.items():
        base, free = map(int, re.findall(r"\d+", c["terms"])[:2])
        fy, q = re.match(r"QS-FY(\d{2})Q(\d)", code).groups()
        last_month = pd.Period(f"20{int(fy) - 1}-03", "M") + 3 * int(q)    # Q1 ends Jun, Q4 ends Mar
        rows.append({
            "scheme_code": code, "circular": c["circular"], "tier": code[-1], "terms": c["terms"],
            "free_per_pack": free / base, "skus": skus(code),
            "valid_from": last_month.to_timestamp() + pd.Timedelta(days=VALID_FROM_DAY - 1),
            "valid_to": last_month.to_timestamp(how="end").normalize(),
            "fq": f"FY{fy}Q{q}", "page": c["page"],
        })
    return pd.DataFrame(rows).set_index("scheme_code")


def tier_of(sku_codes: pd.Series) -> pd.Series:
    """Tier A / Tier B / No scheme, from the SKU scope of the latest circulars."""
    reg = scheme_register()
    a = set().union(*reg[reg.tier == "A"].skus)
    b = set().union(*reg[reg.tier == "B"].skus)
    return pd.Series(np.where(sku_codes.isin(a), "Tier A", np.where(sku_codes.isin(b), "Tier B", "No scheme")),
                     index=sku_codes.index)


# --------------------------------------------------------------------------- data
def fy_quarter(d: pd.Series) -> pd.Series:
    fy = d.dt.year + (d.dt.month >= 4).astype(int)
    q = ((d.dt.month - 4) % 12) // 3 + 1
    return "FY" + (fy % 100).astype(str).str.zfill(2) + "Q" + q.astype(str)


@lru_cache(maxsize=1)
def frames() -> dict:
    """Cleaned frames from data.py, with its two gaps closed: duplicate rows are
    dropped here (data.py does not keep its drop_duplicates() result) and the
    C&F code in the stock snapshot uses the normalised `cnf` column."""
    from data import sales, claims, sku_df, batch_df, stock

    key_cols = ["invoice_no", "date", "cnf_code", "stockist_code", "sku_code", "batch_no",
                "ordered_qty", "invoiced_qty", "free_qty", "net_value_inr", "scheme_code"]
    s = sales.drop_duplicates(subset=key_cols).copy()
    s["scheme_code"] = s.scheme_code.where(~s.scheme_code.isin(["-", "NA", ""]))
    s["fq"] = fy_quarter(s.date)
    s["foc_value"] = s.free_qty * s.pts_inr
    c = claims.drop_duplicates(subset=[x for x in claims.columns if x not in ("date", "exp", "cn_date")]).copy()
    c["fq"] = fy_quarter(c.date)
    st = stock.copy()
    st["cnf_code"] = st.cnf
    return {"sales": s, "claims": c, "sku": sku_df, "batch": batch_df, "stock": st,
            "raw_sales_rows": len(sales), "raw_claim_rows": len(claims)}


# --------------------------------------------------------------------------- analyses (pure functions)
def quarterly_claims_foc(s: pd.DataFrame, c: pd.DataFrame) -> pd.DataFrame:
    q = s.groupby("fq").agg(primary_cr=("net_value_inr", "sum"), foc_cr=("foc_value", "sum"))
    q["foc_pct"] = q.foc_cr / q.primary_cr * 100
    q["foc_above_cap_cr"] = (q.foc_cr - CAP_PCT / 100 * q.primary_cr).clip(lower=0)
    q["ne_claims_cr"] = c[c.claim_type.isin(NE_TYPES)].groupby("fq").val.sum()
    q["ne_claims_pct"] = q.ne_claims_cr / q.primary_cr * 100
    q["all_claims_cr"] = c.groupby("fq").val.sum()
    for col in ["primary_cr", "foc_cr", "foc_above_cap_cr", "ne_claims_cr", "all_claims_cr"]:
        q[col] = q[col] / CRORE
    return q.fillna(0)


def scheme_link(s: pd.DataFrame, c: pd.DataFrame, since: str) -> pd.DataFrame:
    """Join each NE/expired claim to primary_sales on stockist + batch."""
    pair = (s[s.batch_no.notna()].groupby(["stockist_code", "batch_no"])
            .agg(on_scheme=("scheme_code", lambda x: x.notna().any())))
    ne = c[c.claim_type.isin(NE_TYPES)].merge(pair, left_on=["stockist_code", "batch_no"], right_index=True, how="left")
    ne["link"] = np.select([ne.on_scheme.isna(), ne.on_scheme.astype("boolean").fillna(False).astype(bool)],
                           ["Batch not sold to this stockist in extract", "Bought on a quarter-end scheme"],
                           "Bought, no scheme")
    out = []
    for period, frame in [("All periods", ne), (f"Since {since}", ne[ne.date >= since])]:
        t = frame.groupby("link").val.agg(claims="count", value_lakh="sum")
        t["share_pct"] = t.value_lakh / t.value_lakh.sum() * 100
        t["value_lakh"] = t.value_lakh / LAKH
        out.append(t.assign(period=period).reset_index())
    return pd.concat(out).set_index(["period", "link"])


def tier_rates(s: pd.DataFrame, c: pd.DataFrame, sku: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    ne = c[c.claim_type.isin(NE_TYPES)]
    t = pd.DataFrame({"primary_cr": s.groupby(tier_of(s.sku_code)).net_value_inr.sum() / CRORE,
                      "ne_claims_cr": ne.groupby(tier_of(ne.sku_code)).val.sum() / CRORE})
    t.index.name = "tier"
    t["claims_pct_of_sales"] = t.ne_claims_cr / t.primary_cr * 100
    t["share_of_claims_pct"] = t.ne_claims_cr / t.ne_claims_cr.sum() * 100
    ta = (ne.merge(sku[["sku_code", "therapy_area"]], on="sku_code").groupby("therapy_area").val.sum()
          .sort_values(ascending=False).div(LAKH).to_frame("ne_claims_lakh"))
    return t, ta


def fefo_dispatch(s: pd.DataFrame, batch: pd.DataFrame, stock: pd.DataFrame, since: str) -> pd.DataFrame:
    """RSL rule (§7.1) and a FEFO proxy per C&F.

    FEFO proxy: an invoice line is non-FEFO when the C&F held, at the previous
    month-end, a batch of the same SKU with an earlier expiry and >= 60 days of
    life left. Snapshots are monthly only from Apr 2026, so this is an
    indicator, not a pick log (the CFA WMS is not visible to Pfizer).
    """
    lines = s[s.batch_no.notna()].merge(batch[["batch_no", "mfg", "exp"]], on="batch_no")
    lines["rsl_pct"] = (lines.exp - lines.date).dt.days / (lines.exp - lines.mfg).dt.days * 100
    lines["below_min_rsl"] = lines.rsl_pct < MIN_RSL_PCT
    avail = stock[stock.qty > 0]
    flagged = []
    for sd in sorted(avail.date.dropna().unique()):
        sd = pd.Timestamp(sd)
        nxt = sd + pd.offsets.MonthEnd(1)
        a = avail[(avail.date == sd) & ((avail.exp - nxt).dt.days >= 60)]
        oldest = a.groupby(["cnf_code", "sku_code"]).exp.min().rename("oldest_available")
        l = lines[(lines.date > sd) & (lines.date <= nxt)].merge(oldest, left_on=["cnf_code", "sku_code"], right_index=True)
        if len(l):
            flagged.append(l.assign(non_fefo=l.exp > l.oldest_available))
    fefo = pd.concat(flagged)
    w, wf = lines[lines.date >= since], fefo[fefo.date >= since]
    return pd.DataFrame({
        "lines": w.groupby("cnf_code").size(),
        "below_min_rsl_pct": w.groupby("cnf_code").below_min_rsl.mean() * 100,
        "non_fefo_pct_proxy": wf.groupby("cnf_code").non_fefo.mean() * 100,
    })


def settlement(c: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    tat = (c.cn_date - c.date).dt.days
    pending = c[c.status == "Pending"]
    h1 = c[(c.date >= "2026-04-01") & c.claim_type.isin(NE_TYPES)]
    summary = {
        "avg_days_claim_to_cn": round(float(tat.mean()), 1),
        "median_days_claim_to_cn": float(tat.median()),
        "pct_cn_later_than_policy": round(float((tat > CN_DAYS).mean() * 100), 1),
        "policy_days": CN_DAYS,
        "pending_claims": int(len(pending)),
        "pending_value_lakh": round(float(pending.val.sum() / LAKH), 1),
        "oldest_pending": str(pending.date.min().date()) if len(pending) else None,
        "fy27_h1_expiry_claims_without_invoice_ref_pct": round(float(h1.inv.isna().mean() * 100), 1),
    }
    by_q = pd.DataFrame({"credit_notes": tat.groupby(c.fq).count(), "avg_days": tat.groupby(c.fq).mean(),
                         "pct_over_policy": (tat > CN_DAYS).groupby(c.fq).mean() * 100})
    return summary, by_q


def scheme_compliance(s: pd.DataFrame) -> pd.DataFrame:
    """Every scheme line checked against its circular (CO-POL-014 §4.2-4.4, Annexure B).

    * SKU in the circular's scope
    * invoice dated inside the validity window (22nd to month end)
    * free packs within the circular's ratio (rounded to the nearest pack, +1 tolerance)
    * order >= 1.5 x the stockist's average monthly purchase of that SKU over the
      three calendar months before the invoice month. This reading of "previous
      three months" is an assumption to confirm with Commercial Finance.
    """
    reg = scheme_register()
    sch = s[s.scheme_code.notna()].copy()
    sch = sch.join(reg[["tier", "terms", "free_per_pack", "skus", "valid_from", "valid_to"]], on="scheme_code")
    sch["sku_in_scope"] = [sku in scope for sku, scope in zip(sch.sku_code, sch.skus)]
    sch["in_window"] = sch.date.between(sch.valid_from, sch.valid_to)
    sch["free_above_terms"] = sch.free_qty > (sch.invoiced_qty * sch.free_per_pack).round() + 1

    month = s.assign(ym=s.date.dt.to_period("M")).groupby(["stockist_code", "sku_code", "ym"]).invoiced_qty.sum()
    line = (sch.groupby(["invoice_no", "sku_code"])
            .agg(scheme_code=("scheme_code", "first"), stockist_code=("stockist_code", "first"),
                 date=("date", "first"), inv=("invoiced_qty", "sum")).reset_index())
    ym = line.date.dt.to_period("M")
    prior = sum(month.reindex(list(zip(line.stockist_code, line.sku_code, ym - k))).fillna(0).to_numpy() for k in (1, 2, 3))
    line["below_moq"] = (line.inv > 0) & (line.inv < MOQ_MULTIPLE * prior / 3)

    out = sch.groupby("scheme_code").agg(
        tier=("tier", "first"), terms=("terms", "first"), lines=("invoice_no", "size"),
        paid_packs=("invoiced_qty", "sum"), free_packs=("free_qty", "sum"), free_value_lakh=("foc_value", "sum"),
        sku_out_of_scope=("sku_in_scope", lambda x: int((~x).sum())),
        outside_window=("in_window", lambda x: int((~x).sum())),
        free_above_terms=("free_above_terms", "sum"))
    out["free_value_lakh"] = out.free_value_lakh / LAKH
    out["order_lines_below_moq_pct"] = line.groupby("scheme_code").below_moq.mean() * 100
    out = out.join(reg[["circular", "fq", "valid_from", "valid_to"]])
    out["valid_from"] = out.valid_from.dt.date.astype(str)
    out["valid_to"] = out.valid_to.dt.date.astype(str)
    return out


# --------------------------------------------------------------------------- graph



def _records(df: pd.DataFrame, digits: int = 2) -> list:
    return df.round(digits).reset_index().replace({np.nan: None}).to_dict("records")


def _section(key, title, finding, tables, sources) -> dict:
    return {"key": key, "title": title, "finding": finding, "tables": tables, "sources": sources}


def validate_data(state: SchemeState) -> dict:
    f = frames()
    s, c = f["sales"], f["claims"]
    checks = {
        "primary_sales rows (raw -> deduplicated)": f"{f['raw_sales_rows']:,} -> {len(s):,}",
        "expiry_claims rows (raw -> deduplicated)": f"{f['raw_claim_rows']:,} -> {len(c):,}",
        "invoice dates": f"{s.date.min().date()} to {s.date.max().date()}",
        "claim dates": f"{c.date.min().date()} to {c.date.max().date()}",
        "unparsed dates (sales, claims)": f"{int(s.date.isna().sum())}, {int(c.date.isna().sum())}",
        "sales lines where value != qty x PTS": int((abs(s.invoiced_qty * s.pts_inr - s.net_value_inr) > 1).sum()),
        "scheme codes in sales not in Annexure B": sorted(set(s.scheme_code.dropna()) - set(scheme_register().index)),
    }
    if s.date.isna().any() or c.date.isna().any():
        raise ValueError(f"Unparsed dates in the extracts: {checks}")
    return {"data_checks": checks}


def quarterly_node(state: SchemeState) -> dict:
    s, c = frames()["sales"], frames()["claims"]
    q = quarterly_claims_foc(s, c)
    above = q[q.foc_above_cap_cr > 0]
    first, last = q.iloc[1], q.iloc[-1]     # first quarter has no claims yet (register starts 18-Apr-2024)
    finding = (f"NE/expiry claims rose from {first.ne_claims_pct:.2f}% of primary in {q.index[1]} to "
               f"{last.ne_claims_pct:.2f}% in {q.index[-1]}. Free goods were above the {CAP_PCT}% cap in "
               f"{len(above)} of {len(q)} quarters, INR {above.foc_above_cap_cr.sum():.2f} Cr in total above the cap.")
    return {"sections": [_section("quarterly", "Expiry claims and free goods as % of primary, by FY quarter", finding,
                                  {"by_quarter": _records(q)},
                                  ["primary_sales.csv (net_value_inr; free_qty x pts_inr)",
                                   "expiry_claims.csv (claim_value_inr, Near expiry + Expired)",
                                   format_citation("CO-POL-014", "4.4")])]}


def scheme_link_node(state: SchemeState) -> dict:
    since = state.get("request", {}).get("since", DEFAULT_SINCE)
    t = scheme_link(frames()["sales"], frames()["claims"], since)
    recent = t.loc[f"Since {since}"]
    on = recent.loc["Bought on a quarter-end scheme"] if "Bought on a quarter-end scheme" in recent.index else None
    finding = (f"Since {since}, {on.share_pct:.1f}% of NE/expiry claim value (INR {on.value_lakh:.1f} lakh) is on batches "
               f"the claiming stockist bought on a scheme line." if on is not None else "No scheme-bought claims found.")
    return {"sections": [_section("scheme_link", "Were the expired batches bought on a quarter-end scheme?", finding,
                                  {"by_link": _records(t, 1)},
                                  ["expiry_claims.csv joined to primary_sales.csv on stockist_code + batch_no",
                                   "scheme_code per CO-POL-014 Annexure B"])]}


def tier_node(state: SchemeState) -> dict:
    t, ta = tier_rates(frames()["sales"], frames()["claims"], frames()["sku"])
    a, n = t.loc["Tier A"], t.loc["No scheme"]
    finding = (f"Every SKU goes through the same national forecast, yet Tier A scheme SKUs return {a.claims_pct_of_sales:.2f}% "
               f"of sales as expiry claims against {n.claims_pct_of_sales:.2f}% for SKUs never on a scheme. "
               f"Tier A carries {a.share_of_claims_pct:.0f}% of all expiry claim value.")
    return {"sections": [_section("tier", "Expiry rate by scheme tier: same forecast, different outcomes", finding,
                                  {"by_tier": _records(t), "by_therapy_area": _records(ta, 1)},
                                  ["Tier SKU lists from config.SCHEME_CIRCULARS (CO-POL-014 Annexure B)",
                                   "primary_sales.csv; expiry_claims.csv; sku_master.csv (therapy_area)"])]}


def fefo_node(state: SchemeState) -> dict:
    since = state.get("request", {}).get("fefo_from", DEFAULT_FEFO_FROM)
    f = frames()
    t = fefo_dispatch(f["sales"], f["batch"], f["stock"], since)
    worst = t.non_fefo_pct_proxy.idxmax()
    others = t.drop(worst).non_fefo_pct_proxy
    finding = (f"Since {since}, {worst} shipped a later-expiry batch while an older one was in stock on "
               f"{t.loc[worst, 'non_fefo_pct_proxy']:.0f}% of lines, against {others.min():.0f}-{others.max():.0f}% elsewhere. "
               f"{t.loc[worst, 'below_min_rsl_pct']:.1f}% of its lines were below {MIN_RSL_PCT}% shelf life.")
    return {"sections": [_section("fefo", f"Short-dated dispatches and FEFO, by C&F (from {since})", finding,
                                  {"by_cfa": _records(t, 1)},
                                  ["primary_sales.csv + batch_master.csv (RSL at invoice date)",
                                   "cnf_stock_snapshot.csv (batches on hand at previous month-end)",
                                   format_citation("CO-POL-014", "7.1"),
                                   "FEFO proxy, not a WMS pick log"])]}


def settlement_node(state: SchemeState) -> dict:
    summary, by_q = settlement(frames()["claims"])
    finding = (f"Credit notes take {summary['avg_days_claim_to_cn']:.0f} days on average against {CN_DAYS} in policy; "
               f"{summary['pct_cn_later_than_policy']:.0f}% are late. {summary['pending_claims']} claims worth INR "
               f"{summary['pending_value_lakh']:.1f} lakh are pending, the oldest from {summary['oldest_pending']}. "
               f"The latest quarter looks faster only because its slow claims are still open.")
    return {"sections": [_section("settlement", "Settlement: time from claim to credit note, and the backlog", finding,
                                  {"summary": [summary], "by_quarter": _records(by_q, 1)},
                                  ["expiry_claims.csv (claim_date, credit_note_date, status)",
                                   format_citation("CO-POL-014", "5.6")])]}


def compliance_node(state: SchemeState) -> dict:
    t = scheme_compliance(frames()["sales"])
    finding = (f"{len(t)} scheme codes, {int(t.lines.sum()):,} scheme lines, INR {t.free_value_lakh.sum():.1f} lakh of free goods. "
               f"Lines outside the validity window: {int(t.outside_window.sum())}; SKUs outside the circular: "
               f"{int(t.sku_out_of_scope.sum())}; free packs above the circular's ratio: {int(t.free_above_terms.sum())}. "
               f"The {MOQ_MULTIPLE}x MOQ column (order_lines_below_moq_pct) swings from {t.order_lines_below_moq_pct.min():.0f}% to "
               f"{t.order_lines_below_moq_pct.max():.0f}% between circulars, so it is shown for review only until Commercial "
               f"Finance confirms how 'average monthly purchase' is measured. "
               f"The §4.5 stock norm ({STOCK_NORM_MONTHS} months of secondary) cannot be checked: no SSS is received.")
    return {"sections": [_section("compliance", "Scheme circulars against CO-POL-014 §4 and Annexure B", finding,
                                  {"by_scheme": _records(t, 1)},
                                  ["config.SCHEME_CIRCULARS (CO-POL-014 Annexure B, pp. 5-6)",
                                   format_citation("CO-POL-014", "4.2"), format_citation("CO-POL-014", "4.4"),
                                   format_citation("CO-POL-014", "4.5"), "primary_sales.csv (scheme_code, free_qty)"])]}


def _table_text(records: list) -> str:
    if not records:
        return "(no rows)"
    cols = list(records[0].keys())
    cells = [[("" if r[c] is None else f"{r[c]:,.2f}" if isinstance(r[c], float) else str(r[c])) for c in cols] for r in records]
    widths = [max(len(c), *(len(row[i]) for row in cells)) for i, c in enumerate(cols)]
    line = lambda vals: " | ".join(v.ljust(w) for v, w in zip(vals, widths))
    return "\n".join([line(cols), "-+-".join("-" * w for w in widths), *map(line, cells)])


ORDER = ["quarterly", "scheme_link", "tier", "fefo", "settlement", "compliance"]


def build_report(state: SchemeState) -> dict:
    parts = ["# Scheme pipeline report", "", "## Data checks"]
    parts += [f"- {k}: {v}" for k, v in state["data_checks"].items()]
    for sec in sorted(state["sections"], key=lambda x: ORDER.index(x["key"])):
        parts += ["", f"## {sec['title']}", "", sec["finding"]]
        for name, recs in sec["tables"].items():
            parts += ["", f"[{name}]", _table_text(recs)]
        parts += ["", "Sources: " + "; ".join(sec["sources"])]
    return {"report": "\n".join(parts)}


ANALYSIS_NODES = {
    "quarterly_claims_foc": quarterly_node,
    "scheme_link": scheme_link_node,
    "tier_rates": tier_node,
    "fefo_dispatch": fefo_node,
    "settlement": settlement_node,
    "scheme_compliance": compliance_node,
}

builder = StateGraph(SchemeState)
builder.add_node("validate_data", validate_data)
builder.add_node("build_report", build_report)
builder.add_edge(START, "validate_data")
for name, fn in ANALYSIS_NODES.items():
    builder.add_node(name, fn)
    builder.add_edge("validate_data", name)          # fan out: the six analyses run in parallel
builder.add_edge(list(ANALYSIS_NODES), "build_report")  # fan in: report waits for all six
builder.add_edge("build_report", END)
scheme_graph = builder.compile()


def run_scheme_pipeline(since: str = DEFAULT_SINCE, fefo_from: str = DEFAULT_FEFO_FROM) -> dict:
    return scheme_graph.invoke({"request": {"since": since, "fefo_from": fefo_from}, "sections": []})


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--since", default=DEFAULT_SINCE, help="start of the 'last 12 months' window")
    p.add_argument("--fefo-from", default=DEFAULT_FEFO_FROM, help="start of the FEFO / RSL window")
    a = p.parse_args(argv)
    print(run_scheme_pipeline(a.since, a.fefo_from)["report"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
