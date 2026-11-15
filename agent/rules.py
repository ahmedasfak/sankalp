import re
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from llm import llm
from state import Message

def triage(state: Message):
    if (state["analysis"]).upper() == "NEAR EXPIRY":
        return "NEAR EXPIRY"
    if (state["analysis"]).upper() == "EXPIRY":
        return "EXPIRY"
    if (state["analysis"]).upper() == "SHORT SUPPLY":
        return "SHORT SUPPLY"
    if (state["analysis"]).upper() == "BREAKAGE IN TRANSIT":
            return "BREAKAGE IN TRANSIT"
    return "other"
#################################################################################
#Claims_precheck
#################################################################################

def claim_precheck_validation(state : Message) :
    if state["batch_no"] != None and state['invoice_no'] != None and state["Expiry"] != None and state["Qty"]  != None :
        return ["NEAR EXPIRY","EXPIRY","SHORT SUPPLY","BREAKAGE IN TRANSIT"]
    return "invalid_node"

#########################################################################
