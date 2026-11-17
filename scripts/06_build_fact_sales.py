
from pathlib import Path
import pandas as pd
import numpy as np

# =========================================================
# 1. PATHS AND SETTINGS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PROCESSED_DIR = DATA_DIR / "processed"
REPORT_DIR = BASE_DIR / "reports"

REPORT_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

ORDERS_FILE = DATA_DIR / "sales_orders.csv"
LINES_FILE = DATA_DIR / "sales_order_items.csv"
PRODUCT_DIM_FILE = PROCESSED_DIR / "dim_product.csv"

OUTPUT_FILE = PROCESSED_DIR / "fact_sales.csv"

TOLERANCE_EGP = 0.01

# =========================================================
# 2. LOAD DATA
# =========================================================

print("Loading sales data...")

orders = pd.read_csv(
    ORDERS_FILE,
    dtype={
        "sales_order_id": "string",
        "branch_id": "string",
        "customer_id": "string"
    },
    low_memory=False
)

lines = pd.read_csv(
    LINES_FILE,
    dtype={
        "sales_line_id": "string",
        "sales_order_id": "string",
        "branch_id": "string",
        "sku_id": "string",
        "product_id": "string"
    },
    low_memory=False
)

products = pd.read_csv(
    PRODUCT_DIM_FILE,
    dtype={"product_id": "string"},
    low_memory=False
)

# Normalize identifier whitespace
for df, columns in [
    (orders, ["sales_order_id", "branch_id", "customer_id"]),
    (lines, [
        "sales_line_id", "sales_order_id",
        "branch_id", "sku_id", "product_id"
    ]),
    (products, ["product_id"])
]:
    for col in columns:
        if col in df.columns:
            df[col] = df[col].str.strip()

# =========================================================
# 3. REQUIRED COLUMN CHECKS
# =========================================================

required_orders = [
    "sales_order_id", "order_date", "branch_id",
    "customer_id", "sales_channel", "payment_method",
    "items_count", "gross_EGP", "discount_EGP",
    "net_before_tax_EGP", "tax_EGP",
    "paid_total_EGP", "status"
]

required_lines = [
    "sales_line_id", "sales_order_id", "order_date",
    "branch_id", "sku_id", "product_id", "quantity",
    "unit_price_EGP", "gross_line_EGP",
    "discount_line_EGP", "net_line_EGP",
    "unit_cost_EGP", "margin_EGP"
]

for name, df, required in [
    ("sales_orders", orders, required_orders),
    ("sales_order_items", lines, required_lines),
    ("dim_product", products, ["product_id"])
]:
    missing = set(required) - set(df.columns)
    if missing:
        raise ValueError(f"{name} is missing columns: {missing}")

# =========================================================
# 4. PRIMARY KEY VALIDATION
# =========================================================

if orders["sales_order_id"].isna().any():
    raise ValueError("Null sales_order_id in orders.")

if orders["sales_order_id"].duplicated().any():
    raise ValueError("Duplicate sales_order_id in orders.")

if lines["sales_line_id"].isna().any():
    raise ValueError("Null sales_line_id in sales lines.")

if lines["sales_line_id"].duplicated().any():
    raise ValueError("Duplicate sales_line_id in sales lines.")

if products["product_id"].isna().any():
    raise ValueError("Null product_id in dim_product.")

if products["product_id"].duplicated().any():
    raise ValueError("Duplicate product_id in dim_product.")

# =========================================================
# 5. DATE AND NUMERIC CONVERSION
# =========================================================

orders["order_date"] = pd.to_datetime(
    orders["order_date"], errors="coerce"
)

lines["order_date"] = pd.to_datetime(
    lines["order_date"], errors="coerce"
)

numeric_columns = [
    "quantity", "unit_price_EGP", "gross_line_EGP",
    "discount_line_EGP", "net_line_EGP",
    "unit_cost_EGP", "margin_EGP"
]

for col in numeric_columns:
    lines[col] = pd.to_numeric(
        lines[col], errors="coerce"
    )

order_numeric_columns = [
    "items_count", "gross_EGP", "discount_EGP",
    "net_before_tax_EGP", "tax_EGP", "paid_total_EGP"
]

for col in order_numeric_columns:
    orders[col] = pd.to_numeric(
        orders[col], errors="coerce"
    )

if lines[numeric_columns].isna().any().any():
    raise ValueError("Null or invalid numeric values in sales lines.")

if orders[order_numeric_columns].isna().any().any():
    raise ValueError("Null or invalid numeric values in sales orders.")

if lines["order_date"].isna().any():
    raise ValueError("Invalid order_date in sales lines.")

if orders["order_date"].isna().any():
    raise ValueError("Invalid order_date in sales orders.")

# =========================================================
# 6. CHECK LINE-LEVEL BUSINESS FORMULAS
# =========================================================

lines["calculated_gross_EGP"] = (
    lines["quantity"] * lines["unit_price_EGP"]
)

lines["calculated_net_EGP"] = (
    lines["gross_line_EGP"] - lines["discount_line_EGP"]
)

lines["line_cost_EGP"] = (
    lines["quantity"] * lines["unit_cost_EGP"]
)

lines["calculated_margin_EGP"] = (
    lines["net_line_EGP"] - lines["line_cost_EGP"]
)

def difference_report(actual, calculated, label):
    difference = (actual - calculated).abs()

    return {
        "check": label,
        "rows_checked": len(difference),
        "rows_with_difference_over_tolerance": int(
            (difference > TOLERANCE_EGP).sum()
        ),
        "mean_absolute_difference": round(
            difference.mean(), 6
        ),
        "maximum_absolute_difference": round(
            difference.max(), 6
        )
    }

line_formula_checks = [
    difference_report(
        lines["gross_line_EGP"],
        lines["calculated_gross_EGP"],
        "gross_line_vs_quantity_times_unit_price"
    ),
    difference_report(
        lines["net_line_EGP"],
        lines["calculated_net_EGP"],
        "net_line_vs_gross_less_discount"
    ),
    difference_report(
        lines["margin_EGP"],
        lines["calculated_margin_EGP"],
        "margin_vs_net_less_line_cost"
    )
]

formula_report = pd.DataFrame(line_formula_checks)

formula_report.to_csv(
    REPORT_DIR / "26_sales_line_formula_checks.csv",
    index=False,
    encoding="utf-8-sig"
)

print("\nLINE FORMULA CHECKS")
print(formula_report.to_string(index=False))

# =========================================================
# 7. JOIN ORDER ATTRIBUTES TO SALES LINES
# =========================================================

order_attributes = orders[[
    "sales_order_id",
    "order_date",
    "branch_id",
    "customer_id",
    "sales_channel",
    "payment_method",
    "items_count",
    "gross_EGP",
    "discount_EGP",
    "net_before_tax_EGP",
    "tax_EGP",
    "paid_total_EGP",
    "status"
]].copy()

fact = lines.merge(
    order_attributes,
    on="sales_order_id",
    how="left",
    validate="many_to_one",
    indicator=True,
    suffixes=("", "_order")
)

unmatched_orders = fact["_merge"].ne("both")

if unmatched_orders.any():
    raise ValueError(
        f"{int(unmatched_orders.sum())} sales lines have no matching order."
    )

fact = fact.drop(columns=["_merge"])

# Validate order date and branch against line values
date_mismatch = (
    fact["order_date"] != fact["order_date_order"]
)

branch_mismatch = (
    fact["branch_id"] != fact["branch_id_order"]
)

if date_mismatch.any():
    raise ValueError(
        f"{int(date_mismatch.sum())} order-date mismatches."
    )

if branch_mismatch.any():
    raise ValueError(
        f"{int(branch_mismatch.sum())} branch mismatches."
    )

fact = fact.drop(columns=[
    "order_date_order",
    "branch_id_order"
])

# =========================================================
# 8. CHECK ITEMS COUNT AGAINST ORDER TABLE
# =========================================================

actual_line_counts = (
    lines.groupby("sales_order_id")
    .size()
    .rename("actual_items_count")
    .reset_index()
)

count_check = actual_line_counts.merge(
    orders[["sales_order_id", "items_count"]],
    on="sales_order_id",
    how="left",
    validate="one_to_one"
)

count_mismatch = (
    count_check["actual_items_count"]
    != count_check["items_count"]
)

count_check[count_mismatch].to_csv(
    REPORT_DIR / "27_order_items_count_mismatches.csv",
    index=False,
    encoding="utf-8-sig"
)

# =========================================================
# 9. RECONCILE LINE TOTALS TO ORDER TOTALS
# =========================================================

line_totals = (
    lines.groupby("sales_order_id")
    .agg(
        line_count=("sales_line_id", "count"),
        lines_gross_EGP=("gross_line_EGP", "sum"),
        lines_discount_EGP=("discount_line_EGP", "sum"),
        lines_net_EGP=("net_line_EGP", "sum")
    )
    .reset_index()
)

reconciliation = orders[[
    "sales_order_id",
    "items_count",
    "gross_EGP",
    "discount_EGP",
    "net_before_tax_EGP"
]].merge(
    line_totals,
    on="sales_order_id",
    how="left",
    validate="one_to_one"
)

reconciliation["gross_difference"] = (
    reconciliation["gross_EGP"]
    - reconciliation["lines_gross_EGP"]
)

reconciliation["discount_difference"] = (
    reconciliation["discount_EGP"]
    - reconciliation["lines_discount_EGP"]
)

reconciliation["net_difference"] = (
    reconciliation["net_before_tax_EGP"]
    - reconciliation["lines_net_EGP"]
)

reconciliation["line_count_difference"] = (
    reconciliation["items_count"]
    - reconciliation["line_count"]
)

reconciliation.to_csv(
    REPORT_DIR / "28_sales_order_reconciliation.csv",
    index=False,
    encoding="utf-8-sig"
)

reconciliation_summary = []

for col in [
    "gross_difference",
    "discount_difference",
    "net_difference"
]:
    reconciliation_summary.append({
        "check": col,
        "orders_checked": len(reconciliation),
        "orders_with_difference_over_tolerance": int(
            (reconciliation[col].abs() > TOLERANCE_EGP).sum()
        ),
        "maximum_absolute_difference": round(
            reconciliation[col].abs().max(), 6
        )
    })

reconciliation_summary.append({
    "check": "line_count_difference",
    "orders_checked": len(reconciliation),
    "orders_with_difference_over_tolerance": int(
        (reconciliation["line_count_difference"] != 0).sum()
    ),
    "maximum_absolute_difference": int(
        reconciliation["line_count_difference"].abs().max()
    )
})

pd.DataFrame(reconciliation_summary).to_csv(
    REPORT_DIR / "29_sales_order_reconciliation_summary.csv",
    index=False,
    encoding="utf-8-sig"
)

# =========================================================
# 10. JOIN PRODUCT DIMENSION
# =========================================================

product_columns = ["product_id"]

optional_product_columns = [
    "internal_product_name_ar",
    "public_product_name_ar",
    "category_en",
    "category_public",
    "audience",
    "match_status"
]

for col in optional_product_columns:
    if col in products.columns:
        product_columns.append(col)

product_lookup = products[product_columns].copy()

fact = fact.merge(
    product_lookup,
    on="product_id",
    how="left",
    validate="many_to_one",
    indicator="product_merge"
)

unmatched_products = fact["product_merge"].ne("both")

if unmatched_products.any():
    unmatched = fact.loc[unmatched_products, [
        "sales_line_id", "product_id"
    ]].drop_duplicates()

    unmatched.to_csv(
        REPORT_DIR / "30_sales_lines_without_product.csv",
        index=False,
        encoding="utf-8-sig"
    )

    raise ValueError(
        f"{int(unmatched_products.sum())} sales lines "
        "have no matching product dimension."
    )

fact = fact.drop(columns=["product_merge"])

# Unified display name, preserving both source names
if (
    "internal_product_name_ar" in fact.columns
    and "public_product_name_ar" in fact.columns
):
    fact["product_name_ar"] = (
        fact["internal_product_name_ar"]
        .fillna(fact["public_product_name_ar"])
    )

# =========================================================
# 11. FINAL FACT TABLE COLUMNS
# =========================================================

final_columns = [
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
    "category_public",
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

final_columns = [
    col for col in final_columns if col in fact.columns
]

fact_sales = fact[final_columns].copy()

# Date-derived fields for reporting
fact_sales["order_year"] = fact_sales["order_date"].dt.year
fact_sales["order_month"] = fact_sales["order_date"].dt.month
fact_sales["year_month"] = (
    fact_sales["order_date"].dt.to_period("M").astype(str)
)

# =========================================================
# 12. FINAL QUALITY CHECKS
# =========================================================

if fact_sales["sales_line_id"].duplicated().any():
    raise ValueError("Duplicate sales_line_id in final fact table.")

if len(fact_sales) != len(lines):
    raise ValueError("Row count changed during fact construction.")

if fact_sales["product_id"].isna().any():
    raise ValueError("Null product_id in final fact table.")

# Save fact table
fact_sales.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8-sig"
)

# =========================================================
# 13. SUMMARY
# =========================================================

summary = {
    "fact_sales_rows": len(fact_sales),
    "distinct_sales_orders": fact_sales["sales_order_id"].nunique(),
    "distinct_sales_lines": fact_sales["sales_line_id"].nunique(),
    "distinct_products": fact_sales["product_id"].nunique(),
    "distinct_skus": fact_sales["sku_id"].nunique(),
    "distinct_branches": fact_sales["branch_id"].nunique(),
    "null_customer_lines": int(fact_sales["customer_id"].isna().sum()),
    "total_quantity": int(fact_sales["quantity"].sum()),
    "gross_sales_EGP": round(fact_sales["gross_line_EGP"].sum(), 2),
    "discount_EGP": round(fact_sales["discount_line_EGP"].sum(), 2),
    "net_sales_before_tax_EGP": round(
        fact_sales["net_line_EGP"].sum(), 2
    ),
    "line_cost_EGP": round(fact_sales["line_cost_EGP"].sum(), 2),
    "margin_EGP": round(fact_sales["margin_EGP"].sum(), 2)
}

pd.DataFrame(
    list(summary.items()),
    columns=["metric", "value"]
).to_csv(
    REPORT_DIR / "31_fact_sales_summary.csv",
    index=False,
    encoding="utf-8-sig"
)

print("\n" + "=" * 65)
print("FACT SALES BUILD COMPLETE")
print("=" * 65)

for key, value in summary.items():
    print(f"{key}: {value:,}" if isinstance(value, int)
          else f"{key}: {value}")

print(f"\nFact saved to: {OUTPUT_FILE}")
print(f"Reports saved to: {REPORT_DIR}")
