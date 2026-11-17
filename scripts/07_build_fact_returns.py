
from pathlib import Path
import pandas as pd
import numpy as np

# =========================================================
# 1. PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PROCESSED_DIR = DATA_DIR / "processed"
REPORT_DIR = BASE_DIR / "reports"

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

RETURNS_FILE = DATA_DIR / "sales_returns.csv"
FACT_SALES_FILE = PROCESSED_DIR / "fact_sales.csv"

OUTPUT_FILE = PROCESSED_DIR / "fact_returns.csv"

# =========================================================
# 2. LOAD DATA
# =========================================================

print("Loading returns and fact sales...")

returns = pd.read_csv(RETURNS_FILE)
fact_sales = pd.read_csv(FACT_SALES_FILE)

print(f"Returns rows: {len(returns):,}")
print(f"Fact sales rows: {len(fact_sales):,}")

# =========================================================
# 3. REQUIRED COLUMNS
# =========================================================

return_columns = [
    "return_id",
    "sales_order_id",
    "sales_line_id",
    "return_date",
    "sku_id",
    "return_quantity",
    "refund_amount_EGP",
    "reason",
    "refund_method"
]

sales_columns = [
    "sales_line_id",
    "sales_order_id",
    "order_date",
    "branch_id",
    "customer_id",
    "sales_channel",
    "payment_method",
    "status",
    "sku_id",
    "product_id",
    "product_name_ar",
    "category_en",
    "audience",
    "quantity",
    "unit_price_EGP",
    "gross_line_EGP",
    "discount_line_EGP",
    "net_line_EGP",
    "unit_cost_EGP",
    "line_cost_EGP",
    "margin_EGP"
]

missing_returns = [
    c for c in return_columns if c not in returns.columns
]

missing_sales = [
    c for c in sales_columns if c not in fact_sales.columns
]

if missing_returns:
    raise ValueError(f"Missing columns in sales_returns: {missing_returns}")

if missing_sales:
    raise ValueError(f"Missing columns in fact_sales: {missing_sales}")

returns = returns[return_columns].copy()
fact_sales = fact_sales[sales_columns].copy()

# =========================================================
# 4. DATA TYPE CLEANING
# =========================================================

returns["return_date"] = pd.to_datetime(
    returns["return_date"], errors="coerce"
)

fact_sales["order_date"] = pd.to_datetime(
    fact_sales["order_date"], errors="coerce"
)

numeric_columns = [
    "return_quantity",
    "refund_amount_EGP"
]

for col in numeric_columns:
    returns[col] = pd.to_numeric(
        returns[col], errors="coerce"
    )

for col in [
    "quantity",
    "unit_price_EGP",
    "gross_line_EGP",
    "discount_line_EGP",
    "net_line_EGP",
    "unit_cost_EGP",
    "line_cost_EGP",
    "margin_EGP"
]:
    fact_sales[col] = pd.to_numeric(
        fact_sales[col], errors="coerce"
    )

# =========================================================
# 5. PRIMARY KEY VALIDATION
# =========================================================

pk_checks = []

for table_name, df, pk in [
    ("sales_returns", returns, "return_id"),
    ("fact_sales", fact_sales, "sales_line_id")
]:
    pk_checks.append({
        "table": table_name,
        "primary_key": pk,
        "rows": len(df),
        "null_keys": int(df[pk].isna().sum()),
        "duplicate_keys": int(df[pk].duplicated().sum())
    })

pk_report = pd.DataFrame(pk_checks)

pk_report.to_csv(
    REPORT_DIR / "32_returns_primary_key_checks.csv",
    index=False
)

if (
    pk_report["null_keys"].sum() > 0
    or pk_report["duplicate_keys"].sum() > 0
):
    raise ValueError(
        "Primary key validation failed. Check report 32."
    )

# =========================================================
# 6. CHECK RETURN LINE REFERENCES
# =========================================================

# Each return must point to an existing sales line.
merged = returns.merge(
    fact_sales,
    on="sales_line_id",
    how="left",
    suffixes=("_return", "_sale"),
    indicator=True,
    validate="many_to_one"
)

orphan_returns = merged[
    merged["_merge"] == "left_only"
].copy()

orphan_returns.to_csv(
    REPORT_DIR / "33_returns_without_sales_line.csv",
    index=False
)

if len(orphan_returns) > 0:
    raise ValueError(
        f"{len(orphan_returns):,} returns have no matching sales line. "
        "Check report 33."
    )

merged = merged.drop(columns=["_merge"])

# =========================================================
# 7. RELATIONSHIP CONSISTENCY CHECKS
# =========================================================

merged["order_id_match"] = (
    merged["sales_order_id_return"]
    == merged["sales_order_id_sale"]
)

merged["sku_match"] = (
    merged["sku_id_return"]
    == merged["sku_id_sale"]
)

merged["return_date_valid"] = (
    merged["return_date"] >= merged["order_date"]
)

merged["return_quantity_valid"] = (
    (merged["return_quantity"] > 0)
    & (merged["return_quantity"] <= merged["quantity"])
)

merged["refund_amount_valid"] = (
    merged["refund_amount_EGP"] >= 0
)

consistency_checks = pd.DataFrame([
    {
        "check": "sales_order_id_matches",
        "rows_checked": len(merged),
        "failed_rows": int((~merged["order_id_match"]).sum())
    },
    {
        "check": "sku_id_matches",
        "rows_checked": len(merged),
        "failed_rows": int((~merged["sku_match"]).sum())
    },
    {
        "check": "return_date_not_before_order_date",
        "rows_checked": len(merged),
        "failed_rows": int((~merged["return_date_valid"]).sum())
    },
    {
        "check": "return_quantity_positive_and_not_above_sold_quantity",
        "rows_checked": len(merged),
        "failed_rows": int((~merged["return_quantity_valid"]).sum())
    },
    {
        "check": "refund_amount_non_negative",
        "rows_checked": len(merged),
        "failed_rows": int((~merged["refund_amount_valid"]).sum())
    }
])

consistency_checks.to_csv(
    REPORT_DIR / "34_returns_consistency_checks.csv",
    index=False
)

# Save detailed business anomalies for investigation.
anomaly_mask = (
    ~merged["order_id_match"]
    | ~merged["sku_match"]
    | ~merged["return_date_valid"]
    | ~merged["return_quantity_valid"]
    | ~merged["refund_amount_valid"]
)

merged.loc[anomaly_mask].to_csv(
    REPORT_DIR / "35_returns_business_anomalies.csv",
    index=False
)

# =========================================================
# 8. BUILD FACT RETURNS
# =========================================================

fact_returns = merged[[
    "return_id",
    "sales_order_id_return",
    "sales_line_id",
    "return_date",
    "order_date",
    "branch_id",
    "customer_id",
    "sales_channel",
    "payment_method",
    "status",
    "sku_id_return",
    "product_id",
    "product_name_ar",
    "category_en",
    "audience",
    "return_quantity",
    "refund_amount_EGP",
    "reason",
    "refund_method",
    "quantity",
    "unit_price_EGP",
    "gross_line_EGP",
    "discount_line_EGP",
    "net_line_EGP",
    "unit_cost_EGP",
    "line_cost_EGP",
    "margin_EGP"
]].copy()

fact_returns = fact_returns.rename(columns={
    "sales_order_id_return": "sales_order_id",
    "sku_id_return": "sku_id",
    "quantity": "sold_quantity",
    "order_date": "original_order_date"
})

# =========================================================
# 9. DERIVED DATE COLUMNS
# =========================================================

fact_returns["days_to_return"] = (
    fact_returns["return_date"]
    - fact_returns["original_order_date"]
).dt.days

fact_returns["return_year"] = (
    fact_returns["return_date"].dt.year
)

fact_returns["return_month"] = (
    fact_returns["return_date"].dt.month
)

fact_returns["return_year_month"] = (
    fact_returns["return_date"].dt.to_period("M").astype(str)
)

# =========================================================
# 10. FINAL VALIDATION
# =========================================================

if fact_returns["return_id"].duplicated().any():
    raise ValueError("Duplicate return_id found in fact_returns.")

if fact_returns["sales_line_id"].isna().any():
    raise ValueError("Missing sales_line_id found in fact_returns.")

# =========================================================
# 11. SAVE OUTPUT
# =========================================================

fact_returns.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8-sig"
)

# =========================================================
# 12. SUMMARY REPORT
# =========================================================

summary = pd.DataFrame([{
    "fact_returns_rows": len(fact_returns),
    "distinct_returns": fact_returns["return_id"].nunique(),
    "distinct_orders": fact_returns["sales_order_id"].nunique(),
    "distinct_sales_lines": fact_returns["sales_line_id"].nunique(),
    "distinct_products": fact_returns["product_id"].nunique(),
    "distinct_skus": fact_returns["sku_id"].nunique(),
    "distinct_branches": fact_returns["branch_id"].nunique(),
    "total_return_quantity": fact_returns["return_quantity"].sum(),
    "total_refund_EGP": fact_returns["refund_amount_EGP"].sum(),
    "average_days_to_return": fact_returns["days_to_return"].mean(),
    "null_customer_rows": fact_returns["customer_id"].isna().sum()
}])

summary.to_csv(
    REPORT_DIR / "36_fact_returns_summary.csv",
    index=False
)

print("\nCONSISTENCY CHECKS")
print(consistency_checks.to_string(index=False))

print("\nFACT RETURNS BUILD COMPLETE")
print(summary.to_string(index=False))

print(f"\nFact saved to: {OUTPUT_FILE}")
print(f"Reports saved to: {REPORT_DIR}")
