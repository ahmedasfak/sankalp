import pandas as pd


batch_master = pd.read_csv('../data/batch_master.csv')
claim_emails = pd.read_csv('../data/claim_emails.csv')
cnf_stock_snapshot = pd.read_csv('../data/cnf_stock_snapshot.csv')
expiry_claims = pd.read_csv('../data/expiry_claims.csv')
primary_sales = pd.read_csv('../data/primary_sales.csv')
sku_master = pd.read_csv('../data/sku_master.csv')
stockist_master = pd.read_csv('../data/stockist_master.csv')

print(primary_sales)

print(sku_master)

print(stockist_master)