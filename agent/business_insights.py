"""Reproduce the claims, fill-rate, scheme, stock-balance, and control findings.

Run from the repository root with:
    python -m agent.business_insights

Optional CSV detail outputs:
    python -m agent.business_insights --output-dir output/business_insights
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import pandas as pd


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def parse_mixed_dates(values: pd.Series) -> pd.Series:
    """Parse ISO dates as ISO and other supported values as day-first dates."""
    text = values.astype("string").str.strip()
    iso_mask = text.str.match(r"^\d{4}-\d{2}-\d{2}(?:$|T|\s)", na=False)
    iso_dates = pd.to_datetime(
        text.where(iso_mask), format="mixed", errors="coerce"
    )
    day_first_dates = pd.to_datetime(
        text.where(~iso_mask), format="mixed", dayfirst=True, errors="coerce"
    )
    return iso_dates.combine_first(day_first_dates)


def parse_numbers(values: pd.Series) -> pd.Series:
    """Convert numeric strings, including comma-formatted values, to numbers."""
    return pd.to_numeric(
        values.astype("string").str.replace(",", "", regex=False),
        errors="coerce",
    )


def normalize_code(values: pd.Series, *, remove_hyphens: bool = False) -> pd.Series:
    """Normalize identifiers for comparison without changing source files."""
    normalized = values.astype("string").str.strip().str.upper()
    if remove_hyphens:
        normalized = normalized.str.replace("-", "", regex=False)
    return normalized


def load_inputs(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    required = {
        "primary_sales.csv",
        "expiry_claims.csv",
        "cnf_stock_snapshot.csv",
    }
    missing = sorted(name for name in required if not (data_dir / name).is_file())
    if missing:
        raise FileNotFoundError(
            f"Missing required input file(s) in {data_dir}: {', '.join(missing)}"
        )

    sales = pd.read_csv(data_dir / "primary_sales.csv")
    claims = pd.read_csv(data_dir / "expiry_claims.csv")
    stock = pd.read_csv(data_dir / "cnf_stock_snapshot.csv")

    sales["invoice_date"] = parse_mixed_dates(sales["invoice_date"])
    sales["ordered_qty"] = parse_numbers(sales["ordered_qty"])
    sales["invoiced_qty"] = parse_numbers(sales["invoiced_qty"])
    sales["free_qty"] = parse_numbers(sales["free_qty"])
    sales["net_value_inr"] = parse_numbers(sales["net_value_inr"])
    sales["pts_inr"] = parse_numbers(sales["pts_inr"])

    claims["claim_date"] = parse_mixed_dates(claims["claim_date"])
    claims["expiry_date_as_claimed"] = parse_mixed_dates(
        claims["expiry_date_as_claimed"]
    )
    claims["credit_note_date"] = parse_mixed_dates(claims["credit_note_date"])
    claims["claim_value_inr"] = parse_numbers(claims["claim_value_inr"])
    claims["credit_value_inr"] = parse_numbers(claims["credit_value_inr"])
    claims["status_normalized"] = claims["status"].astype("string").str.strip().str.upper()
    claims["claim_type_normalized"] = (
        claims["claim_type"].astype("string").str.strip().str.upper()
    )

    stock["snapshot_date"] = parse_mixed_dates(stock["snapshot_date"])
    stock["expiry_date"] = parse_mixed_dates(stock["expiry_date"])
    stock["qty_on_hand_packs"] = parse_numbers(stock["qty_on_hand_packs"])
    stock["avg_monthly_outward_packs"] = parse_numbers(
        stock["avg_monthly_outward_packs"]
    )
    stock["cnf_code_normalized"] = normalize_code(
        stock["cnf_code"], remove_hyphens=True
    )
    sales["quarter"] = sales["invoice_date"].dt.to_period("Q")
    claims["quarter"] = claims["claim_date"].dt.to_period("Q")
    claims["is_ne_or_expired"] = claims["claim_type_normalized"].isin(
        {"NEAR EXPIRY", "EXPIRED"}
    )
    return sales, claims, stock


def build_quarterly_metrics(
    sales: pd.DataFrame, claims: pd.DataFrame
) -> pd.DataFrame:
    sales_quarterly = sales.groupby("quarter").agg(
        primary_sales_inr=("net_value_inr", "sum"),
        ordered_qty=("ordered_qty", "sum"),
        invoiced_qty=("invoiced_qty", "sum"),
        free_qty=("free_qty", "sum"),
        sales_line_count=("invoice_no", "size"),
        missing_order_qty_lines=("ordered_qty", lambda values: values.isna().sum()),
    )
    sales_quarterly["fill_rate_pct"] = (
        sales_quarterly["invoiced_qty"] / sales_quarterly["ordered_qty"] * 100
    )
    sales_quarterly["invoiced_plus_free_fill_pct"] = (
        (sales_quarterly["invoiced_qty"] + sales_quarterly["free_qty"])
        / sales_quarterly["ordered_qty"]
        * 100
    )

    claims_quarterly = claims.groupby("quarter").agg(
        submitted_claim_value_inr=("claim_value_inr", "sum"),
        claim_count=("claim_no", "size"),
        ne_expired_claim_value_inr=(
            "claim_value_inr",
            lambda values: values.loc[claims.loc[values.index, "is_ne_or_expired"]].sum(),
        ),
        ne_expired_claim_count=(
            "is_ne_or_expired",
            "sum",
        ),
    )
    quarterly = sales_quarterly.join(claims_quarterly, how="outer").sort_index()
    quarterly["ne_expired_to_primary_sales_pct"] = (
        quarterly["ne_expired_claim_value_inr"]
        / quarterly["primary_sales_inr"]
        * 100
    )
    quarterly["submitted_claims_to_primary_sales_pct"] = (
        quarterly["submitted_claim_value_inr"]
        / quarterly["primary_sales_inr"]
        * 100
    )
    return quarterly


def stock_balance_analysis(stock: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    valid_stock = stock.dropna(
        subset=[
            "snapshot_date",
            "cnf_code_normalized",
            "sku_code",
            "qty_on_hand_packs",
            "avg_monthly_outward_packs",
        ]
    ).copy()
    if valid_stock.empty:
        return pd.DataFrame(), pd.DataFrame()

    cfa_aliases = (
        valid_stock.groupby("cnf_code_normalized")["cnf_code"]
        .agg(lambda values: " | ".join(sorted(values.astype(str).unique())))
        .rename("source_cfa_code_aliases")
    )
    latest_snapshot = valid_stock["snapshot_date"].max()
    latest = valid_stock.loc[valid_stock["snapshot_date"].eq(latest_snapshot)]
    grouped = (
        latest.groupby(["cnf_code_normalized", "sku_code"], dropna=False)
        .agg(
            on_hand_packs=("qty_on_hand_packs", "sum"),
            outward_values=("avg_monthly_outward_packs", "nunique"),
            monthly_outward_packs=("avg_monthly_outward_packs", "max"),
            batch_rows=("sku_code", "size"),
            batch_count=("batch_no", "nunique"),
        )
        .reset_index()
    )
    grouped["stock_cover_months"] = (
        grouped["on_hand_packs"]
        / grouped["monthly_outward_packs"].replace(0, pd.NA)
    )
    grouped["snapshot_date"] = latest_snapshot
    grouped = grouped.join(
        cfa_aliases, on="cnf_code_normalized", validate="many_to_one"
    )
    grouped["outward_rate_inconsistent_within_cfa_sku"] = grouped[
        "outward_values"
    ].gt(1)

    sku_spread = (
        grouped.groupby("sku_code")["stock_cover_months"]
        .agg(min_cover_months="min", max_cover_months="max")
        .reset_index()
    )
    sku_spread["cover_gap_months"] = (
        sku_spread["max_cover_months"] - sku_spread["min_cover_months"]
    )
    return grouped, sku_spread.sort_values("cover_gap_months", ascending=False)


def build_findings(
    sales: pd.DataFrame,
    claims: pd.DataFrame,
    stock: pd.DataFrame,
    quarterly: pd.DataFrame,
    cfa_sku: pd.DataFrame,
    sku_spread: pd.DataFrame,
) -> list[str]:
    findings = [
        "Method: NE/expiry means claims with type Near expiry or Expired. "
        "Quarter ratio = those claims' submitted value in the claim-date quarter "
        "divided by primary net sales in the invoice-date quarter; it is not "
        "a cohort-matched return rate."
    ]

    comparable_quarters = quarterly.dropna(
        subset=["primary_sales_inr", "ne_expired_claim_value_inr"]
    )
    if len(comparable_quarters) >= 2:
        first = comparable_quarters.iloc[0]
        latest = comparable_quarters.iloc[-1]
        first_q = comparable_quarters.index[0]
        latest_q = comparable_quarters.index[-1]
        findings.append(
            f"NE/expiry claims-to-sales ratio: {first_q} "
            f"{first['ne_expired_claim_value_inr'] / 1e7:.2f} cr / "
            f"{first['primary_sales_inr'] / 1e7:.2f} cr sales "
            f"({first['ne_expired_to_primary_sales_pct']:.2f}%) to "
            f"{latest_q} {latest['ne_expired_claim_value_inr'] / 1e7:.2f} cr / "
            f"{latest['primary_sales_inr'] / 1e7:.2f} cr sales "
            f"({latest['ne_expired_to_primary_sales_pct']:.2f}%). "
            "These endpoint quarters may not be the same quarter in different years."
        )
        if first_q.quarter == latest_q.quarter and first_q.year != latest_q.year:
            findings.append(
                f"Same-quarter year-over-year comparison: {first_q} to {latest_q}, "
                f"ratio moved from {first['ne_expired_to_primary_sales_pct']:.2f}% "
                f"to {latest['ne_expired_to_primary_sales_pct']:.2f}%."
            )
        else:
            prior_year = latest_q - 4
            if prior_year in comparable_quarters.index:
                prior = comparable_quarters.loc[prior_year]
                findings.append(
                    f"Same-quarter year-over-year comparison: {prior_year} to "
                    f"{latest_q}, ratio moved from "
                    f"{prior['ne_expired_to_primary_sales_pct']:.2f}% to "
                    f"{latest['ne_expired_to_primary_sales_pct']:.2f}%."
                )

    fill_quarters = quarterly.dropna(
        subset=["fill_rate_pct", "ordered_qty", "invoiced_qty"]
    )
    if not fill_quarters.empty:
        start = fill_quarters.iloc[0]
        end = fill_quarters.iloc[-1]
        findings.append(
            f"Aggregate fill proxy (invoiced quantity / known ordered quantity): "
            f"{fill_quarters.index[0]} {start['fill_rate_pct']:.2f}% to "
            f"{fill_quarters.index[-1]} {end['fill_rate_pct']:.2f}%. "
            f"{int(sales['ordered_qty'].isna().sum()):,} lines have no ordered "
            "quantity. This is not a confirmed service-level fill rate."
        )

    if not cfa_sku.empty:
        latest = cfa_sku["snapshot_date"].iloc[0].date()
        low = cfa_sku["stock_cover_months"].lt(1)
        high = cfa_sku["stock_cover_months"].gt(3)
        findings.append(
            f"Latest stock snapshot ({latest}): {int(low.sum())} CFA-SKU pairs "
            f"are below 1 month and {int(high.sum())} are above 3 months "
            "(screening thresholds only; no policy target was supplied). "
            "Inventory is CFA-level, not stockist-level."
        )
        low_skus = set(cfa_sku.loc[low, "sku_code"])
        high_skus = set(cfa_sku.loc[high, "sku_code"])
        spread_skus = set(sku_spread["sku_code"])
        balanced_candidates = sorted(low_skus & high_skus & spread_skus)
        findings.append(
            f"{len(balanced_candidates)} SKUs have at least one CFA below 1 month "
            "and another above 3 months. These are candidates for human transfer "
            "review, subject to batch expiry, demand and transfer feasibility."
        )
        inconsistent = int(
            cfa_sku["outward_rate_inconsistent_within_cfa_sku"].sum()
        )
        if inconsistent:
            findings.append(
                f"Monthly outward varies within {inconsistent} latest CFA-SKU "
                "groups; the script uses the maximum value and flags these groups. "
                "Validate the source denominator before interpreting cover."
            )

    coded = sales["scheme_code"].astype("string").str.strip().str.match(
        r"^QS-", case=False, na=False
    )
    if coded.any():
        scheme_metrics = (
            sales.loc[coded]
            .groupby("quarter")
            .agg(
                coded_sales_inr=("net_value_inr", "sum"),
                coded_free_qty=("free_qty", "sum"),
                coded_foc_value_estimate_inr=(
                    "free_qty",
                    lambda values: (
                        values * sales.loc[values.index, "pts_inr"]
                    ).sum(),
                ),
            )
            .sort_index()
        )
        if len(scheme_metrics) >= 2:
            first = scheme_metrics.iloc[0]
            last = scheme_metrics.iloc[-1]
            findings.append(
                f"QS-coded sales: FOC-at-PTS estimate changed from "
                f"INR {first['coded_foc_value_estimate_inr']:,.0f} "
                f"({int(first['coded_free_qty']):,} free packs) in "
                f"{scheme_metrics.index[0]} to "
                f"INR {last['coded_foc_value_estimate_inr']:,.0f} "
                f"({int(last['coded_free_qty']):,} free packs) in "
                f"{scheme_metrics.index[-1]}. This is a valuation proxy, not "
                "booked scheme cost or evidence of artificial demand."
            )

    missing_order = int(sales["ordered_qty"].isna().sum())
    findings.append(
        f"Demand visibility: {missing_order:,} sales lines lack ordered quantity. "
        "No secondary sell-out, stockist inventory, open-order status, lead time, "
        "or stock-out history is included; stockist-level stale allocation and "
        "true unfulfilled demand cannot be established."
    )

    repeated_claim_ids = int(
        claims.loc[
            claims["claim_no"].duplicated(keep=False), "claim_no"
        ].nunique()
    )
    pending = claims["status_normalized"].eq("PENDING")
    pending_value = claims.loc[pending, "claim_value_inr"].sum()
    missing_original_invoice = int(claims["original_invoice_ref"].isna().sum())
    missing_claim_value = int(claims["claim_value_inr"].isna().sum())
    findings.append(
        f"Claim-control signals: {repeated_claim_ids} repeated claim IDs; "
        f"{int(pending.sum()):,} pending records with INR {pending_value:,.2f} "
        f"submitted value; {missing_original_invoice:,} claims without an "
        f"original invoice reference; {missing_claim_value:,} without a numeric "
        "claim value. These indicate reconciliation work, not proof of manual "
        "processing or confirmed financial leakage."
    )
    dated_credit = claims.dropna(subset=["claim_date", "credit_note_date"])
    if not dated_credit.empty:
        turnaround = (
            dated_credit["credit_note_date"] - dated_credit["claim_date"]
        ).dt.days
        findings.append(
            f"Credited-record turnaround: median {turnaround.median():.0f} days, "
            f"90th percentile {turnaround.quantile(.9):.0f} days, "
            f"maximum {turnaround.max():.0f} days for "
            f"{len(dated_credit):,} records with both dates."
        )

    claim_days_to_expiry = (
        claims["expiry_date_as_claimed"] - claims["claim_date"]
    ).dt.days
    findings.append(
        f"Expiry timing: {int(claim_days_to_expiry.lt(0).sum()):,} claims were "
        f"filed after claimed expiry; {int(claim_days_to_expiry.between(0, 90).sum()):,} "
        "were filed within 90 days before claimed expiry. This is claim timing, "
        "not proof that inventory alerts were late."
    )

    valid_snapshot_expiry = stock.dropna(
        subset=["snapshot_date", "expiry_date", "qty_on_hand_packs"]
    ).copy()
    if not valid_snapshot_expiry.empty:
        days_to_expiry = (
            valid_snapshot_expiry["expiry_date"]
            - valid_snapshot_expiry["snapshot_date"]
        ).dt.days
        expired_qty = valid_snapshot_expiry.loc[
            days_to_expiry.lt(0), "qty_on_hand_packs"
        ].sum()
        near_qty = valid_snapshot_expiry.loc[
            days_to_expiry.between(0, 180), "qty_on_hand_packs"
        ].sum()
        findings.append(
            f"Latest snapshot expiry signal: {int(days_to_expiry.lt(0).sum())} "
            f"rows have expired dates and {int(days_to_expiry.between(0, 180).sum())} "
            f"rows expire within 180 days; recorded quantities are "
            f"{expired_qty:,.0f} and {near_qty:,.0f} packs respectively. "
            f"{int(stock['batch_no'].isna().sum())} source rows lack batch/expiry "
            "identifiers. Snapshot coverage does not prove a warning system "
            "identified risk early or late."
        )
    findings.append(
        "Manual claims, stale stockist allocation, and scheme-caused loading are "
        "hypotheses requiring workflow logs, dated stockist inventory, and scheme "
        "eligibility/cap plus sell-out/control data."
    )
    return findings


def run(data_dir: Path, output_dir: Path | None) -> str:
    sales, claims, stock = load_inputs(data_dir)
    quarterly = build_quarterly_metrics(sales, claims)
    cfa_sku, sku_spread = stock_balance_analysis(stock)
    findings = build_findings(sales, claims, stock, quarterly, cfa_sku, sku_spread)

    report_lines = ["Project Sankalp: reproducible inference checks", ""]
    report_lines.extend(f"- {finding}" for finding in findings)
    report_lines.extend(
        [
            "",
            "Quarterly detail (currency amounts are source-reported INR):",
            quarterly.to_string(float_format=lambda value: f"{value:,.2f}"),
        ]
    )
    report = "\n".join(report_lines)

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        quarterly.to_csv(output_dir / "quarterly_metrics.csv")
        cfa_sku.to_csv(output_dir / "latest_cfa_sku_stock_cover.csv", index=False)
        sku_spread.to_csv(output_dir / "latest_sku_cover_spread.csv", index=False)
        (output_dir / "business_insights.md").write_text(report, encoding="utf-8")
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DATA_DIR,
        help="Directory containing the source CSVs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional directory for Markdown and CSV detail outputs.",
    )
    args = parser.parse_args(argv)
    print(run(args.data_dir, args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
