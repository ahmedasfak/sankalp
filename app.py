"""Project Sankalp: Streamlit front end.

    1. Claim check       -> runs agent/graph_validate.py (via agent/run_claim_check.py) on the customer's query
    2. Generate claim report -> runs agent/graph_schema.py [--since YYYY-MM-DD] [--fefo-from YYYY-MM-DD]
    3. Generate insight  -> runs python -m agent.Discovery.expiry_attribution [--since YYYY-MM-DD]  (from the repo root)
    4. Validate claim    -> runs agent/claim_validate.py --claim-no CLM-YYMM-NNNNN on one register claim

Both graphs run as scripts in a subprocess, exactly as from a terminal.
Start from the repository root (the folder that holds agent/ and data/):

    pip install streamlit
    streamlit run app.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
AGENT = ROOT / "agent"
RESULT_MARKER = "@@SANKALP_RESULT@@"
DEFAULT_SINCE, DEFAULT_FEFO_FROM = date(2025, 10, 1), date(2026, 4, 1)      # same as graph_schema.py
DATA_FROM, DATA_TO = date(2024, 4, 1), date(2026, 9, 30)                     # extract period

PATTERNS = {   # the formats graph_validate.py's readers recognise
    "stockist": (r"^STK\d{4}$", "STK + 4 digits, e.g. STK0047"),
    "invoice": (r"^INV/[A-Z0-9]{3}/\d{4}/\d{6}$", "INV/<C&F>/<YYMM>/<6 digits>, e.g. INV/N02/2505/036911"),
    "batch": (r"^[A-Z][0-9]{7}$", "1 letter + 7 digits, e.g. L2420268"),
}
CLAIM_TYPES = {"Near expiry (expires within 90 days)": "Near expiry stock, return requested.",
               "Expired": "Expired stock, return requested.",
               "Breakage in transit (within 7 days of invoice)": "Received damaged / broken.",
               "Short supply (within 7 days of invoice)": "Short supply: fewer packs received than invoiced."}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

st.set_page_config(page_title="Project Sankalp", layout="wide")

# Screen name -> one-line description shown under the screen's header
TABS = {
    "1. Claim check": "Check a new stockist claim message: the model reads it and the claim window is tested.",
    "2. Generate claim report": "Scheme and expiry-claim report: claims vs free goods, tiers, FEFO by C&F, settlement, circulars.",
    "3. Generate insight": "Generate insight from the inputs dataset.",
    "4. Validate claim": "Validate one claim from the register against the CO-POL-014 rules and get approve, reject or refer.",
}


def page_header(title: str):
    st.header(title)
    st.markdown(f"**{TABS[title]}**")


# ----------------------------------------------------------------------------- helpers
def run_script(args: list[str], timeout: int = 300, cwd: Path = AGENT) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    return subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=timeout)


def to_frame(lines: list[str]) -> pd.DataFrame:
    """Turn graph_schema.py's text table (header | ... , -+- rule, rows) into a DataFrame."""
    rows = [[c.strip() for c in ln.split(" | ")] for ln in lines if ln.strip() and "-+-" not in ln]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows[1:], columns=rows[0])
    for col in df.columns:
        num = pd.to_numeric(df[col].str.replace(",", "", regex=False), errors="coerce")
        if num.notna().sum() == df[col].ne("").sum() and len(df):
            df[col] = num
    return df


def parse_report(text: str) -> dict:
    """Split the printed report into data checks and sections (title, finding, tables, sources)."""
    checks, sections = [], []
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        lines = block.splitlines()
        title, body = lines[0].strip(), lines[1:]
        if title == "Data checks":
            checks = [ln[2:] for ln in body if ln.startswith("- ")]
            continue
        sec = {"title": title, "finding": "", "tables": {}, "sources": ""}
        i = 0
        while i < len(body):
            ln = body[i]
            m = re.match(r"^\[(\w+)\]$", ln.strip())
            if m:
                j = i + 1
                while j < len(body) and body[j].strip():
                    j += 1
                sec["tables"][m.group(1)] = to_frame(body[i + 1:j])
                i = j
                continue
            if ln.startswith("Sources:"):
                sec["sources"] = ln[len("Sources:"):].strip()
            elif ln.strip() and not sec["finding"]:
                sec["finding"] = ln.strip()
            i += 1
        sections.append(sec)
    return {"checks": checks, "sections": sections}


def chart_for(title: str, name: str, df: pd.DataFrame):
    """A chart where the table has an obvious one; the table itself is always shown too."""
    if df.empty:
        return
    t = title.lower()
    if name == "by_quarter" and "fq" in df and "ne_claims_pct" in df:
        st.caption("Expiry claims and free goods, % of primary sales (dashed policy cap: 3%)")
        st.line_chart(df.set_index("fq")[["ne_claims_pct", "foc_pct"]].assign(cap_pct=3.0))
    elif name == "by_tier" and "claims_pct_of_sales" in df:
        st.caption("Expiry claims as % of sales, by scheme tier")
        st.bar_chart(df.set_index(df.columns[0])["claims_pct_of_sales"], horizontal=True)
    elif name == "by_cfa" and "non_fefo_pct_proxy" in df:
        st.caption("Lines shipped while an older batch was in stock (FEFO proxy), % by C&F")
        st.bar_chart(df.set_index("cnf_code")["non_fefo_pct_proxy"])
    elif name == "by_link" and "share_pct" in df and "scheme" in t:
        recent = df[df.period.str.startswith("Since")]
        if len(recent):
            st.caption(f"Share of expiry-claim value, {recent.period.iloc[0].lower()}")
            st.bar_chart(recent.set_index("link")["share_pct"], horizontal=True)


# ----------------------------------------------------------------------------- page: claim check
def claim_check_page():
    page_header("1. Claim check")
    st.caption("Runs `agent/graph_validate.py` on the query below. The model reads the message, the graph routes it "
               "by claim type, and the claim node checks the claim window from CO-POL-014 §5.2.")

    with st.expander("Formats the claim check understands", expanded=True):
        st.markdown(
            "| Field | Format | Example |\n|---|---|---|\n"
            "| Stockist code | `STK` + 4 digits | `STK0047` |\n"
            "| Invoice number | `INV/<C&F>/<YYMM>/<6 digits>` | `INV/N02/2505/036911` |\n"
            "| Batch number | 1 letter + 7 digits (digit 0, not letter O) | `L2420268` |\n"
            "| Expiry on pack | Month + year | `Oct-2026` |\n"
            "| Quantity | number + unit: strips, boxes, packs, bottles or tubes | `43 boxes` |\n"
            "| Claim received date | **DD-MM-YYYY** (filled from the date picker) | `18-11-2026` |")
        st.caption("The invoice and batch must be the pair on the original Pfizer invoice: the check looks them up "
                   "in primary_sales.csv and batch_master.csv.")

    with st.form("claim"):
        c1, c2, c3 = st.columns(3)
        stockist = c1.text_input("Stockist code", placeholder="STK0047")
        invoice = c2.text_input("Invoice number", placeholder="INV/N02/2505/036911")
        batch = c3.text_input("Batch number", placeholder="L2420268")
        c4, c5, c6 = st.columns(3)
        sku = c4.text_input("Product / SKU code", placeholder="Aceclo-PCM or PFL1202")
        qty = c5.number_input("Quantity", min_value=1, step=1, value=1)
        unit = c6.selectbox("Unit", ["strips", "boxes", "packs", "bottles", "tubes"])
        c7, c8, c9 = st.columns(3)
        exp_m = c7.selectbox("Expiry month (on pack)", MONTHS, index=9)
        exp_y = c8.number_input("Expiry year", min_value=2024, max_value=2030, value=2026, step=1)
        received = c9.date_input("Claim received date", value=date.today(), format="DD/MM/YYYY")
        c10, c11 = st.columns([1, 2])
        claim_type = c10.selectbox("What is the claim?", list(CLAIM_TYPES))
        sender = c11.text_input("Sender name", placeholder="Shree Pharma")
        note = st.text_area("Message / note from the customer (optional)",
                            placeholder="e.g. Goods are packed and ready at our godown.")
        submitted = st.form_submit_button("Run claim check", type="primary")

    if not submitted:
        return

    values = {"stockist": stockist.strip().upper(), "invoice": invoice.strip().upper(), "batch": batch.strip().upper()}
    problems = [f"**{k.title()}** `{v or '(empty)'}`: expected {PATTERNS[k][1]}"
                for k, v in values.items() if not re.match(PATTERNS[k][0], v)]
    if problems:
        st.warning("These fields do not match the expected format, so the graph may not find them:\n\n- "
                   + "\n- ".join(problems))

    body = (f"{sku or 'Product'}, batch {values['batch']}, exp {exp_m}-{exp_y}, {qty} {unit}, "
            f"invoice {values['invoice']}. {CLAIM_TYPES[claim_type]} {note.strip()}").strip()
    received_txt = received.strftime("%d-%m-%Y")
    args = ["run_claim_check.py", "--body", body, "--stockist", values["stockist"], "--received-date", received_txt,
            "--from-name", sender, "--subject", claim_type.split(" (")[0]]
    st.markdown("**Message sent to the graph**")
    st.code(body, language=None)

    with st.spinner("Running graph_validate.py ..."):
        try:
            proc = run_script(args, timeout=180)
        except subprocess.TimeoutExpired:
            st.error("graph_validate.py did not finish within 3 minutes (the model call may be stuck).")
            return
    show_claim_result(proc)


def show_claim_result(proc: subprocess.CompletedProcess):
    line = next((ln for ln in reversed(proc.stdout.splitlines()) if ln.startswith(RESULT_MARKER)), None)
    if line is None:
        st.error("graph_validate.py stopped before returning a result.")
        st.code((proc.stdout + "\n" + proc.stderr)[-4000:], language=None)
        return
    res = json.loads(line[len(RESULT_MARKER):])

    st.subheader("Result")
    ex = res.get("extracted") or {}
    st.markdown("**What the graph read from the message**")
    st.dataframe(pd.DataFrame([{
        "Claim type (model)": ex.get("analysis"), "Batch": ex.get("batch_no"), "Invoice": ex.get("invoice_no"),
        "Expiry": ex.get("Expiry"), "Quantity": ex.get("Qty"), "Routed to node": res.get("route"),
    }]), hide_index=True, width="stretch")

    wc = res.get("window_check")
    if wc:
        box = {"pass": st.success, "fail": st.error}.get(wc.get("result"), st.warning)
        box(f"Claim window check (CO-POL-014 §5.2): **{wc.get('result', '').upper()}**, {wc.get('detail', '')}")
    elif res.get("route") == "other" and not res.get("error"):
        st.warning("The graph routed this message to **other** (not a near-expiry, expired, breakage or "
                   "short-supply claim), so no claim check ran.")

    if res.get("error"):
        err = res["error"]
        st.error(f"graph_validate.py raised **{err['type']}**: {err['message']}")
        if err.get("hint"):
            st.info(err["hint"])
        with st.expander("Traceback"):
            st.code(err["traceback"], language=None)

    with st.expander("Full output of graph_validate.py"):
        st.code(res.get("log") or "(nothing printed)", language=None)
        if proc.stderr.strip():
            st.code(proc.stderr[-4000:], language=None)


# ----------------------------------------------------------------------------- page: report
def report_page():
    page_header("2. Generate claim report")
    st.caption("Runs `agent/graph_schema.py`: the scheme pipeline. Both options are optional; leave them "
               "unticked to use the script's defaults.")
    c1, c2 = st.columns(2)
    use_since = c1.checkbox("Set --since  (start of the 'last 12 months' window)")
    since = c1.date_input("--since", value=DEFAULT_SINCE, min_value=DATA_FROM, max_value=DATA_TO,
                          disabled=not use_since, format="YYYY-MM-DD")
    use_fefo = c2.checkbox("Set --fefo-from  (start of the FEFO / RSL window)")
    fefo = c2.date_input("--fefo-from", value=DEFAULT_FEFO_FROM, min_value=DATA_FROM, max_value=DATA_TO,
                         disabled=not use_fefo, format="YYYY-MM-DD")
    args = ["graph_schema.py"]
    if use_since:
        args += ["--since", since.isoformat()]
    if use_fefo:
        args += ["--fefo-from", fefo.isoformat()]
    st.code("python " + " ".join(args), language="bash")

    if st.button("Generate claim report", type="primary"):
        with st.spinner("Running graph_schema.py ..."):
            try:
                proc = run_script(args)
            except subprocess.TimeoutExpired:
                st.error("graph_schema.py did not finish within 5 minutes.")
                return
        if proc.returncode != 0 or "# Scheme pipeline report" not in proc.stdout:
            st.error(f"graph_schema.py failed (exit code {proc.returncode}).")
            st.code((proc.stderr or proc.stdout)[-4000:], language=None)
            return
        st.session_state["report"] = {"text": proc.stdout, "args": args, **parse_report(proc.stdout)}

    rep = st.session_state.get("report")
    if not rep:
        return

    titles = [s["title"] for s in rep["sections"]]
    picked = st.multiselect("Sections to show", titles, default=titles)
    d1, d2 = st.columns([1, 3])
    d1.download_button("Download report (.md)", rep["text"], file_name="scheme_pipeline_report.md")
    d2.caption("Run: `python " + " ".join(rep["args"]) + "`.  Scroll inside the report window with the mouse wheel, "
               "or click inside it and use the arrow / Page Up / Page Down keys.")

    with st.container(height=760, border=True):
        with st.expander("Data checks", expanded=False):
            for c in rep["checks"]:
                st.markdown(f"- {c}")
        for n, sec in enumerate(s for s in rep["sections"] if s["title"] in picked):
            st.subheader(f"{n + 1}. {sec['title']}")
            st.info(sec["finding"])
            for name, df in sec["tables"].items():
                chart_for(sec["title"], name, df)
                st.markdown(f"**{name.replace('_', ' ').capitalize()}**")
                st.dataframe(df, hide_index=True, width="stretch")
            if sec["sources"]:
                st.caption("Sources: " + sec["sources"])
            st.divider()

    with st.expander("Raw output of graph_schema.py"):
        st.code(rep["text"], language=None)


# ----------------------------------------------------------------------------- page: insight
INSIGHT_MODULE = "agent.Discovery.expiry_attribution"
STEP_RE = re.compile(r"^([A-Z]\d+)\. (.*)$")


def parse_insight(text: str) -> dict:
    """Split expiry_attribution.py's printout into parts, numbered steps and the summary."""
    parts, summary, current_part, step = [], [], None, None
    for line in text.splitlines():
        if line.startswith("PART "):
            current_part = {"title": line.strip(), "steps": []}
            parts.append(current_part)
            step = None
        elif line.startswith("SUMMARY"):
            current_part, step = None, "summary"
        elif step == "summary":
            if line.strip():
                summary.append(line.strip())
        elif (m := STEP_RE.match(line)) and current_part is not None:
            title = m.group(2).replace("<- headline share", "").strip()
            step = {"id": m.group(1), "title": title, "headline": "<- headline share" in line, "lines": []}
            current_part["steps"].append(step)
        elif isinstance(step, dict):
            step["lines"].append(line)
    for part in parts:
        for st_ in part["steps"]:
            while st_["lines"] and not st_["lines"][-1].strip():
                st_["lines"].pop()
            while st_["lines"] and not st_["lines"][0].strip():
                st_["lines"].pop(0)
    return {"parts": parts, "summary": summary}


def insight_metrics(summary: list[str]) -> list[tuple[str, str, str]]:
    """Headline numbers read from the script's own SUMMARY lines (never retyped)."""
    text = " ".join(summary)
    out = []
    if m := re.search(r"carry (\d+)% of sales but ([\d.]+)% of expiry-claim value", text):
        out.append(("Claim value on scheme-bought batches", f"{m.group(2)}%", f"those batches are {m.group(1)}% of sales"))
    if m := re.search(r"\(([\d.]+)% if credited", text):
        out.append(("Pack-weighted share", f"{m.group(1)}%", "only the packs bought on scheme"))
    if m := re.search(r"claim rate is ([\d.]+)% of sales against ([\d.]+)%", text):
        out.append(("Claim rate: scheme vs never-scheme", f"{m.group(1)}% vs {m.group(2)}%", "claim value / sales value"))
    if m := re.search(r"Tier A SKUs carry ([\d.]+)% of claim value on ([\d.]+)% of sales", text):
        out.append(("Tier A share of claims", f"{m.group(1)}%", f"on {m.group(2)}% of sales"))
    return out


def insight_page():
    page_header("3. Generate insight")
    st.caption(f"Runs `python -m {INSIGHT_MODULE}` from the repository root: how much of the expiry-return value "
               "is linked to quarter-end schemes, step by step, with every intermediate number.")
    use_since = st.checkbox("Set --since  (start of the claim window for steps A2-A6 and B2)")
    since = st.date_input("--since", value=DEFAULT_SINCE, min_value=DATA_FROM, max_value=DATA_TO,
                          disabled=not use_since, format="YYYY-MM-DD", key="insight_since")
    args = ["-m", INSIGHT_MODULE] + (["--since", since.isoformat()] if use_since else [])
    st.code("python " + " ".join(args), language="bash")

    if st.button("Generate insight", type="primary"):
        with st.spinner(f"Running {INSIGHT_MODULE} ..."):
            try:
                proc = run_script(args, timeout=300, cwd=ROOT)
            except subprocess.TimeoutExpired:
                st.error("expiry_attribution did not finish within 5 minutes.")
                return
        if proc.returncode != 0 or "SUMMARY" not in proc.stdout:
            st.error(f"{INSIGHT_MODULE} failed (exit code {proc.returncode}).")
            st.code((proc.stderr or proc.stdout)[-4000:], language=None)
            return
        st.session_state["insight"] = {"text": proc.stdout, "args": args, **parse_insight(proc.stdout)}

    ins = st.session_state.get("insight")
    if not ins:
        return

    metrics = insight_metrics(ins["summary"])
    if metrics:
        cols = st.columns(len(metrics))
        for col, (label, value, help_) in zip(cols, metrics):
            col.metric(label, value, help=help_)
    if ins["summary"]:
        st.success("**Summary**\n\n" + "\n\n".join(ins["summary"]))

    all_steps = [f"{s_['id']}. {s_['title']}" for p in ins["parts"] for s_ in p["steps"]]
    picked = st.multiselect("Steps to show", all_steps, default=all_steps, key="insight_steps")
    d1, d2 = st.columns([1, 3])
    d1.download_button("Download insight (.txt)", ins["text"], file_name="expiry_attribution.txt")
    d2.caption("Run: `python " + " ".join(ins["args"]) + "`.  Scroll inside the window with the mouse wheel, "
               "or click inside it and use the arrow / Page Up / Page Down keys. Steps marked HEADLINE produce "
               "the summary figures.")

    with st.container(height=760, border=True):
        for part in ins["parts"]:
            steps = [s_ for s_ in part["steps"] if f"{s_['id']}. {s_['title']}" in picked]
            if not steps:
                continue
            st.subheader(part["title"].title() if part["title"].isupper() else part["title"])
            for s_ in steps:
                st.markdown(f"**{s_['id']}. {s_['title']}**" + ("  `HEADLINE`" if s_["headline"] else ""))
                body = [ln for ln in s_["lines"] if not ln.strip().startswith("=>")]
                notes = [ln.strip()[2:].strip() for ln in s_["lines"] if ln.strip().startswith("=>")]
                if any(ln.strip() for ln in body):
                    st.code("\n".join(body), language=None)
                for n in notes:
                    st.info(n)
            st.divider()

    with st.expander(f"Raw output of {INSIGHT_MODULE}"):
        st.code(ins["text"], language=None)


# ----------------------------------------------------------------------------- page: validate one register claim
VALIDATE_MARKER = "@@CLAIM_VALIDATE@@"
EXAMPLE_CLAIMS = {   # real register claims, one per outcome
    "CLM-2605-04488": "duplicate of CLM-2603-01616, already credited",
    "CLM-2603-01616": "clean near-expiry claim",
    "CLM-2609-03036": "outside the claim window",
    "CLM-2609-02999": "more packs than invoiced",
    "CLM-2609-02810": "no invoice reference",
    "CLM-2609-04310": "breakage in transit",
}
VERDICT_BOX = {"APPROVE": st.success, "REJECT": st.error, "NEEDS_PERSON": st.warning}


def validate_claim_page():
    page_header("4. Validate claim")
    st.caption("Runs `agent/claim_validate.py` on one claim from the claims register (expiry_claims.csv). The graph "
               "looks the claim up, routes it by claim type and applies the CO-POL-014 rules read from config.py: "
               "batch and expiry (§5.3), claim window (§5.2), invoice reference (§5.3-5.4), quantity limit (§5.5), "
               "duplicate (§5.6), value at PTS (§5.7) and billing C&F (§5.1).")

    pick = st.selectbox("Example claims (optional)", ["(type your own below)"] +
                        [f"{k} - {v}" for k, v in EXAMPLE_CLAIMS.items()], key="vc_pick")
    default = "" if pick.startswith("(") else pick.split(" - ")[0]
    with st.form("validate_claim"):
        c1, c2 = st.columns([2, 1])
        claim_no = c1.text_input("Claim number", value=default, placeholder="CLM-2605-04488",
                                 help="Format CLM-YYMM-NNNNN, as in the claim_no column of expiry_claims.csv")
        draw = c2.checkbox("Also save the graph image (claim_graph.png)", help="Needs internet (mermaid.ink)")
        go = st.form_submit_button("Validate claim", type="primary")
    if not go:
        return
    claim_no = claim_no.strip().upper()
    if not re.match(r"^CLM-\d{4}-\d{5}$", claim_no):
        st.warning(f"`{claim_no or '(empty)'}` does not look like CLM-YYMM-NNNNN; running anyway.")

    args = ["claim_validate.py", "--claim-no", claim_no] + (["--draw"] if draw else [])
    st.code("python " + " ".join(args), language="bash")
    with st.spinner("Running claim_validate.py ..."):
        try:
            proc = run_script(args, timeout=180)
        except subprocess.TimeoutExpired:
            st.error("claim_validate.py did not finish within 3 minutes.")
            return
    line = next((ln for ln in reversed(proc.stdout.splitlines()) if ln.startswith(VALIDATE_MARKER)), None)
    if proc.returncode != 0 or line is None:
        st.error(f"claim_validate.py failed (exit code {proc.returncode}).")
        st.code((proc.stderr or proc.stdout)[-4000:], language=None)
        return
    r = json.loads(line[len(VALIDATE_MARKER):])

    VERDICT_BOX.get(r["verdict"], st.info)(f"**{r['claim_no']} -> {r['verdict']}**")
    st.caption("Graph path: load_claim -> " + (r.get("route") or "other") + " -> decide")

    if r.get("claim"):
        c = r["claim"]
        st.markdown(f"**Claim as logged** (expiry_claims.csv row {c['csv_row']})")
        st.dataframe(pd.DataFrame([{
            "Type": c["claim_type"], "Date": c["claim_date"], "Stockist": c["stockist_code"], "C&F": c["cnf_code"],
            "SKU": c["sku_code"], "Batch": c["batch_no"], "Expiry": c["expiry_date_as_claimed"],
            "Qty": c["qty_claimed"], "Value INR": c["claim_value_inr"], "Invoice": c["original_invoice_ref"],
            "Status": c["status"], "Credit note": c["credit_note_no"]}]), hide_index=True, width="stretch")
        if c["status"] == "Credited" and r["verdict"] == "REJECT":
            st.error(f"Already credited INR {c['credit_value_inr'] or 0:,.2f} although the rules reject it: "
                     f"a candidate for recovery.")

    checks = r.get("checks") or []
    rules_tbl = pd.DataFrame([{"Rule": k["rule"], "Result": k["result"].upper(), "Detail": k["detail"],
                               "Policy": k["clause"], "Source rows": "; ".join(k["evidence"])}
                              for k in checks if k["result"] != "info"])
    if len(rules_tbl):
        st.markdown("**Rule checks**")
        st.dataframe(rules_tbl, hide_index=True, width="stretch")
    for k in checks:
        if k["result"] == "info":
            st.info(f"{k['detail']}  ({k['clause']})")
    st.markdown(f"**Decision:** {r['summary']}")

    if draw and (AGENT / "claim_graph.png").exists():
        st.image(str(AGENT / "claim_graph.png"), caption="claim_validate.py graph")
    with st.expander("Full output of claim_validate.py"):
        st.code(proc.stdout.replace(line, "").strip(), language=None)


# ----------------------------------------------------------------------------- main
st.title("Project Sankalp")
choice = st.radio("What do you want to do?", list(TABS), horizontal=True)
st.divider()
if choice.startswith("1"):
    claim_check_page()
elif choice.startswith("2"):
    report_page()
elif choice.startswith("3"):
    insight_page()
else:
    validate_claim_page()
