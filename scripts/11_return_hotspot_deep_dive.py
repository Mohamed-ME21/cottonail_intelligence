
from pathlib import Path
import pandas as pd
import numpy as np

# ============================================================
# 1. PATHS AND SETTINGS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
REPORTS_DIR = BASE_DIR / "reports"

FACT_SALES_PATH = PROCESSED_DIR / "fact_sales.csv"
FACT_RETURNS_PATH = PROCESSED_DIR / "fact_returns.csv"

REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Analytical threshold, not a business rule.
MIN_SOLD_QUANTITY = 100

# Number of hotspots to display in the console.
TOP_N = 20


# ============================================================
# 2. HELPER FUNCTIONS
# ============================================================

def require_columns(df, columns, file_name):
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise ValueError(
            f"Missing columns in {file_name}: {missing}\n"
            f"Available columns: {df.columns.tolist()}"
        )


def save_report(df, filename):
    path = REPORTS_DIR / filename
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"Saved: {path}")


def safe_rate(numerator, denominator):
    numerator = np.asarray(numerator, dtype=float)
    denominator = np.asarray(denominator, dtype=float)

    return np.divide(
        numerator * 100,
        denominator,
        out=np.zeros_like(numerator, dtype=float),
        where=denominator != 0
    )


def safe_divide(numerator, denominator):
    numerator = np.asarray(numerator, dtype=float)
    denominator = np.asarray(denominator, dtype=float)

    return np.divide(
        numerator,
        denominator,
        out=np.zeros_like(numerator, dtype=float),
        where=denominator != 0
    )


# ============================================================
# 3. LOAD DATA
# ============================================================

print("=" * 70)
print("RETURN HOTSPOT DEEP DIVE")
print("=" * 70)

if not FACT_SALES_PATH.exists():
    raise FileNotFoundError(FACT_SALES_PATH)

if not FACT_RETURNS_PATH.exists():
    raise FileNotFoundError(FACT_RETURNS_PATH)

fact_sales = pd.read_csv(FACT_SALES_PATH, low_memory=False)
fact_returns = pd.read_csv(FACT_RETURNS_PATH, low_memory=False)

print(f"Fact Sales rows: {len(fact_sales):,}")
print(f"Fact Returns rows: {len(fact_returns):,}")
print(f"Minimum sold quantity threshold: {MIN_SOLD_QUANTITY:,}")


# ============================================================
# 4. VALIDATE INPUTS
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
    raise ValueError("Duplicate sales_line_id in fact_sales.")

if fact_returns["return_id"].duplicated().any():
    raise ValueError("Duplicate return_id in fact_returns.")

if fact_returns["sales_line_id"].isna().any():
    raise ValueError("Null sales_line_id in fact_returns.")

for col in ["quantity", "net_line_EGP"]:
    fact_sales[col] = pd.to_numeric(
        fact_sales[col],
        errors="coerce"
    )

for col in ["return_quantity", "refund_amount_EGP"]:
    fact_returns[col] = pd.to_numeric(
        fact_returns[col],
        errors="coerce"
    )

if fact_sales[["quantity", "net_line_EGP"]].isna().any().any():
    raise ValueError("Invalid numeric sales values found.")

if fact_returns[
    ["return_quantity", "refund_amount_EGP"]
].isna().any().any():
    raise ValueError("Invalid numeric return values found.")

if (fact_sales["quantity"] < 0).any():
    raise ValueError("Negative sales quantity found.")

if (fact_returns["return_quantity"] < 0).any():
    raise ValueError("Negative return quantity found.")

if (fact_returns["refund_amount_EGP"] < 0).any():
    raise ValueError("Negative refund amount found.")



# ============================================================
# 5. BUILD SALES LOOKUP AND ENRICH RETURNS
# ============================================================

# Check whether product_id and branch_id already exist
# in fact_returns. If they exist, do not merge them again.

required_lookup_columns = [
    "sales_line_id",
    "product_id",
    "branch_id"
]

sales_lookup = fact_sales[required_lookup_columns].copy()

# Keep only the sales columns missing from fact_returns.
columns_to_add = [
    "sales_line_id"
]

for col in ["product_id", "branch_id"]:
    if col not in fact_returns.columns:
        columns_to_add.append(col)

sales_lookup = sales_lookup[columns_to_add]

# If product_id and branch_id already exist in fact_returns,
# preserve them and validate that they match fact_sales.
if (
    "product_id" in fact_returns.columns
    and "branch_id" in fact_returns.columns
):
    validation_lookup = fact_sales[
        ["sales_line_id", "product_id", "branch_id"]
    ].copy()

    returns = fact_returns.merge(
        validation_lookup,
        on="sales_line_id",
        how="left",
        validate="many_to_one",
        suffixes=("", "_sales"),
        indicator=True
    )

    unmatched_returns = int(
        (returns["_merge"] != "both").sum()
    )

    if unmatched_returns > 0:
        raise ValueError(
            f"Unmatched returns: {unmatched_returns:,}"
        )

    product_mismatch = (
        returns["product_id"].astype(str)
        != returns["product_id_sales"].astype(str)
    ).sum()

    branch_mismatch = (
        returns["branch_id"].astype(str)
        != returns["branch_id_sales"].astype(str)
    ).sum()

    if product_mismatch > 0:
        raise ValueError(
            f"Product ID mismatches: {product_mismatch:,}"
        )

    if branch_mismatch > 0:
        raise ValueError(
            f"Branch ID mismatches: {branch_mismatch:,}"
        )

    returns = returns.drop(
        columns=[
            "_merge",
            "product_id_sales",
            "branch_id_sales"
        ]
    )

else:
    # Add only missing dimension columns.
    returns = fact_returns.merge(
        sales_lookup,
        on="sales_line_id",
        how="left",
        validate="many_to_one",
        indicator=True
    )

    unmatched_returns = int(
        (returns["_merge"] != "both").sum()
    )

    returns = returns.drop(columns=["_merge"])

    if unmatched_returns > 0:
        raise ValueError(
            f"Unmatched returns: {unmatched_returns:,}"
        )

require_columns(
    returns,
    ["product_id", "branch_id"],
    "enriched returns"
)

if returns["product_id"].isna().any():
    raise ValueError("Some returns have no product_id.")

if returns["branch_id"].isna().any():
    raise ValueError("Some returns have no branch_id.")

print("Return-to-sales matching: PASS")
print(f"Unmatched returns: {unmatched_returns:,}")
print("Product ID consistency: PASS")
print("Branch ID consistency: PASS")



# ============================================================
# 6. SALES BY PRODUCT + BRANCH
# ============================================================

sales_group = (
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


# Optional product and branch names.
product_name_col = next(
    (
        col for col in ["product_name_ar", "product_name"]
        if col in fact_sales.columns
    ),
    None
)

if product_name_col:
    product_names = (
        fact_sales[["product_id", product_name_col]]
        .dropna(subset=["product_id"])
        .drop_duplicates("product_id")
    )

    if product_names["product_id"].duplicated().any():
        raise ValueError(
            "A product_id has multiple product names in fact_sales."
        )

    sales_group = sales_group.merge(
        product_names,
        on="product_id",
        how="left",
        validate="many_to_one"
    )

branch_name_col = (
    "branch_name"
    if "branch_name" in fact_sales.columns
    else None
)

if branch_name_col:
    branch_names = (
        fact_sales[["branch_id", branch_name_col]]
        .dropna(subset=["branch_id"])
        .drop_duplicates("branch_id")
    )

    if branch_names["branch_id"].duplicated().any():
        raise ValueError(
            "A branch_id has multiple branch names in fact_sales."
        )

    sales_group = sales_group.merge(
        branch_names,
        on="branch_id",
        how="left",
        validate="many_to_one"
    )


# ============================================================
# 7. RETURNS BY PRODUCT + BRANCH
# ============================================================

returns_group = (
    returns.groupby(
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


# ============================================================
# 8. BUILD HOTSPOT MASTER TABLE
# ============================================================

hotspots = sales_group.merge(
    returns_group,
    on=["product_id", "branch_id"],
    how="left",
    validate="one_to_one"
)

for col in [
    "return_records",
    "returned_quantity",
    "refund_amount_EGP"
]:
    hotspots[col] = hotspots[col].fillna(0)

hotspots["quantity_return_rate_pct"] = safe_rate(
    hotspots["returned_quantity"],
    hotspots["sold_quantity"]
)

hotspots["refund_to_net_sales_pct"] = safe_rate(
    hotspots["refund_amount_EGP"],
    hotspots["net_sales_EGP"]
)

hotspots["refund_per_returned_unit_EGP"] = safe_divide(
    hotspots["refund_amount_EGP"],
    hotspots["returned_quantity"]
)

# Overall benchmark across the complete dataset.
overall_sold_quantity = fact_sales["quantity"].sum()
overall_returned_quantity = returns["return_quantity"].sum()

overall_return_rate_pct = (
    overall_returned_quantity / overall_sold_quantity * 100
    if overall_sold_quantity > 0
    else 0
)

hotspots["overall_return_rate_pct"] = overall_return_rate_pct

hotspots["expected_returned_quantity_at_overall_rate"] = (
    hotspots["sold_quantity"] * overall_return_rate_pct / 100
)

hotspots["excess_returned_quantity_vs_overall"] = (
    hotspots["returned_quantity"]
    - hotspots["expected_returned_quantity_at_overall_rate"]
)

hotspots["above_overall_return_rate"] = (
    hotspots["quantity_return_rate_pct"]
    > overall_return_rate_pct
)

hotspots["meets_minimum_volume"] = (
    hotspots["sold_quantity"] >= MIN_SOLD_QUANTITY
)

hotspots["eligible_hotspot"] = (
    hotspots["meets_minimum_volume"]
    & hotspots["above_overall_return_rate"]
)

# Rank all product-branch combinations.
hotspots["return_rate_rank"] = (
    hotspots["quantity_return_rate_pct"]
    .rank(method="min", ascending=False)
    .astype(int)
)

hotspots["returned_quantity_rank"] = (
    hotspots["returned_quantity"]
    .rank(method="min", ascending=False)
    .astype(int)
)

hotspots["excess_return_quantity_rank"] = (
    hotspots["excess_returned_quantity_vs_overall"]
    .rank(method="min", ascending=False)
    .astype(int)
)


# ============================================================
# 9. SAVE FULL HOTSPOT RANKING
# ============================================================

hotspots_ranked = hotspots.sort_values(
    [
        "eligible_hotspot",
        "excess_returned_quantity_vs_overall",
        "quantity_return_rate_pct",
        "returned_quantity"
    ],
    ascending=[False, False, False, False]
)

save_report(
    hotspots_ranked,
    "52_product_branch_hotspots_ranked.csv"
)


# ============================================================
# 10. ELIGIBLE HOTSPOTS
# ============================================================

eligible_hotspots = hotspots[
    hotspots["eligible_hotspot"]
].copy()

eligible_hotspots = eligible_hotspots.sort_values(
    [
        "excess_returned_quantity_vs_overall",
        "quantity_return_rate_pct",
        "returned_quantity"
    ],
    ascending=[False, False, False]
)

save_report(
    eligible_hotspots,
    "53_eligible_return_hotspots.csv"
)


# ============================================================
# 11. RETURN REASONS BY PRODUCT + BRANCH
# ============================================================

reason_breakdown = (
    returns.groupby(
        ["product_id", "branch_id", "reason"],
        dropna=False
    )
    .agg(
        reason_return_records=("return_id", "nunique"),
        reason_returned_quantity=("return_quantity", "sum"),
        reason_refund_amount_EGP=("refund_amount_EGP", "sum")
    )
    .reset_index()
)

# Merge only eligible hotspots to keep the detailed report focused.
eligible_keys = eligible_hotspots[
    [
        "product_id",
        "branch_id",
        "sold_quantity",
        "returned_quantity",
        "refund_amount_EGP",
        "quantity_return_rate_pct",
        "refund_to_net_sales_pct",
        "excess_returned_quantity_vs_overall"
    ]
].copy()

reason_breakdown = reason_breakdown.merge(
    eligible_keys,
    on=["product_id", "branch_id"],
    how="inner",
    validate="many_to_one"
)

reason_breakdown["reason_records_share_pct"] = safe_rate(
    reason_breakdown["reason_return_records"],
    reason_breakdown.groupby(
        ["product_id", "branch_id"]
    )["reason_return_records"].transform("sum")
)

reason_breakdown["reason_quantity_share_pct"] = safe_rate(
    reason_breakdown["reason_returned_quantity"],
    reason_breakdown.groupby(
        ["product_id", "branch_id"]
    )["reason_returned_quantity"].transform("sum")
)

reason_breakdown["reason_refund_share_pct"] = safe_rate(
    reason_breakdown["reason_refund_amount_EGP"],
    reason_breakdown.groupby(
        ["product_id", "branch_id"]
    )["reason_refund_amount_EGP"].transform("sum")
)

reason_breakdown = reason_breakdown.sort_values(
    [
        "excess_returned_quantity_vs_overall",
        "reason_returned_quantity"
    ],
    ascending=[False, False]
)

save_report(
    reason_breakdown,
    "54_hotspot_reason_breakdown.csv"
)


# ============================================================
# 12. TOP REASON PER HOTSPOT
# ============================================================

if len(reason_breakdown) > 0:
    top_reason = (
        reason_breakdown.sort_values(
            [
                "product_id",
                "branch_id",
                "reason_returned_quantity",
                "reason_return_records"
            ],
            ascending=[True, True, False, False]
        )
        .drop_duplicates(["product_id", "branch_id"])
        .copy()
    )
else:
    top_reason = pd.DataFrame(
        columns=[
            "product_id",
            "branch_id",
            "reason",
            "reason_return_records",
            "reason_returned_quantity",
            "reason_refund_amount_EGP",
            "reason_records_share_pct",
            "reason_quantity_share_pct",
            "reason_refund_share_pct"
        ]
    )

save_report(
    top_reason,
    "55_hotspot_top_reason.csv"
)


# ============================================================
# 13. ACTION CANDIDATES
# ============================================================

action_candidates = eligible_hotspots.merge(
    top_reason[
        [
            "product_id",
            "branch_id",
            "reason",
            "reason_return_records",
            "reason_returned_quantity",
            "reason_quantity_share_pct"
        ]
    ].rename(
        columns={
            "reason": "top_return_reason",
            "reason_return_records": "top_reason_records",
            "reason_returned_quantity": "top_reason_returned_quantity",
            "reason_quantity_share_pct": "top_reason_quantity_share_pct"
        }
    ),
    on=["product_id", "branch_id"],
    how="left",
    validate="one_to_one"
)

action_candidates["investigation_priority"] = np.select(
    [
        action_candidates["excess_returned_quantity_vs_overall"] > 10,
        action_candidates["excess_returned_quantity_vs_overall"] > 0
    ],
    [
        "High",
        "Review"
    ],
    default="Monitor"
)

action_candidates = action_candidates.sort_values(
    [
        "excess_returned_quantity_vs_overall",
        "quantity_return_rate_pct"
    ],
    ascending=[False, False]
)

save_report(
    action_candidates,
    "56_return_hotspot_action_candidates.csv"
)


# ============================================================
# 14. QUALITY AND RECONCILIATION CHECKS
# ============================================================

sales_pair_quantity = sales_group["sold_quantity"].sum()
sales_total_quantity = fact_sales["quantity"].sum()

returns_pair_quantity = returns_group["returned_quantity"].sum()
returns_total_quantity = returns["return_quantity"].sum()

checks = [
    {
        "check": "unmatched_return_records",
        "value": unmatched_returns,
        "status": "PASS" if unmatched_returns == 0 else "FAIL"
    },
    {
        "check": "sales_quantity_reconciliation",
        "value": sales_pair_quantity - sales_total_quantity,
        "status": (
            "PASS"
            if np.isclose(sales_pair_quantity, sales_total_quantity)
            else "FAIL"
        )
    },
    {
        "check": "return_quantity_reconciliation",
        "value": returns_pair_quantity - returns_total_quantity,
        "status": (
            "PASS"
            if np.isclose(returns_pair_quantity, returns_total_quantity)
            else "FAIL"
        )
    },
    {
        "check": "product_branch_sales_combinations",
        "value": len(sales_group),
        "status": "INFO"
    },
    {
        "check": "eligible_hotspots",
        "value": len(eligible_hotspots),
        "status": "INFO"
    },
    {
        "check": "hotspots_with_reason",
        "value": len(top_reason),
        "status": "INFO"
    },
    {
        "check": "overall_quantity_return_rate_pct",
        "value": overall_return_rate_pct,
        "status": "INFO"
    },
    {
        "check": "minimum_sold_quantity_threshold",
        "value": MIN_SOLD_QUANTITY,
        "status": "INFO"
    }
]

quality_report = pd.DataFrame(checks)

save_report(
    quality_report,
    "57_hotspot_deep_dive_quality_checks.csv"
)

if (quality_report["status"] == "FAIL").any():
    raise ValueError(
        "One or more reconciliation checks failed. "
        "Review report 57 before interpreting the results."
    )


# ============================================================
# 15. CONSOLE SUMMARY
# ============================================================

print("\n" + "=" * 70)
print("HOTSPOT DEEP DIVE - SUMMARY")
print("=" * 70)

print(f"Total product-branch combinations: {len(hotspots):,}")
print(f"Overall quantity return rate: {overall_return_rate_pct:.4f}%")
print(f"Eligible hotspots: {len(eligible_hotspots):,}")
print(f"Hotspots with reason details: {len(top_reason):,}")

print("\nTop 20 hotspots by excess returned quantity:")

display_columns = [
    "product_id",
    "branch_id",
    "sold_quantity",
    "returned_quantity",
    "quantity_return_rate_pct",
    "excess_returned_quantity_vs_overall"
]

if len(action_candidates) > 0:
    print(
        action_candidates[display_columns].head(TOP_N).to_string(
            index=False
        )
    )
else:
    print("No eligible hotspots found with the current threshold.")

print("\nTop reasons in eligible hotspots:")

if len(top_reason) > 0:
    print(
        top_reason[
            [
                "product_id",
                "branch_id",
                "reason",
                "reason_returned_quantity",
                "reason_quantity_share_pct"
            ]
        ].head(TOP_N).to_string(index=False)
    )
else:
    print("No reason details available for eligible hotspots.")

print("\nQuality checks:")
print(quality_report.to_string(index=False))

print("\nReports saved in:")
print(REPORTS_DIR)

print("\n" + "=" * 70)
print("PROCESS FINISHED SUCCESSFULLY")
print("=" * 70)
