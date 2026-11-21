"""Run graph_validate.py's graph on one customer query, from the command line.

graph_validate.py always runs its hard-coded sample_message when executed, so
this script builds a Message from the arguments and invokes graph_validate's
compiled `app` with it. graph_validate.py itself is not changed.

    python run_claim_check.py --stockist STK0047 --received-date 18-11-2026 \
        --subject "near expiry stock" \
        --body "43 boxes of Aceclo-PCM, batch L2420268, expiring Oct-26. Invoice INV/N02/2505/036911."

Everything the graph prints is passed through. The last line is a JSON
result for the Streamlit app, prefixed with RESULT_MARKER.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import io
import json
import re
import sys
import traceback

RESULT_MARKER = "@@SANKALP_RESULT@@"
FIELDS = ("analysis", "batch_no", "invoice_no", "Expiry", "Qty")

# triage() in rules.py -> node name in graph_validate.py ("_" and " " are treated alike, as in triage)
ROUTE_OF = {"NEAR EXPIRY": "near_expiry", "EXPIRY": "expiry", "EXPIRED": "expiry",
            "SHORT SUPPLY": "short_supply", "BREAKAGE IN TRANSIT": "breakage_in_transit"}


def _window_result(log: str):
    """graph_validate's claim nodes print the window-check dict between two marker lines."""
    m = re.search(r"=+output=+\s*\n(.*?)\n=+output end =+", log, re.S)
    if not m:
        return None
    try:
        return ast.literal_eval(m.group(1).strip())
    except (ValueError, SyntaxError):
        return {"result": "unknown", "detail": m.group(1).strip()}


def run(message: dict) -> dict:
    buf = io.StringIO()
    out = {"message": message, "extracted": {}, "route": None, "window_check": None, "error": None, "log": ""}
    try:
        with contextlib.redirect_stdout(buf):
            import graph_validate                      # loads data, the model and the graph
            final = graph_validate.app.invoke(dict(message))
        out["extracted"] = {k: final.get(k) for k in FIELDS}
    except Exception as e:                               # report every failure; never guess a result
        tb = traceback.format_exc()
        out["error"] = {"type": type(e).__name__, "message": str(e), "traceback": tb, "hint": _hint(e, tb)}
    out["log"] = buf.getvalue()
    out["window_check"] = _window_result(out["log"])
    m = re.search(r"analysis value is (.+)", out["log"])
    if m:
        out["route"] = ROUTE_OF.get(m.group(1).strip().replace("_", " "), "other")
        out["extracted"].setdefault("analysis", m.group(1).strip())
    return out


def _hint(e: Exception, tb: str) -> str | None:
    msg = str(e)
    if "does not match format" in msg:
        return "A date could not be read. Enter the received date as DD-MM-YYYY."
    if "strptime() argument 1 must be str, not None" in msg or "NoneType" in msg:
        return ("A value the window check needs was not found: the invoice number + batch number pair is not "
                "in primary_sales.csv, or the batch is not in batch_master.csv.")
    if "api_key" in msg.lower() or "credentials" in msg.lower() or "401" in msg:
        return "The model call failed: set OPENROUTE_API_KEY in code/.env."
    if "Connection" in type(e).__name__ or "connect" in msg.lower():
        return "The model call could not reach openrouter.ai. Check the internet connection."
    return None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Run graph_validate.py on one customer query.")
    p.add_argument("--body", required=True, help="the customer's message: SKU, batch, expiry, qty, invoice")
    p.add_argument("--stockist", default="", help="stockist code, e.g. STK0047")
    p.add_argument("--received-date", required=True, help="date the claim is received, DD-MM-YYYY")
    p.add_argument("--from-name", default="", help="sender name")
    p.add_argument("--subject", default="", help="message subject")
    p.add_argument("--source", default="streamlit", help="where the query came from")
    a = p.parse_args(argv)
    message = {"source": a.source, "received_date": a.received_date, "from_name": a.from_name,
               "stockist_code": a.stockist.strip().upper(), "subject": a.subject, "body": a.body}
    result = run(message)
    sys.stdout.write(result["log"])
    sys.stdout.write("\n" + RESULT_MARKER + json.dumps(result, default=str) + "\n")
    return 1 if result["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
