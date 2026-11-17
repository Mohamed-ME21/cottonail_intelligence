import pandas as pd

df = pd.read_csv(
    "data/processed/sales_returns_by_product.csv")

print(df.head(10))