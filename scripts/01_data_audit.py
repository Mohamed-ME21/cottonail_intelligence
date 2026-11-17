
from pathlib import Path
import pandas as pd
import numpy as np

# ==========================================
# 1. Project Configuration
# ==========================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
REPORT_DIR = BASE_DIR / "reports"

REPORT_DIR.mkdir(parents=True, exist_ok=True)

# ==========================================
# 2. Read CSV with Encoding Fallback
# ==========================================

def read_csv_safely(file_path):

    encodings = ["utf-8", "utf-8-sig", "cp1256", "latin1"]

    for encoding in encodings:
        try:
            df = pd.read_csv(file_path, encoding=encoding)
            return df, encoding
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue

    raise ValueError(f"Cannot read file: {file_path.name}")


# ==========================================
# 3. Data Type Detection
# ==========================================

def detect_data_type(series):

    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"

    if pd.api.types.is_numeric_dtype(series):
        return "numeric"

    if pd.api.types.is_bool_dtype(series):
        return "boolean"

    return "text"


# ==========================================
# 4. Main Data Audit
# ==========================================

def main():

    csv_files = list(DATA_DIR.glob("*.csv"))

    if not csv_files:
        print("No CSV files found in data folder.")
        return

    print(f"\nFound {len(csv_files)} CSV files.\n")

    inventory = []
    column_profiles = []
    key_candidates = []
    quality_issues = []
    loaded_tables = {}

    # --------------------------------------
    # Read and Profile Every File
    # --------------------------------------

    for file_path in csv_files:

        try:
            df, encoding = read_csv_safely(file_path)

            table_name = file_path.stem
            loaded_tables[table_name] = df

            rows, columns = df.shape

            inventory.append({
                "table_name": file_path.name,
                "rows": rows,
                "columns": columns,
                "encoding": encoding,
                "duplicate_rows": int(df.duplicated().sum()),
                "memory_MB": round(
                    df.memory_usage(deep=True).sum() / (1024 ** 2), 2
                )
            })

            print(f"[OK] {file_path.name}: {rows} rows, {columns} columns")

            # ----------------------------------
            # Table-level Issues
            # ----------------------------------

            if df.empty:
                quality_issues.append({
                    "table": table_name,
                    "issue": "Empty table",
                    "column": ""
                })

            if df.columns.duplicated().any():
                quality_issues.append({
                    "table": table_name,
                    "issue": "Duplicate column names",
                    "column": ""
                })

            if df.duplicated().sum() > 0:
                quality_issues.append({
                    "table": table_name,
                    "issue": "Duplicate rows",
                    "column": ""
                })

            # ----------------------------------
            # Column-level Profiling
            # ----------------------------------

            for col in df.columns:

                series = df[col]

                null_count = int(series.isna().sum())
                distinct_count = int(series.nunique(dropna=True))

                profile = {
                    "table": table_name,
                    "column": col,
                    "data_type": detect_data_type(series),
                    "null_count": null_count,
                    "null_percentage": round(
                        (null_count / rows * 100) if rows else 0, 2
                    ),
                    "distinct_count": distinct_count,
                    "unique_percentage": round(
                        (distinct_count / rows * 100) if rows else 0, 2
                    )
                }

                # Numeric statistics
                if pd.api.types.is_numeric_dtype(series):
                    profile["min_value"] = series.min()
                    profile["max_value"] = series.max()
                    profile["mean_value"] = (
                        round(series.mean(), 2)
                        if series.notna().any() else np.nan
                    )

                column_profiles.append(profile)

                # ----------------------------------
                # Candidate Primary Keys
                # ----------------------------------

                if col.lower().endswith("_id"):

                    is_unique = (
                        series.notna().all()
                        and series.is_unique
                        and len(series) > 0
                    )

                    key_candidates.append({
                        "table": table_name,
                        "column": col,
                        "non_null": int(series.notna().sum()),
                        "distinct_count": distinct_count,
                        "is_unique_candidate": bool(is_unique)
                    })

                # ----------------------------------
                # Column-level Quality Issues
                # ----------------------------------

                if null_count > 0:
                    quality_issues.append({
                        "table": table_name,
                        "issue": "Missing values",
                        "column": col
                    })

                if series.dtype == "object":
                    empty_strings = int(
                        series.astype("string").str.strip().eq("").sum()
                    )

                    if empty_strings > 0:
                        quality_issues.append({
                            "table": table_name,
                            "issue": "Empty strings",
                            "column": col
                        })

        except Exception as error:

            print(f"[ERROR] {file_path.name}: {error}")

            quality_issues.append({
                "table": file_path.name,
                "issue": f"Read error: {type(error).__name__}",
                "column": ""
            })

    # ==========================================
    # 5. Candidate Foreign Key Relationships
    # ==========================================

    relationships = []

    id_columns = {}

    for table_name, df in loaded_tables.items():

        for col in df.columns:

            if col.lower().endswith("_id"):

                values = set(
                    df[col].dropna().astype(str).str.strip()
                )

                id_columns[(table_name, col)] = values

    for (child_table, child_col), child_values in id_columns.items():

        for (parent_table, parent_col), parent_values in id_columns.items():

            if child_table == parent_table:
                continue

            if child_col != parent_col:
                continue

            if not child_values or not parent_values:
                continue

            matched = child_values.intersection(parent_values)

            relationships.append({
                "child_table": child_table,
                "child_column": child_col,
                "parent_table": parent_table,
                "parent_column": parent_col,
                "child_distinct_values": len(child_values),
                "matched_values": len(matched),
                "match_percentage": round(
                    len(matched) / len(child_values) * 100, 2
                )
            })

    # ==========================================
    # 6. Save Reports
    # ==========================================

    reports = {
        "01_file_inventory.csv": inventory,
        "02_column_profiles.csv": column_profiles,
        "03_key_candidates.csv": key_candidates,
        "04_relationship_candidates.csv": relationships,
        "05_quality_issues.csv": quality_issues
    }

    for filename, records in reports.items():

        report_df = pd.DataFrame(records)

        report_df.to_csv(
            REPORT_DIR / filename,
            index=False,
            encoding="utf-8-sig"
        )

        print(f"\nSaved: {filename}")

    # ==========================================
    # 7. Final Summary
    # ==========================================

    total_rows = sum(x["rows"] for x in inventory)
    total_tables = len(inventory)

    print("\n" + "=" * 50)
    print("COTTONIL DATA AUDIT SUMMARY")
    print("=" * 50)

    print(f"Total CSV files loaded: {total_tables}")
    print(f"Total records: {total_rows:,}")
    print(f"Total columns: {len(column_profiles)}")
    print(f"Quality issues detected: {len(quality_issues)}")
    print(f"Candidate relationships: {len(relationships)}")

    print("\nReports directory:")
    print(REPORT_DIR)

    print("\nData audit completed successfully!")


if __name__ == "__main__":
    main()
