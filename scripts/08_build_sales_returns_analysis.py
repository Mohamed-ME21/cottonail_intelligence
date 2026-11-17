
from pathlib import Path
import pandas as pd
import numpy as np

# =========================================================
# 1. PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
REPORT_DIR = BASE_DIR / "reports"

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

SALES_FILE = PROCESSED_DIR / "fact_sales.csv"
RETURNS_FILE = PROCESSED_DIR / "fact_returns.csv"

# Main output
DETAIL_OUTPUT = PROCESSED_DIR / "sales_returns_analysis.csv"

# Aggregated outputs
PRODUCT_OUTPUT = PROCESSED_DIR / "sales_returns_by_product.csv"
BRANCH_OUTPUT = PROCESSED_DIR / "sales_returns_by_branch.csv"
SALES_MONTH_OUTPUT = PROCESSED_DIR / "sales_returns_by_sales_month.csv"
RETURN_MONTH_OUTPUT = PROCESSED_DIR / "returns_by_return_month.csv"

# Reports
ANOMALY_REPORT = REPORT_DIR / "37_cumulative_return_quantity_anomalies.csv"
SUMMARY_REPORT = REPORT_DIR / "38_sales_returns_analysis_summary.csv"


# =========================================================
# 2. LOAD DATA
# =========================================================

print("Loading Fact Sales and Fact Returns...")

sales = pd.read_csv(SALES_FILE)
returns = pd.read_csv(RETURNS_FILE)

print(f"Fact Sales rows: {len(sales):,}")
print(f"Fact Returns rows: {len(returns):,}")


# =========================================================
# 3. CHECK REQUIRED COLUMNS
# =========================================================

required_sales = [
    "sales_line_id",
    "sales_order_id",
    "order_date",
    "branch_id",
    "customer_id",
    "sales_channel",
    "product_id",
    "product_name_ar",
    "category_en",
    "audience",
    "sku_id",
    "quantity",
    "gross_line_EGP",
    "discount_line_EGP",
    "net_line_EGP",
    "line_cost_EGP",
    "margin_EGP"
]

required_returns = [
    "return_id",
    "sales_order_id",
    "sales_line_id",
    "return_date",
    "sku_id",
    "product_id",
    "branch_id",
    "return_quantity",
    "refund_amount_EGP",
    "reason",
    "refund_method"
]

missing_sales = [
    col for col in required_sales if col not in sales.columns
]

missing_returns = [
    col for col in required_returns if col not in returns.columns
]

if missing_sales:
    raise ValueError(
        f"Missing columns in Fact Sales: {missing_sales}"
    )

if missing_returns:
    raise ValueError(
        f"Missing columns in Fact Returns: {missing_returns}"
    )


# =========================================================
# 4. DATA TYPE CLEANING
# =========================================================

sales["order_date"] = pd.to_datetime(
    sales["order_date"], errors="coerce"
)

returns["return_date"] = pd.to_datetime(
    returns["return_date"], errors="coerce"
)

sales_numeric = [
    "quantity",
    "gross_line_EGP",
    "discount_line_EGP",
    "net_line_EGP",
    "line_cost_EGP",
    "margin_EGP"
]

returns_numeric = [
    "return_quantity",
    "refund_amount_EGP"
]

for col in sales_numeric:
    sales[col] = pd.to_numeric(sales[col], errors="coerce")

for col in returns_numeric:
    returns[col] = pd.to_numeric(returns[col], errors="coerce")


# =========================================================
# 5. PRIMARY KEY CHECKS
# =========================================================

if sales["sales_line_id"].isna().any():
    raise ValueError("Fact Sales contains null sales_line_id.")

if sales["sales_line_id"].duplicated().any():
    raise ValueError("Fact Sales contains duplicate sales_line_id.")

if returns["return_id"].isna().any():
    raise ValueError("Fact Returns contains null return_id.")

if returns["return_id"].duplicated().any():
    raise ValueError("Fact Returns contains duplicate return_id.")


# =========================================================
# 6. AGGREGATE RETURNS AT SALES LINE LEVEL
# =========================================================

print("\nAggregating returns by sales_line_id...")

# One row per sales_line_id.
# This prevents sales rows from multiplying during the join.

return_by_line = (
    returns
    .groupby("sales_line_id", as_index=False)
    .agg(
        return_records=("return_id", "nunique"),
        returned_quantity=("return_quantity", "sum"),
        refund_amount_EGP=("refund_amount_EGP", "sum"),
        first_return_date=("return_date", "min"),
        last_return_date=("return_date", "max")
    )
)

if return_by_line["sales_line_id"].duplicated().any():
    raise ValueError(
        "Return aggregation did not produce unique sales_line_id."
    )


# =========================================================
# 7. MERGE WITH FACT SALES
# =========================================================

print("Joining aggregated returns to Fact Sales...")

analysis = sales.merge(
    return_by_line,
    on="sales_line_id",
    how="left",
    validate="one_to_one"
)

# Lines without returns get zero return values.
analysis["return_records"] = (
    analysis["return_records"].fillna(0).astype(int)
)

analysis["returned_quantity"] = (
    analysis["returned_quantity"].fillna(0)
)

analysis["refund_amount_EGP"] = (
    analysis["refund_amount_EGP"].fillna(0)
)

analysis["has_return"] = (
    analysis["return_records"] > 0
)


# =========================================================
# 8. CUMULATIVE RETURN QUANTITY CHECK
# =========================================================

analysis["return_quantity_exceeds_sold"] = (
    analysis["returned_quantity"] > analysis["quantity"]
)

anomalies = analysis[
    analysis["return_quantity_exceeds_sold"]
].copy()

anomalies.to_csv(
    ANOMALY_REPORT,
    index=False,
    encoding="utf-8-sig"
)

print(
    "Sales lines with cumulative returned quantity above sold quantity:",
    f"{len(anomalies):,}"
)


# =========================================================
# 9. CALCULATE LINE-LEVEL METRICS
# =========================================================

analysis["remaining_quantity"] = (
    analysis["quantity"] - analysis["returned_quantity"]
)

# Provisional indicator only.
# Refund amount may include tax or other adjustments.
analysis["net_after_refund_proxy_EGP"] = (
    analysis["net_line_EGP"] - analysis["refund_amount_EGP"]
)

analysis["return_quantity_rate"] = np.where(
    analysis["quantity"] > 0,
    analysis["returned_quantity"] / analysis["quantity"],
    np.nan
)

analysis["refund_to_net_sales_rate"] = np.where(
    analysis["net_line_EGP"] > 0,
    analysis["refund_amount_EGP"] / analysis["net_line_EGP"],
    np.nan
)

analysis["order_year_month"] = (
    analysis["order_date"].dt.to_period("M").astype(str)
)


# =========================================================
# 10. SAVE LINE-LEVEL ANALYSIS
# =========================================================

analysis.to_csv(
    DETAIL_OUTPUT,
    index=False,
    encoding="utf-8-sig"
)

print(f"\nDetail file saved: {DETAIL_OUTPUT}")


# =========================================================
# 11. PRODUCT ANALYSIS
# =========================================================

product_summary = (
    analysis
    .groupby(
        ["product_id", "product_name_ar", "category_en", "audience"],
        dropna=False,
        as_index=False
    )
    .agg(
        sales_lines=("sales_line_id", "nunique"),
        sold_quantity=("quantity", "sum"),
        returned_quantity=("returned_quantity", "sum"),
        gross_sales_EGP=("gross_line_EGP", "sum"),
        discounts_EGP=("discount_line_EGP", "sum"),
        net_sales_before_tax_EGP=("net_line_EGP", "sum"),
        refunds_EGP=("refund_amount_EGP", "sum"),
        sales_margin_EGP=("margin_EGP", "sum"),
        lines_with_returns=("has_return", "sum")
    )
)

product_summary["return_quantity_rate"] = np.where(
    product_summary["sold_quantity"] > 0,
    product_summary["returned_quantity"]
    / product_summary["sold_quantity"],
    np.nan
)

product_summary["refund_to_net_sales_rate"] = np.where(
    product_summary["net_sales_before_tax_EGP"] > 0,
    product_summary["refunds_EGP"]
    / product_summary["net_sales_before_tax_EGP"],
    np.nan
)

product_summary["net_after_refund_proxy_EGP"] = (
    product_summary["net_sales_before_tax_EGP"]
    - product_summary["refunds_EGP"]
)

product_summary.to_csv(
    PRODUCT_OUTPUT,
    index=False,
    encoding="utf-8-sig"
)


# =========================================================
# 12. BRANCH ANALYSIS
# =========================================================

branch_summary = (
    analysis
    .groupby("branch_id", dropna=False, as_index=False)
    .agg(
        sales_lines=("sales_line_id", "nunique"),
        sold_quantity=("quantity", "sum"),
        returned_quantity=("returned_quantity", "sum"),
        net_sales_before_tax_EGP=("net_line_EGP", "sum"),
        refunds_EGP=("refund_amount_EGP", "sum"),
        lines_with_returns=("has_return", "sum")
    )
)

branch_summary["return_quantity_rate"] = np.where(
    branch_summary["sold_quantity"] > 0,
    branch_summary["returned_quantity"]
    / branch_summary["sold_quantity"],
    np.nan
)

branch_summary["refund_to_net_sales_rate"] = np.where(
    branch_summary["net_sales_before_tax_EGP"] > 0,
    branch_summary["refunds_EGP"]
    / branch_summary["net_sales_before_tax_EGP"],
    np.nan
)

branch_summary["net_after_refund_proxy_EGP"] = (
    branch_summary["net_sales_before_tax_EGP"]
    - branch_summary["refunds_EGP"]
)

branch_summary.to_csv(
    BRANCH_OUTPUT,
    index=False,
    encoding="utf-8-sig"
)


# =========================================================
# 13. SALES MONTH ANALYSIS
# =========================================================

# This groups sales by the month in which the original
# sale happened, then attributes its returns to that sale.

sales_month_summary = (
    analysis
    .groupby("order_year_month", dropna=False, as_index=False)
    .agg(
        sales_lines=("sales_line_id", "nunique"),
        sold_quantity=("quantity", "sum"),
        returned_quantity=("returned_quantity", "sum"),
        net_sales_before_tax_EGP=("net_line_EGP", "sum"),
        refunds_EGP=("refund_amount_EGP", "sum")
    )
)

sales_month_summary["return_quantity_rate"] = np.where(
    sales_month_summary["sold_quantity"] > 0,
    sales_month_summary["returned_quantity"]
    / sales_month_summary["sold_quantity"],
    np.nan
)

sales_month_summary["refund_to_net_sales_rate"] = np.where(
    sales_month_summary["net_sales_before_tax_EGP"] > 0,
    sales_month_summary["refunds_EGP"]
    / sales_month_summary["net_sales_before_tax_EGP"],
    np.nan
)

sales_month_summary["net_after_refund_proxy_EGP"] = (
    sales_month_summary["net_sales_before_tax_EGP"]
    - sales_month_summary["refunds_EGP"]
)

sales_month_summary.to_csv(
    SALES_MONTH_OUTPUT,
    index=False,
    encoding="utf-8-sig"
)


# =========================================================
# 14. RETURN MONTH ANALYSIS
# =========================================================

returns["return_year_month"] = (
    returns["return_date"].dt.to_period("M").astype(str)
)

return_month_summary = (
    returns
    .groupby("return_year_month", dropna=False, as_index=False)
    .agg(
        return_records=("return_id", "nunique"),
        returned_quantity=("return_quantity", "sum"),
        refunds_EGP=("refund_amount_EGP", "sum"),
        distinct_orders=("sales_order_id", "nunique"),
        distinct_sales_lines=("sales_line_id", "nunique")
    )
)

return_month_summary.to_csv(
    RETURN_MONTH_OUTPUT,
    index=False,
    encoding="utf-8-sig"
)


# =========================================================
# 15. FINAL RECONCILIATION
# =========================================================

sales_total = sales["net_line_EGP"].sum()
refund_total = returns["refund_amount_EGP"].sum()

summary = pd.DataFrame([{
    "fact_sales_rows": len(sales),
    "fact_returns_rows": len(returns),
    "analysis_rows": len(analysis),
    "distinct_sales_lines": analysis["sales_line_id"].nunique(),
    "sales_rows_preserved": len(analysis) == len(sales),
    "total_sold_quantity": sales["quantity"].sum(),
    "total_returned_quantity": returns["return_quantity"].sum(),
    "total_net_sales_before_tax_EGP": sales_total,
    "total_refunds_EGP": refund_total,
    "net_after_refund_proxy_EGP": sales_total - refund_total,
    "sales_lines_with_returns": int(analysis["has_return"].sum()),
    "sales_lines_without_returns": int((~analysis["has_return"]).sum()),
    "cumulative_return_quantity_anomalies": len(anomalies)
}])

summary.to_csv(
    SUMMARY_REPORT,
    index=False,
    encoding="utf-8-sig"
)

# Check that aggregation did not change sales totals.
if len(analysis) != len(sales):
    raise ValueError("Analysis row count differs from Fact Sales.")

if analysis["sales_line_id"].nunique() != sales["sales_line_id"].nunique():
    raise ValueError("Distinct sales lines changed after merge.")

if not np.isclose(
    analysis["net_line_EGP"].sum(),
    sales["net_line_EGP"].sum(),
    atol=0.01
):
    raise ValueError("Net sales total changed after merge.")

if not np.isclose(
    analysis["refund_amount_EGP"].sum(),
    refund_total,
    atol=0.01
):
    raise ValueError("Refund total changed after merge.")


# =========================================================
# 16. PRINT RESULTS
# =========================================================

print("\n======================================")
print("SALES & RETURNS ANALYSIS COMPLETE")
print("======================================")

print(summary.to_string(index=False))

print("\nOUTPUT FILES")
print(f"1. {DETAIL_OUTPUT}")
print(f"2. {PRODUCT_OUTPUT}")
print(f"3. {BRANCH_OUTPUT}")
print(f"4. {SALES_MONTH_OUTPUT}")
print(f"5. {RETURN_MONTH_OUTPUT}")

print("\nREPORT FILES")
print(f"1. {ANOMALY_REPORT}")
print(f"2. {SUMMARY_REPORT}")
