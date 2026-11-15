"""Exploratory analysis for the primary sales CSV.

Run from the repository root:
    python -m agent.primary_sales_eda

Outputs are written to output/primary_sales_eda by default. Source data is
never modified, and duplicate or invalid rows are reported rather than removed.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT_DIR / "data" / "primary_sales.csv"
DEFAULT_OUTPUT = ROOT_DIR / "output" / "primary_sales_eda"
DATE_COLUMN = "invoice_date"
NUMERIC_COLUMNS = (
    "ordered_qty",
    "invoiced_qty",
    "free_qty",
    "pts_inr",
    "net_value_inr",
)
IDENTIFIER_COLUMNS = (
    "invoice_no",
    "cnf_code",
    "stockist_code",
    "sku_code",
    "batch_no",
    "scheme_code",
)
SEGMENT_COLUMNS = (
    "cnf_code",
    "stockist_code",
    "sku_code",
    "batch_no",
    "scheme_code",
)
LOGGER = logging.getLogger("primary_sales_eda")


def parse_mixed_dates(values: pd.Series) -> pd.Series:
    """Parse ISO values as ISO and other supported values as day-first dates."""
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
    """Parse numeric strings, including values containing thousands separators."""
    cleaned = values.astype("string").str.strip().str.replace(",", "", regex=False)
    return pd.to_numeric(cleaned, errors="coerce")


def load_sales(input_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read the CSV as strings and create parsed analysis columns."""
    if not input_path.is_file():
        raise FileNotFoundError(f"Primary sales CSV not found: {input_path}")

    frame = pd.read_csv(input_path, dtype="string")
    source_columns = list(frame.columns)
    required = {DATE_COLUMN, *NUMERIC_COLUMNS, *IDENTIFIER_COLUMNS}
    missing_columns = sorted(required.difference(frame.columns))
    if missing_columns:
        raise ValueError(
            "Primary sales CSV is missing required columns: "
            + ", ".join(missing_columns)
        )

    frame[f"{DATE_COLUMN}_parsed"] = parse_mixed_dates(frame[DATE_COLUMN])
    for column in NUMERIC_COLUMNS:
        frame[f"{column}_parsed"] = parse_numbers(frame[column])

    quality_rows: list[dict[str, object]] = []

    def add_issue(
        issue: str, column: str, count: int, remediation: str
    ) -> None:
        quality_rows.append(
            {
                "issue": issue,
                "column": column,
                "count": count,
                "percent_of_rows": (
                    count / len(frame) * 100 if len(frame) else 0.0
                ),
                "recommended_review": remediation,
            }
        )

    for column in source_columns:
        if column == "scheme_code":
            continue
        missing_count = int(frame[column].isna().sum())
        if missing_count:
            add_issue(
                "Missing values",
                column,
                missing_count,
                "Confirm whether the field is optional; do not impute without a business rule.",
            )

    invalid_dates = int(
        (frame[DATE_COLUMN].notna() & frame[f"{DATE_COLUMN}_parsed"].isna()).sum()
    )
    if invalid_dates:
        add_issue(
            "Unparseable dates",
            DATE_COLUMN,
            invalid_dates,
            "Validate the source date format and correct at source where possible.",
        )

    for column in NUMERIC_COLUMNS:
        parsed_column = f"{column}_parsed"
        invalid_count = int(
            (frame[column].notna() & frame[parsed_column].isna()).sum()
        )
        if invalid_count:
            add_issue(
                "Unparseable numeric values",
                column,
                invalid_count,
                "Validate source formatting and units before converting.",
            )
        negative_count = int((frame[parsed_column] < 0).sum())
        if negative_count:
            add_issue(
                "Negative values for review",
                column,
                negative_count,
                "Check whether returns, adjustments, or data-entry errors explain the value.",
            )
        zero_count = int((frame[parsed_column] == 0).sum())
        if zero_count and column != "free_qty":
            add_issue(
                "Zero values for review",
                column,
                zero_count,
                "Confirm whether zero is valid for this measure and transaction type.",
            )

    duplicate_count = int(frame.duplicated(subset=source_columns).sum())
    if duplicate_count:
        add_issue(
            "Exact duplicate rows",
            "all columns",
            duplicate_count,
            "Review source records; rows are retained and not automatically removed.",
        )

    if "ordered_qty_parsed" in frame and "invoiced_qty_parsed" in frame:
        over_invoiced = int(
            (
                frame["invoiced_qty_parsed"].notna()
                & frame["ordered_qty_parsed"].notna()
                & (
                    frame["invoiced_qty_parsed"]
                    > frame["ordered_qty_parsed"]
                )
            ).sum()
        )
        if over_invoiced:
            add_issue(
                "Invoiced quantity exceeds ordered quantity",
                "ordered_qty, invoiced_qty",
                over_invoiced,
                "Check order amendments, units, and invoice-line matching.",
            )

    key_columns = ["invoice_no", "sku_code", "batch_no"]
    candidate_key_duplicates = int(
        frame.duplicated(subset=key_columns, keep=False).sum()
    )
    if candidate_key_duplicates:
        add_issue(
            "Rows sharing candidate invoice/SKU/batch key",
            ", ".join(key_columns),
            candidate_key_duplicates,
            "Review as a candidate-key collision; multiple legitimate lines may share this key.",
        )

    quality = pd.DataFrame(
        quality_rows,
        columns=[
            "issue",
            "column",
            "count",
            "percent_of_rows",
            "recommended_review",
        ],
    )
    return frame, quality


def profile_columns(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column in frame.columns:
        original_column = column.removesuffix("_parsed")
        if original_column in frame.columns:
            source = frame[original_column]
        else:
            source = frame[column]
        examples = source.dropna().astype(str).drop_duplicates().head(3).tolist()
        parsed_column = f"{original_column}_parsed"
        rows.append(
            {
                "column": original_column,
                "source_dtype": str(source.dtype),
                "analysis_dtype": (
                    str(frame[parsed_column].dtype)
                    if parsed_column in frame.columns
                    else str(source.dtype)
                ),
                "non_null_count": int(source.notna().sum()),
                "missing_count": int(source.isna().sum()),
                "unique_values": int(source.nunique(dropna=True)),
                "example_values": " | ".join(examples),
            }
        )
    return pd.DataFrame(rows).drop_duplicates(subset="column", keep="first")


def summarize_segments(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    """Aggregate sales without dropping rows with missing segment values."""
    label = frame[column].astype("string").str.strip()
    if column == "scheme_code":
        label = label.mask(label.isna() | label.isin(["", "-"]), "No scheme")
    work = frame.assign(
        segment=label.fillna("(Missing)"),
        foc_value_at_pts_estimate_inr=(
            frame["free_qty_parsed"] * frame["pts_inr_parsed"]
        ),
    )
    result = (
        work.groupby("segment", dropna=False)
        .agg(
            sales_lines=("invoice_no", "size"),
            invoices=("invoice_no", "nunique"),
            ordered_qty=("ordered_qty_parsed", "sum"),
            invoiced_qty=("invoiced_qty_parsed", "sum"),
            free_qty=("free_qty_parsed", "sum"),
            foc_value_at_pts_estimate_inr=(
                "foc_value_at_pts_estimate_inr",
                "sum",
            ),
            net_sales_inr=("net_value_inr_parsed", "sum"),
        )
        .reset_index()
        .sort_values("net_sales_inr", ascending=False)
    )
    total_sales = result["net_sales_inr"].sum()
    result["net_sales_share_pct"] = (
        result["net_sales_inr"] / total_sales * 100 if total_sales else 0.0
    )
    return result


def make_plots(
    frame: pd.DataFrame, output_dir: Path, segment_tables: dict[str, pd.DataFrame]
) -> list[str]:
    plot_dir = output_dir / "visualizations"
    plot_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    dated = frame.dropna(subset=[f"{DATE_COLUMN}_parsed"]).copy()
    if not dated.empty:
        dated["month"] = (
            dated[f"{DATE_COLUMN}_parsed"].dt.to_period("M").astype(str)
        )
        monthly = dated.groupby("month")["net_value_inr_parsed"].sum()
        monthly.index = pd.PeriodIndex(monthly.index, freq="M").to_timestamp()
        fig, axis = plt.subplots(figsize=(12, 5))
        axis.plot(monthly.index, monthly.values, marker="o", linewidth=1.5)
        axis.set(title="Primary sales by invoice month", xlabel="Month", ylabel="Net sales (INR)")
        axis.tick_params(axis="x", rotation=60)
        axis.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        name = "monthly_net_sales.png"
        fig.savefig(plot_dir / name, dpi=150)
        plt.close(fig)
        created.append(name)

    for column in ("sku_code", "cnf_code", "stockist_code", "scheme_code"):
        table = segment_tables.get(column)
        if table is None or table.empty:
            continue
        top = table.head(12).sort_values("net_sales_inr")
        fig, axis = plt.subplots(figsize=(10, 6))
        axis.barh(top["segment"].astype(str), top["net_sales_inr"])
        axis.set(title=f"Top sales segments: {column}", xlabel="Net sales (INR)")
        axis.grid(axis="x", alpha=0.25)
        fig.tight_layout()
        name = f"top_{column}_sales.png"
        fig.savefig(plot_dir / name, dpi=150)
        plt.close(fig)
        created.append(name)

    sales_values = frame["net_value_inr_parsed"].dropna()
    if not sales_values.empty:
        fig, axis = plt.subplots(figsize=(9, 5))
        axis.hist(sales_values, bins=40)
        axis.set(
            title="Distribution of primary sales line values",
            xlabel="Net sales per line (INR)",
            ylabel="Line count",
        )
        axis.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        name = "net_sales_line_value_histogram.png"
        fig.savefig(plot_dir / name, dpi=150)
        plt.close(fig)
        created.append(name)

        fig, axis = plt.subplots(figsize=(8, 5))
        axis.boxplot(sales_values, orientation="horizontal", showfliers=False)
        axis.set(
            title="Net sales line value (box plot; outliers hidden)",
            xlabel="Net sales per line (INR)",
        )
        axis.grid(axis="x", alpha=0.25)
        fig.tight_layout()
        name = "net_sales_line_value_boxplot.png"
        fig.savefig(plot_dir / name, dpi=150)
        plt.close(fig)
        created.append(name)

    numeric = frame[[f"{name}_parsed" for name in NUMERIC_COLUMNS]].apply(
        pd.to_numeric, errors="coerce"
    )
    correlation = numeric.corr()
    if len(correlation.columns) > 1 and correlation.notna().any().any():
        fig, axis = plt.subplots(figsize=(8, 6))
        image = axis.imshow(correlation, cmap="coolwarm", vmin=-1, vmax=1)
        axis.set_xticks(range(len(correlation.columns)))
        axis.set_yticks(range(len(correlation.columns)))
        labels = [column.removesuffix("_parsed") for column in correlation.columns]
        axis.set_xticklabels(labels, rotation=45, ha="right")
        axis.set_yticklabels(labels)
        axis.set_title("Correlation of numeric sales fields")
        fig.colorbar(image, ax=axis, label="Correlation")
        fig.tight_layout()
        name = "numeric_correlation_heatmap.png"
        fig.savefig(plot_dir / name, dpi=150)
        plt.close(fig)
        created.append(name)
    return created


def write_report(
    frame: pd.DataFrame,
    quality: pd.DataFrame,
    segment_tables: dict[str, pd.DataFrame],
    output_dir: Path,
    plots: list[str],
    source_column_count: int,
) -> None:
    parsed_dates = frame[f"{DATE_COLUMN}_parsed"].dropna()
    net_sales = frame["net_value_inr_parsed"].sum(min_count=1)
    ordered = frame["ordered_qty_parsed"].sum(min_count=1)
    invoiced = frame["invoiced_qty_parsed"].sum(min_count=1)
    fill_rate = invoiced / ordered * 100 if pd.notna(ordered) and ordered else None
    free_qty = frame["free_qty_parsed"].sum(min_count=1)
    foc_estimate = (
        frame["free_qty_parsed"] * frame["pts_inr_parsed"]
    ).sum(min_count=1)
    duplicate_count = int(
        quality.loc[quality["issue"] == "Exact duplicate rows", "count"].sum()
    )

    lines = [
        "# Primary Sales EDA",
        "",
        "## Dataset overview",
        "",
        f"- Records: {len(frame):,}",
        f"- Columns in source: {source_column_count:,}",
        f"- Invoice date coverage: {parsed_dates.min().date() if not parsed_dates.empty else 'Unavailable'} to {parsed_dates.max().date() if not parsed_dates.empty else 'Unavailable'}",
        f"- Sum of recorded net sales: INR {net_sales:,.2f}" if pd.notna(net_sales) else "- Sum of recorded net sales: unavailable",
        f"- Ordered quantity: {ordered:,.2f}" if pd.notna(ordered) else "- Ordered quantity: unavailable",
        f"- Invoiced quantity: {invoiced:,.2f}" if pd.notna(invoiced) else "- Invoiced quantity: unavailable",
        f"- Aggregate invoiced / ordered quantity: {fill_rate:.2f}%" if fill_rate is not None else "- Aggregate invoiced / ordered quantity: unavailable",
        f"- Free quantity: {free_qty:,.2f}" if pd.notna(free_qty) else "- Free quantity: unavailable",
        f"- Free quantity x PTS estimate: INR {foc_estimate:,.2f}" if pd.notna(foc_estimate) else "- Free quantity x PTS estimate: unavailable",
        f"- Exact duplicate rows detected (retained): {duplicate_count:,}",
        "",
        "Blank scheme codes are treated as `No scheme` in distribution tables; they remain visible as missing in the column profile.",
        "The free-quantity valuation is an estimate using free packs multiplied by PTS; it is not booked scheme expenditure.",
        "Aggregate invoiced / ordered is a quantity ratio, not a service-level fill rate unless the business definition agrees.",
        "",
        "## Sales distribution",
        "",
    ]

    for column, title in (
        ("cnf_code", "CFA"),
        ("sku_code", "SKU"),
        ("stockist_code", "Stockist"),
        ("scheme_code", "Scheme"),
    ):
        table = segment_tables.get(column)
        if table is None or table.empty:
            continue
        lines.extend([f"### Top {title} segments by recorded net sales", ""])
        lines.append("| Segment | Sales lines | Net sales (INR) | Sales share |")
        lines.append("|---|---:|---:|---:|")
        for row in table.head(10).itertuples(index=False):
            lines.append(
                f"| {row.segment} | {row.sales_lines:,} | {row.net_sales_inr:,.2f} | {row.net_sales_share_pct:.2f}% |"
            )
        lines.append("")

    lines.extend(["## Data quality", ""])
    if quality.empty:
        lines.append("No missing, invalid, duplicate, or review-flagged values were detected by the checks in this script.")
    else:
        lines.extend(
            [
                f"- {len(quality):,} issue categories/fields flagged; affected-row counts can overlap.",
                "- See `data_quality_report.csv` for counts, affected columns, percentages, and review suggestions.",
                f"- Exact duplicate rows found: {duplicate_count:,}; no records were removed.",
            ]
        )
    lines.extend(
        [
            "",
            "## Files and interpretation",
            "",
            "- `column_profile.csv` records source-column cardinality and examples.",
            "- `numeric_descriptive_stats.csv` contains numeric summaries.",
            "- `numeric_outlier_summary.csv` uses the 1.5 x IQR rule; investigate flagged records rather than dropping them.",
            "- `monthly_sales.csv` and `quarterly_sales.csv` show time trends.",
            "- `sales_by_<field>.csv` files contain full segment distributions; charts show leading segments only.",
            "- `unfulfilled_quantity_summary.csv` reports positive ordered-minus-invoiced quantity as a proxy; negative gaps are separately flagged in the quality report.",
            "- Missing identifiers and exact duplicate rows are reported, not silently imputed or deleted.",
            "- Primary sales data alone cannot establish secondary demand, inventory availability, expiry causation, or realized scheme spend.",
            "",
            "## Visualizations",
            "",
        ]
    )
    lines.extend(f"- `visualizations/{name}`" for name in plots)
    (output_dir / "eda_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_eda(input_path: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    frame, quality = load_sales(input_path)
    source_column_count = len(
        [column for column in frame.columns if not column.endswith("_parsed")]
    )
    LOGGER.info(
        "Loaded %s rows and %s source columns", len(frame), source_column_count
    )
    profile_columns(frame).to_csv(output_dir / "column_profile.csv", index=False)
    quality.to_csv(output_dir / "data_quality_report.csv", index=False)

    parsed_numeric_columns = [f"{column}_parsed" for column in NUMERIC_COLUMNS]
    (
        frame[parsed_numeric_columns]
        .describe()
        .rename(columns={f"{column}_parsed": column for column in NUMERIC_COLUMNS})
        .to_csv(output_dir / "numeric_descriptive_stats.csv")
    )
    outlier_rows = []
    for column in parsed_numeric_columns:
        values = frame[column].dropna()
        if values.empty:
            outlier_rows.append(
                {
                    "column": column.removesuffix("_parsed"),
                    "non_null_count": 0,
                    "q1": pd.NA,
                    "q3": pd.NA,
                    "lower_iqr_bound": pd.NA,
                    "upper_iqr_bound": pd.NA,
                    "outlier_count": 0,
                    "outlier_percent": 0.0,
                }
            )
            continue
        q1 = values.quantile(0.25)
        q3 = values.quantile(0.75)
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        outlier_count = int(((values < lower_bound) | (values > upper_bound)).sum())
        outlier_rows.append(
            {
                "column": column.removesuffix("_parsed"),
                "non_null_count": len(values),
                "q1": q1,
                "q3": q3,
                "lower_iqr_bound": lower_bound,
                "upper_iqr_bound": upper_bound,
                "outlier_count": outlier_count,
                "outlier_percent": outlier_count / len(values) * 100,
            }
        )
    pd.DataFrame(outlier_rows).to_csv(
        output_dir / "numeric_outlier_summary.csv", index=False
    )

    dated = frame.dropna(subset=[f"{DATE_COLUMN}_parsed"]).copy()
    dated["month"] = dated[f"{DATE_COLUMN}_parsed"].dt.to_period("M").astype(str)
    dated["quarter"] = dated[f"{DATE_COLUMN}_parsed"].dt.to_period("Q").astype(str)
    for period_column, filename in (
        ("month", "monthly_sales.csv"),
        ("quarter", "quarterly_sales.csv"),
    ):
        period_summary = (
            dated.groupby(period_column)
            .agg(
                sales_lines=("invoice_no", "size"),
                invoices=("invoice_no", "nunique"),
                ordered_qty=("ordered_qty_parsed", "sum"),
                invoiced_qty=("invoiced_qty_parsed", "sum"),
                free_qty=("free_qty_parsed", "sum"),
                net_sales_inr=("net_value_inr_parsed", "sum"),
            )
            .reset_index()
        )
        period_summary["fill_rate_pct"] = (
            period_summary["invoiced_qty"]
            .div(period_summary["ordered_qty"])
            .where(period_summary["ordered_qty"].ne(0))
            * 100
        )
        period_summary.to_csv(output_dir / filename, index=False)

    segment_tables: dict[str, pd.DataFrame] = {}
    for column in SEGMENT_COLUMNS:
        table = summarize_segments(frame, column)
        table.to_csv(output_dir / f"sales_by_{column}.csv", index=False)
        segment_tables[column] = table

    frame["unfulfilled_qty_proxy"] = (
        frame["ordered_qty_parsed"] - frame["invoiced_qty_parsed"]
    ).clip(lower=0)
    frame["foc_value_at_pts_estimate_inr"] = (
        frame["free_qty_parsed"] * frame["pts_inr_parsed"]
    )
    unfulfilled = pd.DataFrame(
        [
            {
                "ordered_qty": frame["ordered_qty_parsed"].sum(),
                "invoiced_qty": frame["invoiced_qty_parsed"].sum(),
                "positive_unfulfilled_qty_proxy": frame["unfulfilled_qty_proxy"].sum(),
                "lines_with_unfulfilled_qty": int(
                    (frame["unfulfilled_qty_proxy"] > 0).sum()
                ),
                "lines_invoiced_above_ordered": int(
                    (
                        frame["invoiced_qty_parsed"]
                        > frame["ordered_qty_parsed"]
                    ).sum()
                ),
            }
        ]
    )
    unfulfilled.to_csv(output_dir / "unfulfilled_quantity_summary.csv", index=False)

    correlation = frame[parsed_numeric_columns].corr()
    correlation.rename(
        columns={f"{column}_parsed": column for column in NUMERIC_COLUMNS},
        index={f"{column}_parsed": column for column in NUMERIC_COLUMNS},
    ).to_csv(output_dir / "numeric_correlation.csv")

    plots = make_plots(frame, output_dir, segment_tables)
    write_report(
        frame,
        quality,
        segment_tables,
        output_dir,
        plots,
        source_column_count,
    )
    LOGGER.info("Wrote EDA outputs to %s", output_dir)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Primary sales CSV (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Directory for EDA outputs (default: {DEFAULT_OUTPUT})",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = parse_args(argv)
    try:
        run_eda(args.input, args.output_dir)
    except (OSError, ValueError, pd.errors.ParserError):
        LOGGER.exception("Primary sales EDA failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
