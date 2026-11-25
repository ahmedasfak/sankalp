from __future__ import annotations

from pathlib import Path
from typing import TypedDict
import re
import pandas as pd


data_dir = Path(__file__).resolve().parents[1] / "data"

def parse_dates(s):
    s = s.astype(str).str.strip()
    iso = s.str.match(r"^\d{4}-\d{2}-\d{2}$")
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    out[iso] = pd.to_datetime(s[iso], format="%Y-%m-%d", errors="coerce")
    out[~iso] = pd.to_datetime(s[~iso], format="mixed", dayfirst=True, errors="coerce")
    return out


def to_num(s):
    return pd.to_numeric(s.astype(str).str.replace(",", "").str.strip(), errors="coerce")


def norm_inv(x):
    if x is None or (isinstance(x, float) and pd.isna(x)) or str(x).strip() == "":
        return None
    return re.sub(r"[-\s]+", "/", str(x).strip().upper())


def iso(d):
    return None if d is None or pd.isna(d) else pd.Timestamp(d).strftime("%Y-%m-%d")


bm=pd.read_csv(data_dir / "batch_master.csv")
claim_emails=pd.read_csv(data_dir / "claim_emails.csv")
st=pd.read_csv(data_dir / "cnf_stock_snapshot.csv")
cl=pd.read_csv(data_dir / "expiry_claims.csv")
ps=pd.read_csv(data_dir / "primary_sales.csv")
sku=pd.read_csv(data_dir / "sku_master.csv")
sm=pd.read_csv(data_dir / "stockist_master.csv")

#drop duplicate data.

bm.drop_duplicates()
claim_emails.drop_duplicates()
st.drop_duplicates()
cl.drop_duplicates()
ps.drop_duplicates()
sku.drop_duplicates()
sm.drop_duplicates()

sku.loc[0, "sku_code"] = "PFL1001"  # first SKU code arrives garbled ("+")
for d in (ps, cl):
    d["stockist_code"] = d.stockist_code.str.upper().str.strip()
    d["batch_no"] = d.batch_no.str.upper().str.strip()
    d["sku_code"] = d.sku_code.str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)
ps["date"] = parse_dates(ps.invoice_date)
for c in ["ordered_qty", "invoiced_qty", "free_qty", "pts_inr", "net_value_inr"]:
   ps[c] = to_num(ps[c])
cl["date"] = parse_dates(cl.claim_date); cl["exp"] = parse_dates(cl.expiry_date_as_claimed)
cl["qty"] = to_num(cl.qty_claimed); cl["val"] = to_num(cl.claim_value_inr); cl["cval"] = to_num(cl.credit_value_inr)
cl["cn_date"] = parse_dates(cl.credit_note_date)
cl["inv"] = cl.original_invoice_ref.map(norm_inv)
claims = cl
st["cnf"] = st.cnf_code.str.replace(r"^CF(?=[A-Z]\d)", "CF-", regex=True)
st["date"] = parse_dates(st.snapshot_date); st["qty"] = to_num(st.qty_on_hand_packs)
st["out"] = to_num(st.avg_monthly_outward_packs); st["exp"] = parse_dates(st.expiry_date)
st["sku_code"] = st.sku_code.str.upper().str.strip(); st["batch_no"] = st.batch_no.str.upper().str.strip()
stock = st
bm["exp"] = parse_dates(bm.expiry_date); bm["mfg"] = parse_dates(bm.mfg_date)
bm["batch_no"] = bm.batch_no.str.upper().str.strip(); 
bm["sku_code"] = bm.sku_code.str.upper().str.strip()
batch_df = bm
sm["stockist_code"] = sm.stockist_code.str.upper().str.strip()
stockist_df = sm
sku["pts"] = to_num(sku.pts_inr)
sku_df = sku
sales=ps

stockists = {r.stockist_code: dict(name=r.stockist_name, cnf=r.cnf_code, city=r.city) for r in sm.itertuples()}
batches = {r.batch_no: dict(sku=r.sku_code, exp=r.exp, mfg=r.mfg) for r in bm.itertuples()}
skus = {r.sku_code: dict(desc=r.product_description, pack=r.pack, pts=float(r.pts)) for r in sku.itertuples()}

#print(claims,sku_df,batch_df,stockist_df,stock,sales)