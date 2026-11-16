from config import *


#test = find_policy_references("shelf")

#test1 = get_clause('CO-POL-014','5.2')
#print(SOURCE_DOCUMENTS)

import re
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from llm import llm
from state import Message
from rules import triage, claim_precheck_validation
from data import claims,sku_df,batch_df,stockist_df,stock,sales

#sku_code = sales.query(
#    "invoice_no == 'INV/N01/2503/030427' and batch_no == 'L2420268'"
#)["sku_code"].iloc[0]
#sku_code = sku_code.iloc[0] if not sku_code.empty else None
#sku_code = sales.query("invoice_no== 'INV/N01/2503/030427' and batch_no == 'L2420268' ")['sku_code'].iloc[0]
#print(test)
#print(sku_code)
#expiry_date = batch_df[(batch_df['batch_no'] == 'L2420268') & (batch_df['sku_code'] == sku_code),'expiry_date'].values[0]
#print(expiry_date)
result = sales.query("invoice_no == 'INV/N01/2503/030427' and batch_no == 'L2420268'")["sku_code"]

sku_code = result.iloc[0] if not result.empty else None

print(sku_code)