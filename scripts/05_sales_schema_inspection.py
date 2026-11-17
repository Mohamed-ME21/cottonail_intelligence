
from pathlib import Path
import pandas as pd

# ==================================================
# 1. Project paths
# ==================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
REPORT_DIR = BASE_DIR / "reports"

REPORT_DIR.mkdir(parents=True, exist_ok=True)

FILES = {
    "sales_orders": DATA_DIR / "sales_orders.csv",
    "sales_order_items": DATA_DIR / "sales_order_items.csv",
}

# ==================================================
# 2. Load tables
# ==================================================

tables = {}

for table_name, file_path in FILES.items():
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    print(f"\nLoading {table_name} ...")

    tables[table_name] = pd.read_csv(
        file_path,
        low_memory=False
    )

# ==================================================
# 3. Inspect columns and data types
# ==================================================

schema_rows = []

for table_name, df in tables.items():

    print("\n" + "=" * 70)
    print(f"TABLE: {table_name}")
    print("=" * 70)

    print(f"Rows: {len(df):,}")
    print(f"Columns: {len(df.columns)}")

    for col in df.columns:

        schema_rows.append({
            "table_name": table_name,
            "column_name": col,
            "data_type": str(df[col].dtype),
            "null_count": int(df[col].isna().sum()),
            "null_percent": round(
                df[col].isna().mean() * 100, 2
            ),
            "unique_count": int(df[col].nunique(dropna=True))
        })

        print(
            f"{col:35} "
            f"type={str(df[col].dtype):12} "
            f"nulls={df[col].isna().sum():>10,} "
            f"unique={df[col].nunique():>10,}"
        )

schema_report = pd.DataFrame(schema_rows)

schema_report.to_csv(
    REPORT_DIR / "21_sales_schema.csv",
    index=False,
    encoding="utf-8-sig"
)

# ==================================================
# 4. Inspect numeric columns
# ==================================================

numeric_rows = []

for table_name, df in tables.items():

    print(f"\nNUMERIC PROFILE: {table_name}")

    numeric_cols = df.select_dtypes(
        include="number"
    ).columns

    for col in numeric_cols:

        series = df[col]

        result = {
            "table_name": table_name,
            "column_name": col,
            "min": series.min(),
            "max": series.max(),
            "mean": series.mean(),
            "median": series.median(),
            "zero_count": int((series == 0).sum()),
            "negative_count": int((series < 0).sum()),
            "null_count": int(series.isna().sum())
        }

        numeric_rows.append(result)

        print(
            f"{col:35} "
            f"min={series.min()} | "
            f"max={series.max()} | "
            f"mean={series.mean():.2f}"
        )

pd.DataFrame(numeric_rows).to_csv(
    REPORT_DIR / "22_sales_numeric_profile.csv",
    index=False,
    encoding="utf-8-sig"
)

# ==================================================
# 5. Inspect key columns
# ==================================================

orders = tables["sales_orders"]
items = tables["sales_order_items"]

key_checks = []

def add_key_check(table_name, column_name, df):

    if column_name not in df.columns:
        return

    series = df[column_name]

    key_checks.append({
        "table_name": table_name,
        "column_name": column_name,
        "row_count": len(df),
        "null_count": int(series.isna().sum()),
        "unique_count": int(series.nunique()),
        "duplicate_non_null_count": int(
            series.dropna().duplicated().sum()
        )
    })

add_key_check(
    "sales_orders",
    "sales_order_id",
    orders
)

add_key_check(
    "sales_order_items",
    "sales_line_id",
    items
)

add_key_check(
    "sales_order_items",
    "sales_order_id",
    items
)

pd.DataFrame(key_checks).to_csv(
    REPORT_DIR / "23_sales_key_checks.csv",
    index=False,
    encoding="utf-8-sig"
)

# ==================================================
# 6. Check order-to-lines structure
# ==================================================

if (
    "sales_order_id" in orders.columns
    and "sales_order_id" in items.columns
):

    lines_per_order = (
        items.groupby("sales_order_id")
        .size()
        .rename("line_count")
    )

    order_line_summary = {
        "orders_in_orders_table": len(orders),
        "orders_with_lines": int(lines_per_order.size),
        "orders_without_lines": int(
            orders["sales_order_id"].nunique()
            - lines_per_order.size
        ),
        "total_order_lines": len(items),
        "minimum_lines_per_order": int(lines_per_order.min()),
        "maximum_lines_per_order": int(lines_per_order.max()),
        "average_lines_per_order": round(
            lines_per_order.mean(), 2
        ),
        "orders_with_multiple_lines": int(
            (lines_per_order > 1).sum()
        )
    }

    pd.DataFrame(
        [order_line_summary]
    ).to_csv(
        REPORT_DIR / "24_order_line_structure.csv",
        index=False,
        encoding="utf-8-sig"
    )

    print("\nORDER / LINE STRUCTURE")
    for key, value in order_line_summary.items():
        print(f"{key}: {value:,}" if isinstance(value, int)
              else f"{key}: {value}")

# ==================================================
# 7. Show sample records
# ==================================================

for table_name, df in tables.items():

    sample = df.head(5)

    sample.to_csv(
        REPORT_DIR / f"25_{table_name}_sample.csv",
        index=False,
        encoding="utf-8-sig"
    )

    print(f"\nSAMPLE: {table_name}")
    print(sample.to_string(index=False))

# ==================================================
# 8. Candidate business measure columns
# ==================================================

keywords = [
    "qty", "quantity", "price", "amount",
    "gross", "net", "discount", "tax",
    "total", "cost", "revenue", "subtotal"
]

print("\n" + "=" * 70)
print("POTENTIAL BUSINESS MEASURE COLUMNS")
print("=" * 70)

for table_name, df in tables.items():

    candidates = [
        col for col in df.columns
        if any(word in col.lower() for word in keywords)
    ]

    print(f"\n{table_name}:")
    for col in candidates:
        print(f"  - {col}")

print("\nINSPECTION COMPLETE")
print(f"Reports saved in: {REPORT_DIR}")
