"""Expiry returns: how much is linked to quarter-end schemes, step by step.

Reproduces, with every intermediate number, the two claims in the problem statement:

  A. "91.3% of NE/expiry claim value is on batches the same stockist bought on a
     quarter-end scheme line", what that test really measures, and the stronger
     evidence: pack-weighted share, baseline and claim rates.
  B. "82% of claim value is in Tier A scheme SKUs", with shelf life and the
     quarterly trend as the check against confounding.

Standalone: reads the extracts through data.py and the scheme register through
config.py; graph_schema.py is not used or changed. Run from the repository root:

    python -m agent.Discovery.expiry_attribution
    python -m agent.Discovery.expiry_attribution --since 2025-10-01
"""
from __future__ import annotations

import argparse
import re

import numpy as np
import pandas as pd

from agent.config import SCHEME_CIRCULARS

NE_TYPES = ["Near expiry", "Expired"]
DEFAULT_SINCE = "2025-10-01"          # last 12 months of the extract (ends 30-Sep-2026)
CRORE, LAKH = 1e7, 1e5
SCHEME_BUCKETS = [-0.01, 0, 0.25, 0.5, 1.0]
BUCKET_LABELS = ["0%", "1-25%", "26-50%", ">50%"]


# --------------------------------------------------------------------------- data
def load() -> dict:
    """Cleaned sales, claims and SKU master, with repeated rows removed.

    data.py calls drop_duplicates() without keeping the result, so it is done
    here. The index is kept, so csv_row = index + 2 still points at the raw file.
    """
    from agent.data import sales, claims, sku_df

    key = ["invoice_no", "date", "cnf_code", "stockist_code", "sku_code", "batch_no",
           "ordered_qty", "invoiced_qty", "free_qty", "net_value_inr", "scheme_code"]
    s = sales.drop_duplicates(subset=key).copy()
    s["scheme_code"] = s.scheme_code.where(~s.scheme_code.isin(["-", "NA", ""]))
    s["csv_row"] = s.index + 2
    c = claims.drop_duplicates(subset=[x for x in claims.columns if x not in ("date", "exp", "cn_date")]).copy()
    c["csv_row"] = c.index + 2
    return {"sales": s, "claims": c, "sku": sku_df.drop_duplicates("sku_code"),
            "raw": (len(sales), len(claims))}


def fy_quarter(d: pd.Series) -> pd.Series:
    fy = d.dt.year + (d.dt.month >= 4).astype(int)
    q = ((d.dt.month - 4) % 12) // 3 + 1
    return "FY" + (fy % 100).astype(str).str.zfill(2) + "Q" + q.astype(str)


def scheme_tiers() -> dict[str, set]:
    """Tier A / Tier B SKU sets from CO-POL-014 Annexure B (config.SCHEME_CIRCULARS),
    resolving 'As QS-FY25Q3-A' references. Uses the latest circular of each tier."""
    by_code = {c["scheme_codes"][0]: c for c in SCHEME_CIRCULARS}

    def skus(code):
        scope = by_code[code]["sku_scope"]
        m = re.match(r"As (\S+)", scope)
        return skus(m.group(1)) if m else {x.strip() for x in scope.split(",")}

    latest = {tier: max(code for code in by_code if code.endswith(f"-{tier}")) for tier in ("A", "B")}
    return {"Tier A": skus(latest["A"]), "Tier B": skus(latest["B"])}


def tier_of(sku_codes: pd.Series) -> pd.Series:
    t = scheme_tiers()
    return pd.Series(np.where(sku_codes.isin(t["Tier A"]), "Tier A",
                              np.where(sku_codes.isin(t["Tier B"]), "Tier B", "No scheme")), index=sku_codes.index)


def stockist_batch_pairs(sales: pd.DataFrame) -> pd.DataFrame:
    """One row per stockist + batch: how it was bought.

    any_scheme    at least one invoice line for this pair carries a scheme code
    scheme_packs  paid + free packs on scheme lines
    packs         all paid + free packs of this batch sold to this stockist
    scheme_share  scheme_packs / packs
    """
    s = sales[sales.batch_no.notna()].assign(on_scheme=lambda d: d.scheme_code.notna(),
                                             packs=lambda d: d.invoiced_qty + d.free_qty)
    g = s.groupby(["stockist_code", "batch_no"])
    pairs = pd.DataFrame({
        "sku_code": g.sku_code.first(),
        "any_scheme": g.on_scheme.any(),
        "scheme_packs": s[s.on_scheme].groupby(["stockist_code", "batch_no"]).packs.sum(),
        "packs": g.packs.sum(),
        "value_inr": g.net_value_inr.sum(),
        "lines": g.size(),
    })
    pairs["scheme_packs"] = pairs.scheme_packs.fillna(0)
    pairs["scheme_share"] = pairs.scheme_packs / pairs.packs
    return pairs


def expiry_claims(claims: pd.DataFrame, since: str | None = None) -> pd.DataFrame:
    ne = claims[claims.claim_type.isin(NE_TYPES)]
    return ne[ne.date >= since] if since else ne


def attach_pairs(ne: pd.DataFrame, pairs: pd.DataFrame) -> pd.DataFrame:
    m = ne.merge(pairs.drop(columns="sku_code"), left_on=["stockist_code", "batch_no"], right_index=True, how="left")
    m["link"] = np.select(
        [m.any_scheme.isna(), m.any_scheme.astype("boolean").fillna(False).astype(bool)],
        ["Never sold to this stockist in extract", "Bought at least once on a scheme line"],
        "Bought, never on a scheme line")
    return m


# --------------------------------------------------------------------------- part A
def a_scheme_link_shares(m: pd.DataFrame) -> pd.DataFrame:
    """Step A3: claim value by how the stockist bought the batch (the 91.3% test)."""
    t = m.groupby("link").agg(claims=("claim_no", "size"), claims_with_value=("val", "count"), value_inr=("val", "sum"))
    t["share_pct"] = t.value_inr / t.value_inr.sum() * 100
    return t.sort_values("value_inr", ascending=False)


def a_overlap(m: pd.DataFrame) -> dict:
    """Step A4: does 'bought on scheme' mean the claimed packs came from the scheme line?"""
    sc = m[m.any_scheme == True]                                   # noqa: E712 (nullable boolean)
    return {"scheme_flagged_claims": len(sc),
            "pair_also_bought_off_scheme": int((sc.scheme_packs < sc.packs).sum()),
            "median_purchase_lines_per_pair": float(sc.lines.median()),
            "median_scheme_share_of_packs_pct": float(sc.scheme_share.median() * 100)}


def a_example(m: pd.DataFrame, sales: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
    """The first scheme-flagged claim whose stockist also bought the batch off-scheme, with its purchases."""
    sc = m[(m.any_scheme == True) & (m.scheme_packs < m.packs)].sort_values(["date", "claim_no"])   # noqa: E712
    ex = sc.iloc[0]
    rows = sales[(sales.stockist_code == ex.stockist_code) & (sales.batch_no == ex.batch_no)]
    return ex, rows[["csv_row", "invoice_no", "date", "invoiced_qty", "free_qty", "scheme_code"]].sort_values("date")


def a_pack_weighted_share(m: pd.DataFrame) -> float:
    """Step A5: credit each claim to schemes only in proportion to the pair's scheme packs."""
    v = m.val.fillna(0)
    return float((v * m.scheme_share.fillna(0)).sum() / v.sum() * 100)


def a_baseline(pairs: pd.DataFrame) -> dict:
    """Step A6: how common are scheme pairs in sales? (what 91% must be compared with)"""
    return {"sales_value_in_scheme_pairs_pct": float(pairs.loc[pairs.any_scheme, "value_inr"].sum() / pairs.value_inr.sum() * 100),
            "packs_on_scheme_lines_pct": float(pairs.scheme_packs.sum() / pairs.packs.sum() * 100)}


def a_claim_rates(ne_all: pd.DataFrame, pairs: pd.DataFrame) -> pd.DataFrame:
    """Step A7: expiry-claim value as % of sales value, scheme pairs vs never-scheme pairs,
    for all SKUs and for Tier A only (same products, so product mix is held constant)."""
    claim_by_pair = ne_all.groupby(["stockist_code", "batch_no"]).val.sum()
    p = pairs.assign(claims_inr=claim_by_pair.reindex(pairs.index).fillna(0).to_numpy(), tier=tier_of(pairs.sku_code).to_numpy())
    rows = []
    for scope, frame in [("All SKUs", p), ("Tier A only", p[p.tier == "Tier A"])]:
        for flag, label in [(True, "Bought on a scheme line"), (False, "Never on a scheme line")]:
            f = frame[frame.any_scheme == flag]
            rows.append({"scope": scope, "pairs": label, "n_pairs": len(f), "sales_cr": f.value_inr.sum() / CRORE,
                         "claims_lakh": f.claims_inr.sum() / LAKH, "claim_rate_pct": f.claims_inr.sum() / f.value_inr.sum() * 100})
    return pd.DataFrame(rows)


def a_dose_response(ne_all: pd.DataFrame, pairs: pd.DataFrame) -> pd.DataFrame:
    """Step A8: within Tier A, claim rate by the share of the pair's packs bought on scheme."""
    claim_by_pair = ne_all.groupby(["stockist_code", "batch_no"]).val.sum()
    p = pairs[tier_of(pairs.sku_code) == "Tier A"].copy()
    p["claims_inr"] = claim_by_pair.reindex(p.index).fillna(0)
    p["scheme_share_bucket"] = pd.cut(p.scheme_share, SCHEME_BUCKETS, labels=BUCKET_LABELS)
    t = p.groupby("scheme_share_bucket", observed=True).agg(n_pairs=("packs", "size"), sales_inr=("value_inr", "sum"),
                                                              claims_inr=("claims_inr", "sum"))
    t["claim_rate_pct"] = t.claims_inr / t.sales_inr * 100
    return t.assign(sales_cr=t.sales_inr / CRORE, claims_lakh=t.claims_inr / LAKH)[
        ["n_pairs", "sales_cr", "claims_lakh", "claim_rate_pct"]]


# --------------------------------------------------------------------------- part B
def b_tier_shares(ne: pd.DataFrame, sales: pd.DataFrame) -> pd.DataFrame:
    """Step B2: claim value and sales value by scheme tier (the 82% figure)."""
    t = pd.DataFrame({"claims_cr": ne.groupby(tier_of(ne.sku_code)).val.sum() / CRORE,
                      "sales_cr": sales.groupby(tier_of(sales.sku_code)).net_value_inr.sum() / CRORE})
    t["share_of_claims_pct"] = t.claims_cr / t.claims_cr.sum() * 100
    t["share_of_sales_pct"] = t.sales_cr / t.sales_cr.sum() * 100
    t["claim_rate_pct"] = t.claims_cr / t.sales_cr * 100
    return t.loc[["Tier A", "Tier B", "No scheme"]]


def b_shelf_life(sku: pd.DataFrame) -> pd.DataFrame:
    """Step B3: the confounder. Do Tier A SKUs simply have shorter shelf lives?"""
    x = sku.assign(tier=tier_of(sku.sku_code))
    return x.groupby("tier").shelf_life_months.agg(skus="size", avg_months="mean", min_months="min",
                                                   skus_with_18_months=lambda v: int((v == 18).sum())).loc[["Tier A", "Tier B", "No scheme"]]


def b_quarterly_trend(ne: pd.DataFrame) -> pd.DataFrame:
    """Step B4: claims by quarter and tier. Shelf life is constant, so a step change
    after the scheme terms changed points at the scheme, not the product."""
    t = ne.assign(fq=fy_quarter(ne.date), tier=tier_of(ne.sku_code)).pivot_table(
        index="fq", columns="tier", values="val", aggfunc="sum").fillna(0) / LAKH
    return t[["Tier A", "Tier B", "No scheme"]]


# --------------------------------------------------------------------------- report
def show(title: str, obj, digits: int = 2):
    print(f"\n{title}")
    if isinstance(obj, pd.DataFrame):
        print(obj.round(digits).to_string())
    elif isinstance(obj, dict):
        for k, v in obj.items():
            print(f"  {k:40s} {round(v, digits) if isinstance(v, float) else v}")
    else:
        print(f"  {obj}")


def run(since: str = DEFAULT_SINCE) -> dict:
    d = load()
    s, c, sku = d["sales"], d["claims"], d["sku"]
    ne_all, ne = expiry_claims(c), expiry_claims(c, since)
    pairs = stockist_batch_pairs(s)
    m = attach_pairs(ne, pairs)
  

    out = {
        "since": since,
        "claims_in_scope": {"claims": len(ne), "value_cr": ne.val.sum() / CRORE, "blank_value": int(ne.val.isna().sum())},
        "pairs": {"stockist_batch_pairs": len(pairs), "with_a_scheme_line": int(pairs.any_scheme.sum())},
        "link": a_scheme_link_shares(m),
        "overlap": a_overlap(m),
        "example": a_example(m, s),
        "pack_weighted_pct": a_pack_weighted_share(m),
        "baseline": a_baseline(pairs),
        "claim_rates": a_claim_rates(ne_all, pairs),
        "dose": a_dose_response(ne_all, pairs),
        "tiers_all": b_tier_shares(ne_all, s),
        "tiers_since": b_tier_shares(ne, s[s.date >= since]),
        "shelf_life": b_shelf_life(sku),
        "trend": b_quarterly_trend(ne_all),
        "raw_rows": d["raw"], "clean_rows": (len(s), len(c)),
    }
    return out


def print_report(r: dict):
    since = r["since"]
    link = r["link"]
    on = link.loc["Bought at least once on a scheme line"]
    print("=" * 78)
    print("EXPIRY RETURNS: LINK TO QUARTER-END SCHEMES")
    print("Sources: primary_sales.csv, expiry_claims.csv, sku_master.csv; tiers from CO-POL-014 Annexure B")
    print("=" * 78)

    print("\nPART A. Were the expired batches bought on a quarter-end scheme?")
    show("A1. Clean the extracts (repeated rows removed)",
         {"primary_sales rows raw -> clean": f"{r['raw_rows'][0]:,} -> {r['clean_rows'][0]:,}",
          "expiry_claims rows raw -> clean": f"{r['raw_rows'][1]:,} -> {r['clean_rows'][1]:,}"})
    show(f"A2. Near expiry + Expired claims dated on or after {since}", r["claims_in_scope"])
    show("A3. Stockist + batch pairs in primary_sales (flag: any invoice line with a QS- scheme code)", r["pairs"])
    show("A4. Join claims to pairs on stockist_code + batch_no; claim value by flag  <- headline share",
         link.assign(value_cr=link.value_inr / CRORE).drop(columns="value_inr"))
    print(f"\n  => {on.share_pct:.1f}% of claim value is on batches the stockist bought at least once on a scheme line.")

    show("A5. Caveat: the flag does not mean the claimed packs came from the scheme line", r["overlap"], 1)
    ex, rows = r["example"]
    print(f"\n  Example: {ex.claim_no} (expiry_claims.csv row {ex.csv_row}), {ex.stockist_code}, batch {ex.batch_no}, "
          f"{ex.qty:.0f} packs. Purchases of this batch by this stockist:")
    print("  " + rows.to_string(index=False).replace("\n", "\n  "))

    show("A6. Pack-weighted share (credit each claim to schemes only by the pair's share of scheme packs)",
         f"{r['pack_weighted_pct']:.1f}% of claim value")
    show("A7. Baseline: how common are scheme pairs in sales?", r["baseline"], 1)
    print(f"  => scheme pairs carry {r['baseline']['sales_value_in_scheme_pairs_pct']:.0f}% of sales value "
          f"but {on.share_pct:.0f}% of claim value")
    show("A8. Expiry-claim rate (claim value / sales value), all periods", r["claim_rates"])
    show("A9. Tier A only: claim rate by share of the pair's packs bought on scheme", r["dose"])

    print("\nPART B. Expiry claims by scheme tier")
    tiers = scheme_tiers()
    show("B1. Tiers from Annexure B", {k: ", ".join(sorted(v)) for k, v in tiers.items()} | {"No scheme": "all other SKUs"})
    show("B2. Claim value vs sales value by tier, all periods  <- headline share", r["tiers_all"])
    show(f"    Same, claims and sales on or after {since}", r["tiers_since"])
    show("B3. Confounder check: shelf life by tier (sku_master.csv)", r["shelf_life"], 1)
    show("B4. Claim value by quarter and tier, INR lakh (shelf life is constant; schemes changed in FY25Q3)", r["trend"], 1)

    rates = r["claim_rates"].set_index(["scope", "pairs"]).claim_rate_pct
    ta = r["tiers_all"].loc["Tier A"]
    trend = r["trend"]["Tier A"]
    print("\nSUMMARY (every number above, recomputed)")
    print(f"  Stockist-batch pairs ever bought on a quarter-end scheme carry "
          f"{r['baseline']['sales_value_in_scheme_pairs_pct']:.0f}% of sales but {on.share_pct:.1f}% of expiry-claim value "
          f"since {since} ({r['pack_weighted_pct']:.1f}% if credited only by the share of packs bought on scheme).")
    print(f"  Their claim rate is {rates[('All SKUs', 'Bought on a scheme line')]:.2f}% of sales against "
          f"{rates[('All SKUs', 'Never on a scheme line')]:.2f}% for pairs never on a scheme "
          f"(Tier A only: {rates[('Tier A only', 'Bought on a scheme line')]:.2f}% vs {rates[('Tier A only', 'Never on a scheme line')]:.2f}%).")
    print(f"  Tier A SKUs carry {ta.share_of_claims_pct:.1f}% of claim value on {ta.share_of_sales_pct:.1f}% of sales; "
          f"Tier A claims went from INR {trend.iloc[0]:.1f} lakh in {trend.index[0]} to INR {trend.iloc[-1]:.1f} lakh in {trend.index[-1]}.")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Expiry returns: link to quarter-end schemes, step by step.")
    p.add_argument("--since", default=DEFAULT_SINCE, help="start of the claim window for parts A2-A6 (YYYY-MM-DD)")
    a = p.parse_args(argv)
    pd.set_option("display.width", 200)
    print_report(run(a.since))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
