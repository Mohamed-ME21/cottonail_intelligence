
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
REPORT_DIR = BASE_DIR / "reports"

# 1. Quality Issues
quality = pd.read_csv(
    REPORT_DIR / "05_quality_issues.csv"
)

print("\n========== QUALITY ISSUES ==========")
print(quality.to_string(index=False))

# 2. Candidate Primary Keys
keys = pd.read_csv(
    REPORT_DIR / "03_key_candidates.csv"
)

print("\n========== KEY CANDIDATES ==========")
print(
    keys.sort_values(
        ["table", "column"]
    ).to_string(index=False)
)

# 3. Relationship Candidates
relations = pd.read_csv(
    REPORT_DIR / "04_relationship_candidates.csv"
)

print("\n========== RELATIONSHIPS ==========")
print(
    relations.sort_values(
        ["child_table", "child_column", "parent_table"]
    ).to_string(index=False)
)

# 4. File Inventory
inventory = pd.read_csv(
    REPORT_DIR / "01_file_inventory.csv"
)

print("\n========== FILE INVENTORY ==========")
print(inventory.to_string(index=False))

# 5. Column Profiles: show only important statistics
profiles = pd.read_csv(
    REPORT_DIR / "02_column_profiles.csv"
)

print("\n========== COLUMN PROFILE SUMMARY ==========")

summary = profiles[
    profiles["null_count"] > 0
][
    ["table", "column", "data_type", "null_count",
     "null_percentage"]
]

print("Columns containing missing values:")
if summary.empty:
    print("No missing values detected.")
else:
    print(summary.to_string(index=False))

print("\nAudit report review completed.")
