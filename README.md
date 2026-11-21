# Project Sankalp: expiry returns and short supply

A pilot for the domestic General Medicines trade channel (fictional teaching case; Pfizer Limited is not involved). It checks stockist claims against CO-POL-014, and shows how quarter-end schemes, stock placement and unchecked claims drive expiry returns.

The CFO asked for a demand-forecasting tool. The data shows the money is lost at three control points instead: the quarter-end scheme decision, the allocation of stock between C&Fs, and the approval of claims. The pilot puts a check at each.

| Finding | Figure | Source |
|---|---|---|
| Expiry claims, % of primary | 0.60% (Q2 FY25) → 3.27% (Q2 FY27) | `agent/business_insights.py` |
| Expiry-claim value on scheme-bought batches, last 12 months | 91.3% (51.4% pack-weighted) | `agent/Discovery/expiry_attribution.py` |
| Credit notes the policy rules reject, last 12 months | ₹67.9 lakh | claim checker |
| Kolkata lines shipped while an older batch was in stock | 81% vs 27–34% elsewhere | `agent/graph_schema.py` |

## Quick start

From the repository root, on Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

Only **1. Claim check** calls a model. It needs an OpenRouter key in `.env` at the repo root:

```
OPENROUTE_API_KEY=<your key>
```

Never commit `.env`; `.gitignore` excludes it.

## The app: four screens

| Screen | Runs | Who uses it | What it does |
|---|---|---|---|
| 1. Claim check | `agent/run_claim_check.py` → `agent/graph_validate.py` | Claims executives | Reads a stockist's claim message (gpt-4o-mini picks the claim type; regex pulls batch, invoice, expiry, quantity), routes it and checks the §5.2 claim window |
| 2. Generate claim report | `agent/graph_schema.py [--since] [--fefo-from]` | NSM, RSMs, Head SC | Six analyses in parallel: claims vs free goods by quarter, scheme link, tier rates, FEFO by C&F, settlement, circular compliance |
| 3. Generate insight | `python -m agent.Discovery.expiry_attribution [--since]` | CFO, NSM | Step by step, how much expiry-claim value is linked to quarter-end schemes |
| 4. Validate claim | `agent/claim_validate.py --claim-no CLM-YYMM-NNNNN` | Controller | One register claim against 8 CO-POL-014 rules: approve, reject or refer to a person, with the clause and CSV rows for each rule |

Each script also runs on its own from the command line, for example:

```powershell
cd agent
python claim_validate.py --claim-no CLM-2605-04488
python graph_schema.py --since 2025-10-01 --fefo-from 2026-04-01
cd ..
python -m agent.Discovery.expiry_attribution --since 2025-10-01
python -m agent.business_insights
```

## Repository layout

```
app.py                       Streamlit app: the four screens; runs each script as a subprocess
agent/
  graph_validate.py          LangGraph: read_review (model + regex) -> triage -> claim-type node -> END
  run_claim_check.py         Runs graph_validate's graph on one query from the form; prints a JSON result
  claim_validate.py          LangGraph: load_claim -> triage -> claim-type node (8 rules) -> decide -> END
  graph_schema.py            LangGraph: validate_data -> 6 analyses in parallel -> build_report
  Discovery/expiry_attribution.py   Plain script: scheme link (A1-A9) and tiers (B1-B4)
  business_insights.py       Reproducible quarterly figures used in the discovery note
  rules.py                   triage, to_date, check_claim_window (§5.2)
  config.py                  CO-POL-014 clauses and values, CE-BRF data dictionary, citations
  data.py                    Loads and cleans the 7 CSV extracts
  llm.py                     OpenRouter client (gpt-4o-mini)
  state.py                   Graph state types
data/                        The 7 CSV extracts (read-only)
tests/                       pytest suite: one file per module, a test for every rule
```

## Data

Seven extracts from the client's systems, 01 Apr 2024 – 30 Sep 2026: `primary_sales`, `expiry_claims`, `batch_master`, `sku_master`, `stockist_master`, `cnf_stock_snapshot`, `claim_emails`. They are read-only, and nothing is written back to SAP.

The cleaning handles the known faults:
- three date formats;
- codes written inconsistently (`stk0039`, `PFL-1301`, `CFN01`);
- numbers stored with commas;
- the `+` SKU code (it is PFL1001);
- 745 repeated sales rows and 23 repeated claims;
- `ordered_qty` repeated on the lines of a split order.

## Rules and where they come from

| Rule | Policy | Code |
|---|---|---|
| Near expiry: 90 days before expiry up to expiry; expired: up to 90 days after | CO-POL-014 §5.2 | `rules.check_claim_window`, `claim_validate.rule_window_expiry` |
| Breakage / short supply: within 7 days of the invoice | §5.2 | `rules.check_claim_window`, `claim_validate.rule_window_invoice` |
| Batch exists, belongs to the SKU; claimed expiry matches | §5.3 | `rule_batch`, `rule_expiry_matches` |
| Original invoice quoted, billed to this stockist, carried this batch; no reference needs written Area Manager approval | §5.3–5.4 | `rule_invoice_ref` |
| Packs claimed ≤ packs invoiced to the stockist, free included | §5.5 | `rule_quantity` |
| Same stockist + batch + quantity claimed before = duplicate | §5.6 | `rule_duplicate` |
| Claim value = quantity × PTS | §2.3, §5.7 | `rule_value` |
| Returned only to the C&F that billed the stock | §5.1 | `rule_billing_cfa` |
| Free goods ≤ 3% of the quarter's primary sales | §4.4 | `graph_schema.quarterly_claims_foc` |
| Scheme only on circular SKUs, 22nd to month end, at the circular's free ratio | §4.2, Annexure B | `graph_schema.scheme_compliance` |
| Shelf life at dispatch ≥ 60% | §7.1 | `graph_schema.fefo_dispatch` |
| Credit note within 30 days of the claim | §5.6 | `graph_schema.settlement`, `claim_validate.info_settlement` |

Decision in `claim_validate`: any failed rule → **REJECT**; otherwise any rule that couldn't be checked → **NEEDS_PERSON**; otherwise **APPROVE**. The pilot recommends; credit notes stay with Commercial Finance.

## Tests

```powershell
pytest
```

The suite has 174 tests in `tests/`, one file per module. They make no model or network calls, and take about 16 seconds.

| File | Covers | Tests |
|---|---|---|
| `test_rules.py` | triage, claim pre-check, `to_date`, the §5.2 window and its boundaries | 56 |
| `test_claim_validate.py` | each of the 8 rules (pass, fail, unknown), routing, the decision, a 10-claim check set agreed by hand | 68 |
| `test_graph_schema.py` | scheme register, policy values, cap, tiers, FEFO, settlement, circular compliance, the graph | 26 |
| `test_run_claim_check.py` | route mapping, reading the window result, error hints | 12 |
| `test_expiry_attribution.py` | 91.3%, 51.4%, claim rates, Tier A 82.1% | 9 |
| `test_business_insights.py` | date, number and code cleaning | 3 |

`tests/conftest.py` puts `agent/` on the path and sets a placeholder `OPENROUTE_API_KEY` when none is set, because `rules.py` imports `llm.py`.

## Cost per run

Only the claim check calls a model: one gpt-4o-mini call of about 300 input and 20 output tokens. At $0.15 / $0.60 per million tokens and ₹94 per US$, that is about ₹0.005 a check, or about ₹21 a year for 4,000 claims. The other screens make no model calls.

## Known gaps

- `graph_validate.py` draws `graph.png` through mermaid.ink when it is imported, so the claim check fails offline. Wrap it in try/except, as `claim_validate.py --draw` does.
- `rules.CLAIM_WINDOWS` holds its own §5.2 values instead of reading `config.py`; the values are the same today.
- `data.py` calls `drop_duplicates()` without keeping the result; each script de-duplicates for itself.
- The FEFO figure is a proxy from month-end stock, not a WMS pick log.
- The six voice notes are not transcribed yet. The app is not yet deployed to a live URL.
