
from pathlib import Path
import pandas as pd
import numpy as np

# ==========================================
# CONFIGURATION
# ==========================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
REPORT_DIR = BASE_DIR / "reports"

REPORT_DIR.mkdir(exist_ok=True)


# ==========================================
# SAFE CSV LOADER
# ==========================================

def load_table(name):

    path = DATA_DIR / f"{name}.csv"

    for encoding in ["utf-8", "utf-8-sig", "cp1256"]:

        try:
            return pd.read_csv(
                path,
                encoding=encoding,
                low_memory=False
            )

        except UnicodeDecodeError:
            continue

    raise ValueError(f"Cannot read {name}")


# ==========================================
# TABLES TO ANALYZE
# ==========================================

table_names = [
    "sales_orders",
    "sales_order_items",
    "sales_payments",
    "sales_returns",
    "products_catalog",
    "branches",
    "customers",
    "monthly_stock",
    "marketing_campaigns"
]

numeric_results = []
categorical_results = []
date_results = []
quality_results = []

# ==========================================
# PROFILE TABLES
# ==========================================

for table_name in table_names:

    print(f"\nAnalyzing: {table_name}")

    df = load_table(table_name)

    # --------------------------------------
    # Numeric Columns
    # --------------------------------------

    for col in df.select_dtypes(include=np.number).columns:

        s = df[col].dropna()

        if len(s) == 0:
            continue

        numeric_results.append({

            "table": table_name,
            "column": col,

            "count": len(s),
            "min": s.min(),
            "max": s.max(),
            "mean": round(s.mean(), 2),
            "median": round(s.median(), 2),

            "negative_count": int((s < 0).sum()),
            "zero_count": int((s == 0).sum()),

            "p01": s.quantile(0.01),
            "p99": s.quantile(0.99)

        })

    # --------------------------------------
    # Categorical Columns
    # --------------------------------------

    for col in df.columns:

        if (
            df[col].dtype == "object"
            or isinstance(df[col].dtype, pd.StringDtype)
        ):

            # Exclude identifiers
            if col.lower().endswith("_id"):
                continue

            s = df[col].dropna().astype(str).str.strip()

            if len(s) == 0:
                continue

            if s.nunique() <= 100:

                categorical_results.append({

                    "table": table_name,
                    "column": col,

                    "unique_values": s.nunique(),

                    "top_values": str(
                        s.value_counts().head(15).to_dict()
                    )

                })

    
# --------------------------------------
# Date Column Detection - Improved
# --------------------------------------

for col in df.columns:

    if any(word in col.lower() for word in [
        "date", "created_at", "updated_at",
        "timestamp", "time"
    ]):

        raw = df[col].astype("string").str.strip()

        # Detect ISO format vs slash format
        iso_mask = raw.str.match(
            r"^\d{4}-\d{2}-\d{2}"
        )

        slash_mask = raw.str.match(
            r"^\d{1,2}/\d{1,2}/\d{4}$"
        )

        parsed = pd.Series(
            pd.NaT,
            index=df.index,
            dtype="datetime64[ns]"
        )

        parsed.loc[iso_mask] = pd.to_datetime(
            raw.loc[iso_mask],
            format="ISO8601",
            errors="coerce"
        )

        parsed.loc[slash_mask] = pd.to_datetime(
            raw.loc[slash_mask],
            format="%m/%d/%Y",
            errors="coerce"
        )

        valid = parsed.dropna()

        date_results.append({

            "table": table_name,
            "column": col,

            "total_rows": len(df),
            "valid_dates": len(valid),

            "invalid_dates": int(parsed.isna().sum()),

            "min_date": (
                str(valid.min()) if len(valid) else None
            ),

            "max_date": (
                str(valid.max()) if len(valid) else None
            )

        })

    # --------------------------------------
    # Nulls and Duplicates
    # --------------------------------------

    for col in df.columns:

        null_count = int(df[col].isna().sum())

        if null_count > 0:

            quality_results.append({

                "table": table_name,
                "column": col,

                "null_count": null_count,

                "null_percentage": round(
                    null_count / len(df) * 100, 2
                )

            })


# ==========================================
# SAVE REPORTS
# ==========================================

reports = {

    "10_numeric_profiling.csv": numeric_results,

    "11_categorical_profiling.csv": categorical_results,

    "12_date_profiling.csv": date_results,

    "13_business_quality.csv": quality_results

}

for filename, records in reports.items():

    pd.DataFrame(records).to_csv(
        REPORT_DIR / filename,
        index=False,
        encoding="utf-8-sig"
    )

    print(f"Saved: {filename}")


# ==========================================
# SUMMARY
# ==========================================

print("\n" + "=" * 50)

print("BUSINESS DATA PROFILING COMPLETED")

print("=" * 50)

print("Numeric profiles:", len(numeric_results))
print("Categorical profiles:", len(categorical_results))
print("Date profiles:", len(date_results))
print("Quality observations:", len(quality_results))

print("\nReports saved in:", REPORT_DIR)



# Daily Historical Columns

DATE_COLUMNS = {
    "sales_orders": ["order_date"],
    "sales_order_items": ["order_date"],
    "sales_payments": ["payment_date"],
    "sales_returns": ["return_date"],
    "branches": ["opening_date"],
    "customers": ["joined_date"],
    "marketing_campaigns": ["start_date", "end_date"],
    "delivery_shipments": ["ship_date", "delivery_date"],
    "purchase_orders": ["po_date"],
    "inventory_transfers": ["transfer_date"],
    "employees": ["hire_date"],
}

# أعمدة تمثل شهرًا أو فترة شهرية
MONTH_COLUMNS = {
    "monthly_stock": ["year_month"],
    "payroll": ["pay_month"],
}

results = []

def profile_date_column(table, column, monthly=False):
    path = DATA_DIR / f"{table}.csv"

    df = pd.read_csv(path, usecols=[column])
    raw = df[column].astype("string").str.strip()

    if monthly:
        # نتوقع صيغة شهر مثل YYYY-MM
        parsed = pd.to_datetime(
            raw,
            format="%Y-%m",
            errors="coerce"
        )
    else:
        parsed = pd.to_datetime(
            raw,
            format="mixed",
            errors="coerce"
        )

    invalid = raw.notna() & parsed.isna()

    results.append({
        "table": table,
        "column": column,
        "rows": len(raw),
        "null_count": int(raw.isna().sum()),
        "valid_count": int(parsed.notna().sum()),
        "invalid_count": int(invalid.sum()),
        "min_date": (
            parsed.min().strftime("%Y-%m-%d")
            if parsed.notna().any() else None
        ),
        "max_date": (
            parsed.max().strftime("%Y-%m-%d")
            if parsed.notna().any() else None
        ),
    })


for table, columns in DATE_COLUMNS.items():
    for column in columns:
        profile_date_column(table, column)

for table, columns in MONTH_COLUMNS.items():
    for column in columns:
        profile_date_column(table, column, monthly=True)

report = pd.DataFrame(results)

REPORT_DIR.mkdir(exist_ok=True)

report.to_csv(
    REPORT_DIR / "12_date_profiling.csv",
    index=False
)

print(report.to_string(index=False))
print("\nTotal date columns profiled:", len(report))
print("Total invalid values:", report["invalid_count"].sum())
