"""Shared graph state. Plain dicts and lists only, so the checkpointer can store it and a run can resume in another process."""
import operator
from typing import Annotated, Literal, Optional, TypedDict



class Message(TypedDict, total=False):
    source: str            # "email" | "register"
    received_date: str     # ISO date
    from_name: str
    stockist_code: str     # from the mailbox rule; may be empty
    subject: str
    body: str
    analysis : str
    batch_no: Optional[str]
    invoice_no: Optional[str]
    Expiry : Optional[str]
    Qty : Optional[str]

class SchemeState(TypedDict, total=False):
    request: dict                                   # {"since": "YYYY-MM-DD", "fefo_from": "YYYY-MM-DD"}
    data_checks: dict
    sections: Annotated[list, operator.add]         # one dict per analysis node (fan-in)
    report: str
 
class MessageLine(TypedDict, total=False):
    sku: Optional[str]
    batch_no: Optional[str]
    expiry_date: Optional[str]
    quantity: Optional[str]

class ClaimLine(TypedDict, total=False):
    line_id: str
    stockist_code: str
    product_text: str
    sku_code: str
    batch_no: str
    batch_as_written: str
    expiry_text: str
    qty: float
    invoice_ref: str
    claim_type: str
    claim_type_inferred: bool
    claim_date: str
    claim_no: str          # register rows only
    claimed_value: float   # register rows only


class Check(TypedDict):
    rule: str
    result: Literal["pass", "fail", "unknown", "info"]
    detail: str


class LineResult(TypedDict, total=False):
    line_id: str
    verdict: str
    allowed_qty: float
    expected_value_inr: float
    checks: list
    flags: list
    candidates: list
    facts: list            # every number or ID a note may quote


class SankalpState(TypedDict, total=False):
    request: dict                                   # {"kind": "inbound_message" | "weekly_expiry_run" | "scheme_view", ...}
    message: Message
    parse_attempts: int
    parse_status: str                               # ok | retry | failed
    extractor: str                                  # "llm:<model>" | "rules"
    message_type: str
    lines: list
    flags: Annotated[list, operator.add]            # message-level flags
    results: Annotated[list, operator.add]          # one LineResult per claim line, fan-in from Send
    candidates: list                                # sender candidates for unidentified mail
    queue: str                                      # who owns this item next
    note: str
    note_source: str                                # "template" | "llm:<model>" | "template (grounding failed)"
    decisions: list                                 # reviewer decisions, one per line
    lookup: dict                                    # status lookup result
    review_errors: list
    handoff: str                                    # "C" when a scheme question is routed to pilot C
    final: dict                                     # proposed action record; nothing is written to SAP
    pilot_b: dict
    pilot_c: dict
