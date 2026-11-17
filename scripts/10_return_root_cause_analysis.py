
from pathlib import Path
import pandas as pd
import numpy as np

# ============================================================
# 1. PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
REPORTS_DIR = BASE_DIR / "reports"

FACT_SALES_PATH = PROCESSED_DIR / "fact_sales.csv"
FACT_RETURNS_PATH = PROCESSED_DIR / "fact_returns.csv"

REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# 2. HELPER FUNCTIONS
# ============================================================

def save_report(df, filename):
    """Save a report as CSV."""
    output_path = REPORTS_DIR / filename
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"Saved: {output_path}")


def require_columns(df, columns, file_name):
    """Check that required columns exist."""
    missing = [col for col in columns if col not in df.columns]

    if missing:
        raise ValueError(
            f"Missing columns in {file_name}: {missing}\n"
            f"Available columns: {df.columns.tolist()}"
        )


def safe_rate(numerator, denominator):
    """Calculate a percentage safely."""
    return np.where(
        denominator > 0,
        numerator / denominator * 100,
        0
    )


def add_reason_shares(df, group_columns):
    """Add each reason's share within its product or branch."""
    result = df.copy()

    totals = (
        result.groupby(group_columns, dropna=False)["return_records"]
        .transform("sum")
    )

    result["reason_records_share_pct"] = safe_rate(
        result["return_records"],
        totals
    )

    return result


# ============================================================
# 3. LOAD DATA
# ============================================================

print("=" * 65)
print("RETURN ROOT CAUSE ANALYSIS")
print("=" * 65)

if not FACT_SALES_PATH.exists():
    raise FileNotFoundError(f"Fact Sales file not found: {FACT_SALES_PATH}")

if not FACT_RETURNS_PATH.exists():
    raise FileNotFoundError(f"Fact Returns file not found: {FACT_RETURNS_PATH}")

fact_sales = pd.read_csv(FACT_SALES_PATH, low_memory=False)
fact_returns = pd.read_csv(FACT_RETURNS_PATH, low_memory=False)

print(f"Fact Sales rows: {len(fact_sales):,}")
print(f"Fact Returns rows: {len(fact_returns):,}")


# ============================================================
# 4. VALIDATE REQUIRED COLUMNS
# ============================================================

require_columns(
    fact_sales,
    [
        "sales_line_id",
        "product_id",
        "branch_id",
        "quantity",
        "net_line_EGP"
    ],
    "fact_sales.csv"
)

require_columns(
    fact_returns,
    [
        "return_id",
        "sales_line_id",
        "return_quantity",
        "refund_amount_EGP",
        "reason"
    ],
    "fact_returns.csv"
)

if fact_sales["sales_line_id"].duplicated().any():
    raise ValueError("Duplicate sales_line_id found in fact_sales.")

if fact_returns["return_id"].duplicated().any():
    raise ValueError("Duplicate return_id found in fact_returns.")

if fact_returns["sales_line_id"].isna().any():
    raise ValueError("Null sales_line_id found in fact_returns.")


# ============================================================
# 5. PREPARE SALES LOOKUP
# ============================================================

# We use fact_sales as the source for product and branch information.
# Avoid selecting columns already present in fact_returns.
lookup_candidates = [
    "sales_line_id",
    "product_id",
    "branch_id",
    "quantity",
    "net_line_EGP",
    "order_date",
    "product_name_ar",
    "product_name",
    "branch_name"
]

lookup_columns = [
    col for col in lookup_candidates
    if col in fact_sales.columns
]

sales_lookup = fact_sales[lookup_columns].copy()

# Rename sales measures so they cannot be confused with return measures.
rename_map = {}

if "quantity" in sales_lookup.columns:
    rename_map["quantity"] = "sold_quantity"

if "net_line_EGP" in sales_lookup.columns:
    rename_map["net_line_EGP"] = "sales_net_line_EGP"

sales_lookup = sales_lookup.rename(columns=rename_map)

# Keep only columns that are not already in fact_returns.
# This prevents Pandas from creating product_id_x / product_id_y.
lookup_columns_to_add = [
    col for col in sales_lookup.columns
    if col == "sales_line_id" or col not in fact_returns.columns
]

sales_lookup = sales_lookup[lookup_columns_to_add]


# ============================================================
# 6. ENRICH RETURNS WITHOUT DUPLICATE COLUMN NAMES
# ============================================================

returns_enriched = fact_returns.merge(
    sales_lookup,
    on="sales_line_id",
    how="left",
    validate="many_to_one",
    indicator=True
)

unmatched_returns = int(
    (returns_enriched["_merge"] != "both").sum()
)

returns_enriched = returns_enriched.drop(columns=["_merge"])

if unmatched_returns > 0:
    raise ValueError(
        f"{unmatched_returns:,} return records could not be matched "
        "to fact_sales using sales_line_id."
    )

# Make sure product_id and branch_id are available.
require_columns(
    returns_enriched,
    ["product_id", "branch_id"],
    "enriched returns"
)

# Convert numeric fields.
for col in ["return_quantity", "refund_amount_EGP"]:
    returns_enriched[col] = pd.to_numeric(
        returns_enriched[col],
        errors="coerce"
    )

if returns_enriched["return_quantity"].isna().any():
    raise ValueError("Invalid or missing return_quantity values found.")

if returns_enriched["refund_amount_EGP"].isna().any():
    raise ValueError("Invalid or missing refund_amount_EGP values found.")

if (returns_enriched["return_quantity"] < 0).any():
    raise ValueError("Negative return_quantity values found.")

if (returns_enriched["refund_amount_EGP"] < 0).any():
    raise ValueError("Negative refund_amount_EGP values found.")

print("Return-to-sales matching: PASS")
print(f"Unmatched return records: {unmatched_returns:,}")


# ============================================================
# 7. BUILD SALES DENOMINATORS
# ============================================================

product_sales = (
    fact_sales.groupby("product_id", dropna=False)
    .agg(
        sold_quantity=("quantity", "sum"),
        sales_lines=("sales_line_id", "nunique"),
        net_sales_EGP=("net_line_EGP", "sum")
    )
    .reset_index()
)

branch_sales = (
    fact_sales.groupby("branch_id", dropna=False)
    .agg(
        sold_quantity=("quantity", "sum"),
        sales_lines=("sales_line_id", "nunique"),
        net_sales_EGP=("net_line_EGP", "sum")
    )
    .reset_index()
)

product_branch_sales = (
    fact_sales.groupby(
        ["product_id", "branch_id"],
        dropna=False
    )
    .agg(
        sold_quantity=("quantity", "sum"),
        sales_lines=("sales_line_id", "nunique"),
        net_sales_EGP=("net_line_EGP", "sum")
    )
    .reset_index()
)


# ============================================================
# 8. RETURN REASONS BY PRODUCT
# ============================================================

product_reason = (
    returns_enriched.groupby(
        ["product_id", "reason"],
        dropna=False
    )
    .agg(
        return_records=("return_id", "nunique"),
        returned_quantity=("return_quantity", "sum"),
        refund_amount_EGP=("refund_amount_EGP", "sum")
    )
    .reset_index()
)

product_reason = add_reason_shares(
    product_reason,
    ["product_id"]
)

product_reason = product_reason.merge(
    product_sales,
    on="product_id",
    how="left",
    validate="many_to_one"
)

product_reason["quantity_return_rate_pct"] = safe_rate(
    product_reason["returned_quantity"],
    product_reason["sold_quantity"]
)

product_reason["refund_to_net_sales_pct"] = safe_rate(
    product_reason["refund_amount_EGP"],
    product_reason["net_sales_EGP"]
)

save_report(
    product_reason.sort_values(
        "returned_quantity",
        ascending=False
    ),
    "44_return_reasons_by_product.csv"
)


# ============================================================
# 9. RETURN REASONS BY BRANCH
# ============================================================

branch_reason = (
    returns_enriched.groupby(
        ["branch_id", "reason"],
        dropna=False
    )
    .agg(
        return_records=("return_id", "nunique"),
        returned_quantity=("return_quantity", "sum"),
        refund_amount_EGP=("refund_amount_EGP", "sum")
    )
    .reset_index()
)

branch_reason = add_reason_shares(
    branch_reason,
    ["branch_id"]
)

branch_reason = branch_reason.merge(
    branch_sales,
    on="branch_id",
    how="left",
    validate="many_to_one"
)

branch_reason["quantity_return_rate_pct"] = safe_rate(
    branch_reason["returned_quantity"],
    branch_reason["sold_quantity"]
)

branch_reason["refund_to_net_sales_pct"] = safe_rate(
    branch_reason["refund_amount_EGP"],
    branch_reason["net_sales_EGP"]
)

save_report(
    branch_reason.sort_values(
        "returned_quantity",
        ascending=False
    ),
    "45_return_reasons_by_branch.csv"
)


# ============================================================
# 10. PRODUCT RETURN ROOT CAUSE
# ============================================================

product_totals = (
    returns_enriched.groupby("product_id", dropna=False)
    .agg(
        return_records=("return_id", "nunique"),
        returned_quantity=("return_quantity", "sum"),
        refund_amount_EGP=("refund_amount_EGP", "sum")
    )
    .reset_index()
)

product_root_cause = product_sales.merge(
    product_totals,
    on="product_id",
    how="left",
    validate="one_to_one"
)

product_root_cause[
    ["return_records", "returned_quantity", "refund_amount_EGP"]
] = product_root_cause[
    ["return_records", "returned_quantity", "refund_amount_EGP"]
].fillna(0)

product_root_cause["quantity_return_rate_pct"] = safe_rate(
    product_root_cause["returned_quantity"],
    product_root_cause["sold_quantity"]
)

product_root_cause["refund_to_net_sales_pct"] = safe_rate(
    product_root_cause["refund_amount_EGP"],
    product_root_cause["net_sales_EGP"]
)

# Find the most frequent return reason for each product.
product_top_reason = (
    product_reason.sort_values(
        ["product_id", "return_records"],
        ascending=[True, False]
    )
    .drop_duplicates("product_id")
    [["product_id", "reason", "return_records"]]
    .rename(
        columns={
            "reason": "top_return_reason",
            "return_records": "top_reason_records"
        }
    )
)

product_root_cause = product_root_cause.merge(
    product_top_reason,
    on="product_id",
    how="left",
    validate="one_to_one"
)

save_report(
    product_root_cause.sort_values(
        "quantity_return_rate_pct",
        ascending=False
    ),
    "46_product_return_root_cause.csv"
)


# ============================================================
# 11. BRANCH RETURN ROOT CAUSE
# ============================================================

branch_totals = (
    returns_enriched.groupby("branch_id", dropna=False)
    .agg(
        return_records=("return_id", "nunique"),
        returned_quantity=("return_quantity", "sum"),
        refund_amount_EGP=("refund_amount_EGP", "sum")
    )
    .reset_index()
)

branch_root_cause = branch_sales.merge(
    branch_totals,
    on="branch_id",
    how="left",
    validate="one_to_one"
)

branch_root_cause[
    ["return_records", "returned_quantity", "refund_amount_EGP"]
] = branch_root_cause[
    ["return_records", "returned_quantity", "refund_amount_EGP"]
].fillna(0)

branch_root_cause["quantity_return_rate_pct"] = safe_rate(
    branch_root_cause["returned_quantity"],
    branch_root_cause["sold_quantity"]
)

branch_root_cause["refund_to_net_sales_pct"] = safe_rate(
    branch_root_cause["refund_amount_EGP"],
    branch_root_cause["net_sales_EGP"]
)

branch_top_reason = (
    branch_reason.sort_values(
        ["branch_id", "return_records"],
        ascending=[True, False]
    )
    .drop_duplicates("branch_id")
    [["branch_id", "reason", "return_records"]]
    .rename(
        columns={
            "reason": "top_return_reason",
            "return_records": "top_reason_records"
        }
    )
)

branch_root_cause = branch_root_cause.merge(
    branch_top_reason,
    on="branch_id",
    how="left",
    validate="one_to_one"
)

save_report(
    branch_root_cause.sort_values(
        "quantity_return_rate_pct",
        ascending=False
    ),
    "47_branch_return_root_cause.csv"
)


# ============================================================
# 12. PRODUCT-BRANCH HOTSPOTS
# ============================================================

product_branch_returns = (
    returns_enriched.groupby(
        ["product_id", "branch_id"],
        dropna=False
    )
    .agg(
        return_records=("return_id", "nunique"),
        returned_quantity=("return_quantity", "sum"),
        refund_amount_EGP=("refund_amount_EGP", "sum")
    )
    .reset_index()
)

hotspots = product_branch_sales.merge(
    product_branch_returns,
    on=["product_id", "branch_id"],
    how="left",
    validate="one_to_one"
)

hotspots[
    ["return_records", "returned_quantity", "refund_amount_EGP"]
] = hotspots[
    ["return_records", "returned_quantity", "refund_amount_EGP"]
].fillna(0)

hotspots["quantity_return_rate_pct"] = safe_rate(
    hotspots["returned_quantity"],
    hotspots["sold_quantity"]
)

hotspots["refund_to_net_sales_pct"] = safe_rate(
    hotspots["refund_amount_EGP"],
    hotspots["net_sales_EGP"]
)

save_report(
    hotspots.sort_values(
        ["quantity_return_rate_pct", "returned_quantity"],
        ascending=[False, False]
    ),
    "48_product_branch_return_hotspots.csv"
)


# ============================================================
# 13. OVERALL RETURN REASON SUMMARY
# ============================================================

overall_reason = (
    returns_enriched.groupby("reason", dropna=False)
    .agg(
        return_records=("return_id", "nunique"),
        returned_quantity=("return_quantity", "sum"),
        refund_amount_EGP=("refund_amount_EGP", "sum")
    )
    .reset_index()
)

total_return_records = overall_reason["return_records"].sum()
total_return_quantity = overall_reason["returned_quantity"].sum()
total_refunds = overall_reason["refund_amount_EGP"].sum()

overall_reason["records_share_pct"] = safe_rate(
    overall_reason["return_records"],
    total_return_records
)

overall_reason["quantity_share_pct"] = safe_rate(
    overall_reason["returned_quantity"],
    total_return_quantity
)

overall_reason["refund_share_pct"] = safe_rate(
    overall_reason["refund_amount_EGP"],
    total_refunds
)

save_report(
    overall_reason.sort_values(
        "return_records",
        ascending=False
    ),
    "50_overall_return_reason_summary.csv"
)


# ============================================================
# 14. CUMULATIVE RETURN QUANTITY ANOMALIES
# ============================================================

returned_by_line = (
    returns_enriched.groupby("sales_line_id", dropna=False)
    .agg(
        cumulative_return_quantity=("return_quantity", "sum"),
        return_records=("return_id", "nunique")
    )
    .reset_index()
)

sold_by_line = fact_sales[
    ["sales_line_id", "quantity"]
].rename(
    columns={"quantity": "sold_quantity"}
)

line_check = sold_by_line.merge(
    returned_by_line,
    on="sales_line_id",
    how="left",
    validate="one_to_one"
)

line_check[
    ["cumulative_return_quantity", "return_records"]
] = line_check[
    ["cumulative_return_quantity", "return_records"]
].fillna(0)

anomalies = line_check[
    line_check["cumulative_return_quantity"]
    > line_check["sold_quantity"]
].copy()

save_report(
    anomalies,
    "51_cumulative_return_quantity_anomalies.csv"
)


# ============================================================
# 15. DATA QUALITY SUMMARY
# ============================================================

quality_summary = pd.DataFrame(
    [
        {
            "check": "fact_sales_rows",
            "value": len(fact_sales),
            "status": "INFO"
        },
        {
            "check": "fact_returns_rows",
            "value": len(fact_returns),
            "status": "INFO"
        },
        {
            "check": "unique_sales_line_ids",
            "value": fact_sales["sales_line_id"].nunique(),
            "status": (
                "PASS"
                if fact_sales["sales_line_id"].is_unique
                else "FAIL"
            )
        },
        {
            "check": "unique_return_ids",
            "value": fact_returns["return_id"].nunique(),
            "status": (
                "PASS"
                if fact_returns["return_id"].is_unique
                else "FAIL"
            )
        },
        {
            "check": "unmatched_return_records",
            "value": unmatched_returns,
            "status": "PASS" if unmatched_returns == 0 else "FAIL"
        },
        {
            "check": "negative_return_quantity",
            "value": int(
                (returns_enriched["return_quantity"] < 0).sum()
            ),
            "status": "PASS"
        },
        {
            "check": "negative_refund_amount",
            "value": int(
                (returns_enriched["refund_amount_EGP"] < 0).sum()
            ),
            "status": "PASS"
        },
        {
            "check": "cumulative_return_qty_exceeds_sold_qty",
            "value": len(anomalies),
            "status": "PASS" if len(anomalies) == 0 else "CHECK"
        },
        {
            "check": "null_product_id_in_returns",
            "value": int(returns_enriched["product_id"].isna().sum()),
            "status": (
                "PASS"
                if returns_enriched["product_id"].notna().all()
                else "CHECK"
            )
        },
        {
            "check": "null_branch_id_in_returns",
            "value": int(returns_enriched["branch_id"].isna().sum()),
            "status": (
                "PASS"
                if returns_enriched["branch_id"].notna().all()
                else "CHECK"
            )
        }
    ]
)

save_report(
    quality_summary,
    "49_return_data_quality_summary.csv"
)


# ============================================================
# 16. FINAL CONSOLE SUMMARY
# ============================================================

print("\n" + "=" * 65)
print("RETURN ROOT CAUSE ANALYSIS - COMPLETED")
print("=" * 65)

print(f"Fact Sales rows: {len(fact_sales):,}")
print(f"Fact Returns rows: {len(fact_returns):,}")

print(f"Total returned quantity: {total_return_quantity:,.0f}")
print(f"Total refund amount: {total_refunds:,.2f} EGP")

print(f"Products analyzed: {product_sales['product_id'].nunique():,}")
print(f"Branches analyzed: {branch_sales['branch_id'].nunique():,}")

print(f"Product-reason groups: {len(product_reason):,}")
print(f"Branch-reason groups: {len(branch_reason):,}")
print(f"Product-branch combinations: {len(hotspots):,}")

print(f"Cumulative return quantity anomalies: {len(anomalies):,}")

print("\nTop 10 products by quantity return rate:")
print(
    product_root_cause.sort_values(
        "quantity_return_rate_pct",
        ascending=False
    )[
        [
            "product_id",
            "sold_quantity",
            "returned_quantity",
            "quantity_return_rate_pct",
            "refund_amount_EGP"
        ]
    ].head(10).to_string(index=False)
)

print("\nTop 10 branches by quantity return rate:")
print(
    branch_root_cause.sort_values(
        "quantity_return_rate_pct",
        ascending=False
    )[
        [
            "branch_id",
            "sold_quantity",
            "returned_quantity",
            "quantity_return_rate_pct",
            "refund_amount_EGP"
        ]
    ].head(10).to_string(index=False)
)

print("\nReturn reasons summary:")
print(
    overall_reason.sort_values(
        "return_records",
        ascending=False
    ).to_string(index=False)
)

print("\nAll reports saved in:")
print(REPORTS_DIR)

print("\n" + "=" * 65)
print("PROCESS FINISHED SUCCESSFULLY")
print("=" * 65)
