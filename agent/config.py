"""
Project Sankalp — Policy Configuration
======================================

Structured policy registry extracted from the supplied fictional FDE Academy
training materials. Pfizer Limited is not involved and did not review,
endorse, or supply these documents.

Source files:
  * 02_trade_terms_and_returns_policy.pdf (CO-POL-014 v4.2, 6 pages)
  * 01_company_and_channel_overview.pdf (CE-BRF-2026-07 v1.0, 5 pages)

Page numbers below are the printed page numbers in the source documents.

Usage:
    from config import POLICIES, get_policy, find_policy_references

    policy = get_policy("CO-POL-014")
    refs = find_policy_references("claim valuation")
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

CONFIG_VERSION = "1.0"
PROJECT_NAME = "Project Sankalp"
PAGE_NUMBER_CONVENTION = "Printed page number in source PDF"

SOURCE_DOCUMENTS: Dict[str, Dict[str, Any]] = {
    "CO-POL-014": {
        "document_number": "CO-POL-014",
        "title": "Trade Terms, Schemes and Returns Policy",
        "version": "4.2",
        "owner": "National Sales Manager, Primary Care; co-owned with Commercial Finance",
        "effective_date": "2025-04-01",
        "classification": "Internal",
        "distribution": "Sales, Commercial Finance, Supply Chain, C&F agents (Sections 5 to 7 only)",
        "source_file": "02_trade_terms_and_returns_policy.pdf",
        "total_pages": 6,
        "fictional_training_material": True,
        "clauses": {
            "1": {
                "title": "Purpose and scope",
                "page": 1,
                "details": [
                    "Applies to domestic trade channel, General Medicines portfolio.",
                    "Covers PTS/PTR/MRP ladder and trade margins, credit, trade schemes (bonus and FOC), non-saleable returns (NE, expiry and BED), DPCO 2013 price revisions, and residual shelf life at dispatch.",
                    "Applies to every appointed stockist and every C&F agent handling claims on the company's behalf.",
                    "Institutional business (hospital rate contracts, CGHS/ESIC and state tenders), vaccines, cold-chain SKUs and exports are out of scope.",
                    "Saleable returns (SR) are not accepted under this policy.",
                ],
            },
            "2.1": {
                "title": "MRP and scheduled/non-scheduled formulation pricing",
                "page": 1,
                "values": {
                    "scheduled_formulation_price_ceiling": "NPPA ceiling price plus applicable GST",
                    "scheduled_formulation_regulatory_reference": "DPCO 2013, para 14; NLEM 2022, Schedule I",
                    "non_scheduled_formulation_regulatory_reference": "DPCO 2013, para 20",
                    "new_drug_pricing_para_2_1_u_applies": False,
                },
                "details": [
                    "MRP is printed on every pack and is inclusive of all taxes.",
                    "For scheduled formulations, MRP must not exceed the ceiling price notified by NPPA plus applicable GST.",
                    "Non-scheduled formulations are subject to para 20 of DPCO 2013.",
                    "New-drug pricing under para 2(1)(u) does not apply to this portfolio.",
                ],
            },
            "2.2": {
                "title": "PTR / retail chemist margin",
                "page": 1,
                "values": {
                    "retail_chemist_margin_percent": 20,
                    "calculation_basis": "PTR is worked back from MRP excluding GST",
                },
                "details": ["PTR allows the retail chemist a margin of 20%, worked back from MRP ex-GST."],
            },
            "2.3": {
                "title": "PTS / stockist margin and claim valuation basis",
                "page": 2,
                "values": {
                    "stockist_margin_percent_on_pts": 10,
                    "calculation_basis": "PTS is worked back from PTR",
                    "pts_is_taxable_value_on_tax_invoice": True,
                    "pts_basis_for_foc_returns_cn_pd_claims": True,
                },
                "details": [
                    "PTS allows the stockist a margin of 10% on PTS, worked back from PTR.",
                    "PTS is the taxable value on the tax invoice.",
                    "PTS is the basis on which FOC goods, returns, CN and PD claims are valued throughout this policy.",
                ],
            },
            "2.4": {
                "title": "Price master and manual price controls",
                "page": 2,
                "values": {
                    "price_system": "SAP SD pricing condition records",
                    "manual_billing_price_override_allowed": False,
                    "net_rate_deals_permitted": False,
                    "off_invoice_discounts_permitted": False,
                },
                "details": ["Prices are maintained in SAP SD by Commercial Finance; no manual billing override, net-rate deal or off-invoice discount."],
            },
            "3.1": {
                "title": "Standard credit and cash discount",
                "page": 2,
                "values": {
                    "standard_credit_days_from_invoice": 30,
                    "cash_discount_percent": 1,
                    "cash_discount_payment_within_days": 7,
                    "cash_discount_settlement": "Credit note (CN)",
                    "discount_value_basis": "Taxable value",
                },
            },
            "3.2": {
                "title": "Stockist credit limit",
                "page": 2,
                "values": {
                    "credit_limit_lookback_months": 6,
                    "credit_limit_inputs": ["purchases", "DSO"],
                    "breach_action": "Credit block until payment or one-time RSM release",
                    "maximum_one_time_rsm_release_percent": 20,
                    "post_dated_cheques_accepted": False,
                },
                "details": ["Credit limit is set by Commercial Finance in SAP credit management."],
            },
            "3.3": {
                "title": "Credit note adjustment",
                "page": 2,
                "values": {"adjustment_period": "Month in which CN is issued"},
                "details": ["CNs under Sections 5 and 6 are adjusted against the stockist's outstanding balance in the month issued."],
            },
            "4.1": {
                "title": "Scheme definition",
                "page": 2,
                "values": {
                    "scheme_type": "Quantity-linked bonus offer / FOC on MOQ",
                    "required_circular_fields": ["scheme code", "validity", "SKU list", "terms"],
                    "value_schemes_permitted": False,
                    "net_rate_schemes_permitted": False,
                    "turnover_discounts_permitted": False,
                    "hcp_benefits_governed_by": "UCPMP 2024",
                },
            },
            "4.2": {
                "title": "Types of scheme",
                "page": 2,
                "scheme_types": {
                    "quarter_end_tier_a": {
                        "code_pattern": "QS-FYyyQn-A",
                        "terms": "Free packs on orders of at least 1.5 times the stockist's average monthly purchase",
                        "timing": "Last 7 to 10 days of quarter",
                    },
                    "quarter_end_tier_b": {
                        "code_pattern": "QS-FYyyQn-B",
                        "terms": "As Tier A, on second-tier SKUs, at a lower free ratio",
                        "timing": "Last 7 to 10 days of quarter",
                    },
                    "season_launch": {
                        "code_pattern": "SL-yy-nn",
                        "terms": "Free packs on first orders of the season",
                        "timing": "Before monsoon and winter seasons",
                    },
                    "new_stockist": {
                        "code_pattern": "NS-yy-nn",
                        "terms": "One-time opening order terms",
                        "timing": "On appointment",
                    },
                },
                "details": ["Since 15 November 2024, quarter-end schemes are the only schemes issued for this portfolio."],
            },
            "4.3": {
                "title": "Scheme approval",
                "page": 2,
                "approval_flow": [
                    "Sales proposes scheme",
                    "Commercial Finance checks cost accrual",
                    "National Sales Manager approves",
                    "CFO approval is additionally required for schemes above the Section 4.4 cap",
                ],
            },
            "4.4": {
                "title": "Quarterly scheme cap",
                "page": 2,
                "values": {
                    "maximum_quarterly_free_goods_value_percent_of_portfolio_primary_sales": 3,
                    "valuation_basis": "PTS",
                    "scope": "All schemes in a quarter",
                },
                "formula": "Quarterly FOC value at PTS <= 3% * quarter portfolio primary sales value",
            },
            "4.5": {
                "title": "Stock norms for schemes",
                "page": 3,
                "values": {
                    "maximum_closing_stock_months_of_average_secondary": 2.5,
                    "stock_confirmation_owner": "RSM",
                    "stock_confirmation_source_expected_by_policy": "SSS",
                    "actual_sss_availability_note": "SSS is not received for this portfolio after the DMS pilot was discontinued; RSM confirms through discussion with stockist.",
                },
                "details": ["A scheme must not be offered on an SKU to a stockist whose closing stock exceeds 2.5 months of average secondary for that SKU."],
            },
            "4.6": {
                "title": "Scheme accounting",
                "page": 3,
                "values": {
                    "foc_taxable_value_on_invoice": 0,
                    "foc_sap_item_category": "Free item category",
                    "foc_cost_accrual_basis": "PTS",
                    "accrual_period": "Month of scheme",
                    "reporting": "GTN as trade spend",
                },
            },
            "5.1": {
                "title": "General returns rule",
                "page": 3,
                "values": {
                    "saleable_returns_accepted": False,
                    "accepted_return_categories": ["NE", "expired", "BED"],
                    "return_location": "Only the CFA that billed the stock",
                    "LBE_claim_treatment": "Settled on the same terms as NE",
                },
            },
            "5.2": {
                "title": "Claim types and submission windows",
                "page": 3,
                "claim_windows": {
                    "near_expiry": {
                        "definition": "Stock that will expire within 90 days",
                        "window": "From 90 days before expiry through expiry date",
                        "days_before_expiry": 90,
                        "days_after_expiry": 0,
                    },
                    "expired": {
                        "definition": "Stock past its expiry date",
                        "window": "From expiry date through 90 days after expiry",
                        "days_before_expiry": 0,
                        "days_after_expiry": 90,
                    },
                    "breakage_in_transit": {
                        "definition": "Damage found on receipt",
                        "window_days_from_invoice": 7,
                    },
                    "short_supply": {
                        "definition": "Fewer packs received than invoiced",
                        "window_days_from_invoice": 7,
                    },
                },
                "values": {
                    "claim_more_than_days_after_expiry_rejected": 90,
                    "outside_window_rejected": True,
                },
            },
            "5.3": {
                "title": "Required claim documents and physical stock",
                "page": 3,
                "requirements": [
                    "Claim form signed by stockist listing SKU, batch number, expiry date and quantity for each line.",
                    "Original Pfizer invoice number on which stock was supplied.",
                    "Physical stock sent to the CFA on delivery challan in sealed cartons marked with claim number, with LR copy.",
                ],
            },
            "5.4": {
                "title": "Claims without invoice reference",
                "page": 3,
                "values": {
                    "invoice_reference_mandatory_exception": True,
                    "alternative_verification": "Stockist purchase ledger for that batch",
                    "written_approval_required_from": "Area Manager",
                    "introduced_in_version": "4.2",
                },
            },
            "5.5": {
                "title": "Claim quantity limit",
                "page": 3,
                "values": {
                    "maximum_claim_qty": "Packs of that batch invoiced by Pfizer to that stockist, including free packs",
                },
                "formula": "Claimed quantity <= invoiced quantity for same stockist + batch, including free packs",
            },
            "5.6": {
                "title": "Verification and settlement service levels",
                "page": 4,
                "workflow": [
                    {"step": "Log claim in claims register with claim number", "owner": "C&F agent", "time_limit": "On receipt"},
                    {"step": "Physical verification against claim form", "owner": "C&F agent", "time_limit": "10 working days from receipt"},
                    {"step": "Check earlier claim on same stockist and batch", "owner": "C&F agent", "time_limit": "During verification"},
                    {"step": "Approve and raise credit note", "owner": "Commercial Finance", "time_limit": "30 days from receipt of claim"},
                    {"step": "Destroy stock under witness and record it", "owner": "C&F agent", "time_limit": "Monthly, after credit"},
                ],
                "values": {
                    "physical_verification_working_days": 10,
                    "credit_note_days_from_claim_receipt": 30,
                    "destruction_frequency": "Monthly after credit",
                },
            },
            "5.7": {
                "title": "Value of a claim",
                "page": 4,
                "values": {
                    "claim_valuation_basis": "PTS in force on the date of the claim",
                    "delivery_document": "Delivery challan",
                    "credit_note_reference": "Original supply",
                },
                "critical_note": "This policy clause states claim valuation at PTS in force on claim date. The Company Overview separately says the Project uses current SAP PTS/MRP from SKU master; retain both statements and obtain Finance resolution before valuation logic is finalized.",
            },
            "6.1": {
                "title": "Annual price revisions",
                "page": 4,
                "values": {
                    "scheduled_formulation_revision_date": "1 April annually",
                    "basis": "Annual WPI change notified under DPCO 2013 para 16(2)",
                    "price_list_effective_date": "First billing day of April",
                    "non_scheduled_formulation_limit": "DPCO 2013 para 20",
                },
            },
            "6.2": {
                "title": "Price-decrease credit note",
                "page": 4,
                "values": {
                    "trigger": "MRP revision lowers MRP",
                    "credit_type": "PD credit note",
                    "claim_deadline_days_from_effective_date": 30,
                    "required_evidence": "Batch-wise stock statement",
                },
            },
            "6.3": {
                "title": "Price increase and stock in trade",
                "page": 4,
                "values": {
                    "existing_trade_stock_sold_at": "MRP printed on pack",
                    "company_takes_back_stock_due_to_price_increase": False,
                    "regulatory_affairs_review": "Confirms annually whether relabelling is required and informs Sales by circular",
                },
            },
            "7.1": {
                "title": "Minimum residual shelf life at dispatch",
                "page": 4,
                "values": {
                    "minimum_rsl_percent_of_total_shelf_life_at_invoice": 60,
                    "stockist_may_refuse_below_minimum": True,
                    "cfa_minimum_days_to_expiry_at_dispatch": 60,
                },
            },
            "7.2": {
                "title": "CFA stock below 60 days to expiry",
                "page": 4,
                "values": {
                    "sap_status": "Restricted / blocked stock",
                    "disposition": "Destroyed under Section 5.6",
                    "write_off": "Booked against inventory provision",
                },
            },
            "8.1": {
                "title": "Tax invoice compliance fields",
                "page": 4,
                "required_invoice_fields": ["GSTIN of both parties", "HSN", "batch", "expiry", "MRP", "IRN", "signed QR code", "e-way bill where required"],
            },
            "8.2": {
                "title": "Wholesale drug licence and Schedule H1",
                "page": 4,
                "values": {
                    "required_licence_forms": ["Form 20B", "Form 21B"],
                    "governing_rules": "Drugs Rules, 1945",
                    "sap_billing_block_if_licence_lapsed": True,
                    "schedule_h1_sale_records_responsible_party": "Stockist",
                },
            },
            "8.3": {
                "title": "Permitted recipient of schemes, discounts and credit notes",
                "page": 4,
                "values": {
                    "may_be_offered_to_person_other_than_invoiced_stockist": False,
                },
            },
            "Annexure A": {
                "title": "Margin illustration",
                "page": 5,
                "values": {
                    "illustrative_mrp_inr": 100.00,
                    "illustrative_gst_percent": 12,
                    "mrp_net_of_gst_inr": 89.29,
                    "ptr_inr": 74.40,
                    "pts_inr": 67.64,
                    "calculation": "MRP net of GST = 100 / 1.12; PTR = 89.29 / 1.20; PTS = 74.40 / 1.10",
                },
            },
            "Annexure B": {
                "title": "Scheme circular register FY25-FY27",
                "pages": [5, 6],
                "values": {
                    "circular_validity_start_day": 22,
                    "circular_validity_end": "Last day of quarter-end month",
                    "minimum_order_multiple_of_prior_3_month_average_monthly_sku_purchase": 1.5,
                },
            },
        },
        "revision_history": [
            {"version": "3.0", "date": "2022-04-01", "change": "Consolidated trade terms and returns policy", "page": 1},
            {"version": "4.0", "date": "2024-04-01", "change": "Added Section 4.5 scheme stock norms; claims window narrowed from 180 to 90 days after expiry", "page": 1},
            {"version": "4.1", "date": "2024-11-15", "change": "Section 4.2 quarter-end schemes extended to second-tier SKUs; scheme cap restated", "page": 1},
            {"version": "4.2", "date": "2025-04-01", "change": "Section 5.4 invoice-reference exception with purchase-ledger verification and Area Manager approval", "page": 1},
        ],
    },

    "CE-BRF-2026-07": {
        "document_number": "CE-BRF-2026-07",
        "title": "Company and Domestic Channel Overview",
        "version": "1.0",
        "owner": "Anita Desai, Head, Commercial Excellence",
        "effective_date": "2026-10-20",
        "classification": "Confidential, internal use",
        "distribution": "Project Sankalp team, CFO office",
        "source_file": "01_company_and_channel_overview.pdf",
        "total_pages": 5,
        "fictional_training_material": True,
        "references": {
            "1": {"title": "Purpose", "page": 1, "details": ["Project Sankalp focuses on NE/expiry returns from trade and fill rate to stockists."]},
            "2.1": {
                "title": "GM scope",
                "page": 1,
                "values": {
                    "sku_count": 36,
                    "therapy_areas": 7,
                    "portfolio_scope": "GM (Primary Care), domestic trade channel",
                    "excluded": ["Hospital/institutional", "tenders", "vaccines", "exports"],
                },
            },
            "3": {
                "title": "Distribution model",
                "page": 2,
                "values": {
                    "stockist_count": 156,
                    "cfa_count": 6,
                    "secondary_sales_visibility": "No stockist-level SSS; DMS pilot discontinued in 2023; AWACS is IPM-level only",
                    "cfa_operating_model": "Service model",
                    "cfa_agreement_identifier": "SC-AGR-CF-003",
                    "inventory_ownership_before_invoicing": "Stock remains on company books till invoicing",
                    "returns_policy_reference": "CO-POL-014 Section 5",
                    "claim_settlement": "Credit note against original supply",
                },
            },
            "3.1": {
                "title": "Regulatory frame",
                "page": 2,
                "references": [
                    "DPCO 2013: paras 14, 16, 20",
                    "NLEM 2022",
                    "NPPA annual WPI notification, March 2026",
                    "Drugs and Cosmetics Act, 1940",
                    "Drugs Rules, 1945: Forms 20B/21B, Rule 65, Schedule H1",
                    "CDSCO Good Distribution Practices guidance",
                    "Company standard WS-02",
                    "UCPMP 2024",
                ],
            },
            "3.2": {"title": "CFA locations and territories", "page": 2},
            "4": {
                "title": "Named functional owners",
                "page": 2,
                "owners": {
                    "Finance / Sponsor": "Rohan Mehta, CFO",
                    "Commercial Finance / Controller": "Neha Bansal",
                    "Sales / Primary Care / NSM": "Arjun Sethi",
                    "Supply Chain / Head SC": "Kavita Rao",
                    "Demand Planning / Lead": "Vaishali Kapoor",
                    "Distribution / East / RDM East": "Subhajit Banerjee",
                    "Commercial Excellence / Project Sankalp lead": "Anita Desai",
                },
            },
            "5": {
                "title": "Source systems and extracts",
                "page": 3,
                "period": "2024-04-01 to 2026-09-30, unless otherwise stated",
                "systems": {
                    "ERP SAP SD/MM/FI": "Sales orders, billing documents, CN, batch master, stock by plant and storage location; real-time",
                    "CFA WMS": "Bins, pick and putaway; CFA-owned, no Pfizer access",
                    "Claims register": "NE/expiry, BED, short-supply claims; Excel consolidated monthly; CN posted in SAP FI and reported to IRP",
                    "Planning workbook": "National forecast, allocation shares, scheme overlays; monthly",
                    "Scheme circulars": "QS and festive schemes; PDF issued by Sales Ops",
                    "Field calls": "Voice notes and call recordings; ad hoc",
                },
                "data_extracts": {
                    "sku_master.csv": {"section": "5.1", "page": 3, "grain": "One row per SKU", "fields": ["sku_code", "product_description", "pack", "therapy_area", "shelf_life_months", "storage", "nlem_scheduled", "pts_inr", "mrp_inr"], "price_note": "Current SAP price master values; overview says use these PTS/MRP values for Project Sankalp; do not substitute published ceiling prices or third-party price lists."},
                    "batch_master.csv": {"section": "5.2", "page": 3, "grain": "One row per batch", "fields": ["batch_no", "sku_code", "mfg_site", "mfg_date", "expiry_date", "batch_qty_packs"], "coverage_note": "Batches manufactured from Oct 2023; earlier batches archived at ERP migration."},
                    "stockist_master.csv": {"section": "5.3", "page": 3, "fields": ["stockist_code", "stockist_name", "cnf_code", "city", "state", "appointed_on", "drug_licence_no", "gstin"], "coverage_note": "appointed_on not migrated for stockists active before Apr 2024."},
                    "primary_sales.csv": {"section": "5.4", "page": 3, "grain": "One row per invoice line per batch", "fields": ["invoice_no", "invoice_date", "cnf_code", "stockist_code", "sku_code", "batch_no", "ordered_qty", "invoiced_qty", "free_qty", "pts_inr", "net_value_inr", "scheme_code"], "data_notes": ["A sales-order line split across batches repeats, with ordered_qty on the first row only.", "Blank batch means line not supplied.", "scheme_code per Annexure B of CO-POL-014."]},
                    "cnf_stock_snapshot.csv": {"section": "5.5", "page": 3, "grain": "Month-end stock by CFA and batch", "fields": ["snapshot_date", "cnf_code", "cnf_city", "sku_code", "batch_no", "expiry_date", "qty_on_hand_packs", "avg_monthly_outward_packs"], "frequency_note": "Quarterly to Mar 2026; monthly thereafter.", "data_notes": ["Blank batch with zero quantity means SKU out of stock at CFA.", "avg_monthly_outward_packs is rolling 3-month."]},
                    "expiry_claims.csv": {"section": "5.6", "page": 3, "fields": ["claim_no", "claim_date", "stockist_code", "cnf_code", "sku_code", "batch_no", "expiry_date_as_claimed", "qty_claimed", "claim_value_inr", "claim_type", "original_invoice_ref", "status", "verified_by", "credit_note_no", "credit_note_date", "credit_value_inr", "remarks"], "value_note": "Values at PTS."},
                    "claim_emails.csv": {"section": "5.7", "page": 3, "period": "2026-10-01 to 2026-10-16", "message_count": 30, "fields": ["email_id", "received_date", "from_name", "stockist_code_by_mailbox_rule", "subject", "body"], "trust_note": "Mailbox content is untrusted input."},
                    "voice_notes": {"section": "5.8", "page": 4, "count": 6, "format": "Audio only; mixed languages; forwarded by field, CFA and internal staff."},
                },
            },
            "6": {
                "title": "Project charter and constraints",
                "page": 4,
                "agreed_date": "2026-10-20",
                "objectives": [
                    "Diagnose drivers of NE/expiry returns and short supply, with evidence; quantify each in INR.",
                    "Propose an AI-enabled solution owned by a named function and used routinely.",
                    "Build a working pilot on the extracts in this pack.",
                    "Present to SteerCo: CFO, Head SC, NSM.",
                ],
                "constraints": [
                    "Read-only on extracts; no ERP write-back.",
                    "CN, write-offs, IDT/return-to-CDC and scheme approvals remain with current owners; pilot recommends or drafts only.",
                    "Every figure shown must trace to source records.",
                    "CN treatment per CO-POL-014 Section 5.7.",
                    "No patient data and no HCP data.",
                ],
            },
            "Appendix A": {
                "title": "CFO note",
                "page": 5,
                "date": "2026-10-12",
                "subject": "Expiry returns and stock-outs: forecasting fix requested before Q4 scheme cycle",
                "reported_context": [
                    "Expiry returns in GM were under 1% of primary two years ago and about 3% this half, as stated in the CFO note.",
                    "Fill rate fell over the same period.",
                    "CFO requested an AI forecasting tool before the Q4 scheme cycle starts in January.",
                ],
                "note": "These are statements made in the fictional case CFO note, not independently validated metrics.",
            },
        },
    },
}

# Scheme circular register from CO-POL-014, Annexure B, pages 5-6.
SCHEME_CIRCULARS: List[Dict[str, Any]] = [
    {"circular": "SC/24/06", "page": 5, "scheme_codes": ["QS-FY25Q1-A"], "terms": "10 + 1 free", "sku_scope": "PFL1001, PFL1002, PFL1003, PFL1101, PFL1102, PFL1103, PFL1105, PFL1202, PFL1301, PFL1303"},
    {"circular": "SC/24/09", "page": 5, "scheme_codes": ["QS-FY25Q2-A"], "terms": "10 + 1 free", "sku_scope": "As QS-FY25Q1-A"},
    {"circular": "SC/24/12", "page": 5, "scheme_codes": ["QS-FY25Q3-A"], "terms": "10 + 2 free", "sku_scope": "As QS-FY25Q1-A"},
    {"circular": "SC/24/12", "page": 5, "scheme_codes": ["QS-FY25Q3-B"], "terms": "10 + 1 free", "sku_scope": "PFL1004, PFL1104, PFL1201, PFL1302, PFL1401"},
    {"circular": "SC/25/03", "page": 5, "scheme_codes": ["QS-FY25Q4-A"], "terms": "10 + 2 free", "sku_scope": "As QS-FY25Q3-A"},
    {"circular": "SC/25/03", "page": 5, "scheme_codes": ["QS-FY25Q4-B"], "terms": "10 + 1 free", "sku_scope": "As QS-FY25Q3-B"},
    {"circular": "SC/25/06", "page": 5, "scheme_codes": ["QS-FY26Q1-A"], "terms": "10 + 2 free", "sku_scope": "As QS-FY25Q3-A"},
    {"circular": "SC/25/06", "page": 5, "scheme_codes": ["QS-FY26Q1-B"], "terms": "10 + 1 free", "sku_scope": "As QS-FY25Q3-B"},
    {"circular": "SC/25/09", "page": 5, "scheme_codes": ["QS-FY26Q2-A"], "terms": "10 + 2 free", "sku_scope": "As QS-FY25Q3-A"},
    {"circular": "SC/25/09", "page": 5, "scheme_codes": ["QS-FY26Q2-B"], "terms": "10 + 1 free", "sku_scope": "As QS-FY25Q3-B"},
    {"circular": "SC/25/12", "page": 5, "scheme_codes": ["QS-FY26Q3-A"], "terms": "10 + 2 free", "sku_scope": "As QS-FY25Q3-A"},
    {"circular": "SC/25/12", "page": 5, "scheme_codes": ["QS-FY26Q3-B"], "terms": "10 + 1 free", "sku_scope": "As QS-FY25Q3-B"},
    {"circular": "SC/26/03", "page": 5, "scheme_codes": ["QS-FY26Q4-A"], "terms": "10 + 2 free", "sku_scope": "As QS-FY25Q3-A"},
    {"circular": "SC/26/03", "page": 6, "scheme_codes": ["QS-FY26Q4-B"], "terms": "10 + 1 free", "sku_scope": "As QS-FY25Q3-B"},
    {"circular": "SC/26/06", "page": 6, "scheme_codes": ["QS-FY27Q1-A"], "terms": "10 + 2 free", "sku_scope": "As QS-FY25Q3-A"},
    {"circular": "SC/26/06", "page": 6, "scheme_codes": ["QS-FY27Q1-B"], "terms": "10 + 1 free", "sku_scope": "As QS-FY25Q3-B"},
    {"circular": "SC/26/09", "page": 6, "scheme_codes": ["QS-FY27Q2-A"], "terms": "10 + 2 free", "sku_scope": "As QS-FY25Q3-A"},
    {"circular": "SC/26/09", "page": 6, "scheme_codes": ["QS-FY27Q2-B"], "terms": "10 + 1 free", "sku_scope": "As QS-FY25Q3-B"},
]

# Identifiers mentioned in the supplied pack whose full governing documents
# were not supplied. Do not infer the missing policy contents.
REFERENCED_BUT_NOT_SUPPLIED: Dict[str, Dict[str, Any]] = {
    "SC-AGR-CF-003": {
        "description": "CFA service agreement identifier",
        "source_document": "CE-BRF-2026-07",
        "page": 2,
        "section": "3",
        "known_context": "CFA operates on a service model; stock remains on company books till invoicing.",
        "full_document_supplied": False,
    },
    "WS-02": {
        "description": "Company distribution-practice standard",
        "source_document": "CE-BRF-2026-07",
        "page": 2,
        "section": "3.1",
        "known_context": "Listed as the company distribution-practice standard.",
        "full_document_supplied": False,
    },
}

EXTERNAL_REGULATORY_REFERENCES: Dict[str, Dict[str, Any]] = {
    "DPCO 2013": {
        "provisions": ["para 14", "para 16(2)", "para 20"],
        "references": [
            {"document": "CO-POL-014", "pages": [1, 4], "sections": ["2.1", "6.1"]},
            {"document": "CE-BRF-2026-07", "pages": [2], "sections": ["3.1"]},
        ],
    },
    "NLEM 2022": {
        "references": [
            {"document": "CO-POL-014", "pages": [1], "sections": ["2.1"]},
            {"document": "CE-BRF-2026-07", "pages": [2], "sections": ["3.1"]},
        ],
    },
    "NPPA annual WPI notification, March 2026": {
        "references": [
            {"document": "CE-BRF-2026-07", "pages": [2], "sections": ["3.1"]},
            {"document": "CO-POL-014", "pages": [4], "sections": ["6.1"]},
        ],
    },
    "Drugs and Cosmetics Act, 1940": {
        "references": [{"document": "CE-BRF-2026-07", "pages": [2], "sections": ["3.1"]}],
    },
    "Drugs Rules, 1945": {
        "references": [
            {"document": "CE-BRF-2026-07", "pages": [2], "sections": ["3.1"]},
            {"document": "CO-POL-014", "pages": [4], "sections": ["8.2"]},
        ],
        "provisions": ["Forms 20B and 21B", "Rule 65", "Schedule H1"],
    },
    "CDSCO Good Distribution Practices guidance": {
        "references": [{"document": "CE-BRF-2026-07", "pages": [2], "sections": ["3.1"]}],
    },
    "UCPMP 2024": {
        "references": [
            {"document": "CO-POL-014", "pages": [2], "sections": ["4.1"]},
            {"document": "CE-BRF-2026-07", "pages": [2], "sections": ["3.1"]},
        ],
    },
}

# High-importance cross-document issue. This is intentionally not resolved
# in code because the supplied documents state different valuation bases.
POLICY_CONFLICTS: List[Dict[str, Any]] = [
    {
        "topic": "PTS valuation basis for Project Sankalp claim analysis",
        "policy_statement": {
            "document": "CO-POL-014",
            "section": "5.7",
            "page": 4,
            "value": "PTS in force on the date of the claim",
        },
        "overview_statement": {
            "document": "CE-BRF-2026-07",
            "section": "5.1",
            "page": 3,
            "value": "Use current SAP PTS and MRP values from sku_master.csv for Project Sankalp valuation",
        },
        "required_action": "Preserve both source statements and obtain Commercial Finance confirmation before choosing the valuation rule.",
        "owner_to_confirm": "Neha Bansal, Commercial Finance / Controller",
    }
]

# Quick access index for agent retrieval, validation, and citation generation.
POLICY_REFERENCE_INDEX: List[Dict[str, Any]] = [
    {"topic": "MRP ceiling and pricing", "document": "CO-POL-014", "section": "2.1", "pages": [1]},
    {"topic": "PTR retail margin 20%", "document": "CO-POL-014", "section": "2.2", "pages": [1]},
    {"topic": "PTS stockist margin 10%", "document": "CO-POL-014", "section": "2.3", "pages": [2]},
    {"topic": "Credit 30 days; cash discount 1% within 7 days", "document": "CO-POL-014", "section": "3.1", "pages": [2]},
    {"topic": "Credit limit and one-time release up to 20%", "document": "CO-POL-014", "section": "3.2", "pages": [2]},
    {"topic": "Quarter-end scheme MOQ 1.5x", "document": "CO-POL-014", "section": "4.2", "pages": [2]},
    {"topic": "Quarterly FOC cap 3% of primary sales at PTS", "document": "CO-POL-014", "section": "4.4", "pages": [2]},
    {"topic": "Scheme stock norm 2.5 months average secondary", "document": "CO-POL-014", "section": "4.5", "pages": [3]},
    {"topic": "NE and expired claim windows", "document": "CO-POL-014", "section": "5.2", "pages": [3]},
    {"topic": "Breakage and short-supply claim window 7 days", "document": "CO-POL-014", "section": "5.2", "pages": [3]},
    {"topic": "Claim quantity capped at invoiced batch quantity including free packs", "document": "CO-POL-014", "section": "5.5", "pages": [3]},
    {"topic": "Physical verification within 10 working days", "document": "CO-POL-014", "section": "5.6", "pages": [4]},
    {"topic": "Credit note within 30 days of claim receipt", "document": "CO-POL-014", "section": "5.6", "pages": [4]},
    {"topic": "Claim valuation at PTS on claim date", "document": "CO-POL-014", "section": "5.7", "pages": [4]},
    {"topic": "Price decrease PD claim within 30 days", "document": "CO-POL-014", "section": "6.2", "pages": [4]},
    {"topic": "Minimum RSL 60%; CFA no dispatch under 60 days to expiry", "document": "CO-POL-014", "section": "7.1", "pages": [4]},
    {"topic": "Project read-only / no ERP write-back", "document": "CE-BRF-2026-07", "section": "6", "pages": [4]},
]


def get_policy(document_number: str) -> Dict[str, Any]:
    """Return a source document's complete policy/configuration record."""
    key = document_number.strip().upper()
    if key not in SOURCE_DOCUMENTS:
        raise KeyError(f"Unknown document number: {document_number}")
    return SOURCE_DOCUMENTS[key]


def get_clause(document_number: str, section: str) -> Dict[str, Any]:
    """Return a clause from CO-POL-014 or a reference from CE-BRF-2026-07."""
    doc = get_policy(document_number)
    collection = doc.get("clauses", doc.get("references", {}))
    if section not in collection:
        raise KeyError(f"Section {section!r} not found in {document_number}")
    return collection[section]


def find_policy_references(keyword: str) -> List[Dict[str, Any]]:
    """Search the quick reference index by keyword and return page citations."""
    term = keyword.casefold().strip()
    return [
        item for item in POLICY_REFERENCE_INDEX
        if term in item["topic"].casefold()
    ]


def format_citation(document_number: str, section: str, page: Optional[int] = None) -> str:
    """Build a compact source citation string."""
    doc = get_policy(document_number)
    if page is None:
        collection = doc.get("clauses", doc.get("references", {}))
        item = collection[section]
        page_value = item.get("page", item.get("pages"))
    else:
        page_value = page
    if isinstance(page_value, list):
        page_text = ", ".join(str(p) for p in page_value)
    else:
        page_text = str(page_value)
    return f'{document_number} v{doc["version"]}, §{section}, p.{page_text}'


# Alias useful for agent code that expects a generic CONFIG object.
CONFIG = {
    "config_version": CONFIG_VERSION,
    "project": PROJECT_NAME,
    "source_documents": SOURCE_DOCUMENTS,
    "scheme_circulars": SCHEME_CIRCULARS,
    "referenced_but_not_supplied": REFERENCED_BUT_NOT_SUPPLIED,
    "external_regulatory_references": EXTERNAL_REGULATORY_REFERENCES,
    "policy_conflicts": POLICY_CONFLICTS,
    "policy_reference_index": POLICY_REFERENCE_INDEX,
}
