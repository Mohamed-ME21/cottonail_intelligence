
from pathlib import Path
import pandas as pd

# ==========================================
# 1. Configuration
# ==========================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
REPORT_DIR = BASE_DIR / "reports"

REPORT_DIR.mkdir(exist_ok=True)

def load_table(name, columns):
    return pd.read_csv(
        DATA_DIR / f"{name}.csv",
        usecols=columns,
        dtype="string",
        low_memory=False
    )

def clean_id(series):
    return series.astype("string").str.strip()

# ==========================================
# 2. Load Required Tables
# ==========================================

orders = load_table(
    "sales_orders",
    [
        "sales_order_id", "customer_id", "branch_id",
        "gross_EGP", "discount_EGP", "net_before_tax_EGP"
    ]
)

items = load_table(
    "sales_order_items",
    [
        "sales_line_id", "sales_order_id", "branch_id",
        "product_id", "sku_id", "gross_line_EGP",
        "discount_line_EGP", "net_line_EGP"
    ]
)

customers = load_table("customers", ["customer_id"])
branches = load_table("branches", ["branch_id"])
products = load_table("products_catalog", ["product_id"])
skus = load_table("sku_variants", ["sku_id", "product_id"])

payments = load_table(
    "sales_payments",
    ["payment_id", "sales_order_id"]
)

shipments = load_table(
    "delivery_shipments",
    ["shipment_id", "sales_order_id"]
)

returns = load_table(
    "sales_returns",
    ["return_id", "sales_order_id", "sales_line_id", "sku_id"]
)

# ==========================================
# 3. Normalize IDs
# ==========================================

tables = {
    "orders": orders,
    "items": items,
    "customers": customers,
    "branches": branches,
    "products": products,
    "skus": skus,
    "payments": payments,
    "shipments": shipments,
    "returns": returns
}

for df in tables.values():
    for col in df.columns:
        if col.endswith("_id"):
            df[col] = clean_id(df[col])

# ==========================================
# 4. Primary Key Validation
# ==========================================

primary_keys = {
    "orders": ("sales_order_id", orders),
    "items": ("sales_line_id", items),
    "customers": ("customer_id", customers),
    "branches": ("branch_id", branches),
    "products": ("product_id", products),
    "skus": ("sku_id", skus),
    "payments": ("payment_id", payments),
    "shipments": ("shipment_id", shipments),
    "returns": ("return_id", returns)
}

pk_results = []

for table, (column, df) in primary_keys.items():

    duplicate_count = int(df[column].duplicated().sum())
    null_count = int(df[column].isna().sum())

    pk_results.append({
        "table": table,
        "column": column,
        "rows": len(df),
        "duplicate_count": duplicate_count,
        "null_count": null_count,
        "valid_candidate": (
            duplicate_count == 0 and null_count == 0
        )
    })

pk_report = pd.DataFrame(pk_results)

# ==========================================
# 5. Foreign Key Validation
# ==========================================

relationships = [
    ("orders", "customer_id", "customers", "customer_id", True),
    ("orders", "branch_id", "branches", "branch_id", False),
    ("items", "sales_order_id", "orders", "sales_order_id", False),
    ("items", "branch_id", "branches", "branch_id", False),
    ("items", "product_id", "products", "product_id", False),
    ("items", "sku_id", "skus", "sku_id", False),
    ("payments", "sales_order_id", "orders", "sales_order_id", False),
    ("shipments", "sales_order_id", "orders", "sales_order_id", False),
    ("returns", "sales_order_id", "orders", "sales_order_id", False),
    ("returns", "sales_line_id", "items", "sales_line_id", False),
    ("returns", "sku_id", "skus", "sku_id", False),
    ("skus", "product_id", "products", "product_id", False)
]

fk_results = []

for child_name, child_col, parent_name, parent_col, nullable in relationships:

    child = tables[child_name]
    parent = tables[parent_name]

    parent_values = set(parent[parent_col].dropna())

    child_values = child[child_col].dropna()

    orphan_mask = ~child_values.isin(parent_values)

    fk_results.append({
        "child_table": child_name,
        "child_column": child_col,
        "parent_table": parent_name,
        "parent_column": parent_col,
        "child_rows": len(child),
        "null_count": int(child[child_col].isna().sum()),
        "orphan_rows": int(orphan_mask.sum()),
        "nullable": nullable
    })

fk_report = pd.DataFrame(fk_results)

# ==========================================
# 6. Cardinality Validation
# ==========================================

cardinality_results = []

for name, df, column in [
    ("payments", payments, "sales_order_id"),
    ("shipments", shipments, "sales_order_id"),
    ("returns", returns, "sales_order_id"),
    ("returns", returns, "sales_line_id")
]:

    counts = df.groupby(column).size()

    cardinality_results.append({
        "table": name,
        "relationship_column": column,
        "distinct_values": len(counts),
        "values_with_multiple_rows": int((counts > 1).sum()),
        "maximum_rows_per_value": (
            int(counts.max()) if len(counts) else 0
        )
    })

cardinality_report = pd.DataFrame(cardinality_results)

# ==========================================
# 7. SKU and Product Consistency
# ==========================================

item_sku_check = items[
    ["sales_line_id", "sku_id", "product_id"]
].merge(
    skus,
    on="sku_id",
    how="left",
    suffixes=("_item", "_sku")
)

sku_product_mismatch = (
    item_sku_check["product_id_item"]
    != item_sku_check["product_id_sku"]
)

sku_product_mismatch_count = int(
    sku_product_mismatch.fillna(False).sum()
)

# ==========================================
# 8. Order and Item Branch Consistency
# ==========================================

order_branch_check = items[
    ["sales_order_id", "branch_id"]
].merge(
    orders[["sales_order_id", "branch_id"]],
    on="sales_order_id",
    how="left",
    suffixes=("_item", "_order")
)

branch_mismatch = (
    order_branch_check["branch_id_item"]
    != order_branch_check["branch_id_order"]
)

branch_mismatch_count = int(
    branch_mismatch.fillna(False).sum()
)

# ==========================================
# 9. Sales Amount Reconciliation
# ==========================================

numeric_columns = [
    "gross_line_EGP",
    "discount_line_EGP",
    "net_line_EGP"
]

for col in numeric_columns:
    items[col] = pd.to_numeric(items[col], errors="coerce")

for col in ["gross_EGP", "discount_EGP", "net_before_tax_EGP"]:
    orders[col] = pd.to_numeric(orders[col], errors="coerce")

item_totals = (
    items.groupby("sales_order_id", as_index=False)
    .agg(
        items_gross=("gross_line_EGP", "sum"),
        items_discount=("discount_line_EGP", "sum"),
        items_net=("net_line_EGP", "sum")
    )
)

reconciliation = orders[
    [
        "sales_order_id", "gross_EGP",
        "discount_EGP", "net_before_tax_EGP"
    ]
].merge(
    item_totals,
    on="sales_order_id",
    how="left"
)

reconciliation["gross_difference"] = (
    reconciliation["gross_EGP"] - reconciliation["items_gross"]
)

reconciliation["discount_difference"] = (
    reconciliation["discount_EGP"] - reconciliation["items_discount"]
)

reconciliation["net_difference"] = (
    reconciliation["net_before_tax_EGP"] - reconciliation["items_net"]
)

reconciliation_summary = []

for column in [
    "gross_difference",
    "discount_difference",
    "net_difference"
]:

    differences = reconciliation[column].dropna()

    reconciliation_summary.append({
        "metric": column,
        "compared_orders": len(differences),
        "orders_with_difference_over_0.01": int(
            (differences.abs() > 0.01).sum()
        ),
        "mean_absolute_difference": round(
            differences.abs().mean(), 4
        ),
        "max_absolute_difference": round(
            differences.abs().max(), 4
        )
    })

reconciliation_report = pd.DataFrame(reconciliation_summary)

# ==========================================
# 10. Save Reports
# ==========================================

reports = {
    "06_primary_key_validation.csv": pk_report,
    "07_foreign_key_validation.csv": fk_report,
    "08_cardinality_validation.csv": cardinality_report,
    "09_sales_reconciliation.csv": reconciliation_report
}

for filename, df in reports.items():
    df.to_csv(
        REPORT_DIR / filename,
        index=False,
        encoding="utf-8-sig"
    )

# ==========================================
# 11. Final Summary
# ==========================================

print("\n========== PRIMARY KEY VALIDATION ==========")
print(pk_report.to_string(index=False))

print("\n========== FOREIGN KEY VALIDATION ==========")
print(fk_report.to_string(index=False))

print("\n========== CARDINALITY VALIDATION ==========")
print(cardinality_report.to_string(index=False))

print("\n========== SKU / PRODUCT VALIDATION ==========")
print("Product-SKU mismatches:", sku_product_mismatch_count)

print("\n========== BRANCH VALIDATION ==========")
print("Order-item branch mismatches:", branch_mismatch_count)

print("\n========== SALES RECONCILIATION ==========")
print(reconciliation_report.to_string(index=False))

print("\nAll validation reports saved successfully.")
