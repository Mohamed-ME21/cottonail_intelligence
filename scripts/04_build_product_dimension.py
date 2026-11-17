
from pathlib import Path
import pandas as pd
import numpy as np

# --------------------------------------------------
# 1. Paths
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
REPORT_DIR = BASE_DIR / "reports"
OUTPUT_DIR = DATA_DIR / "processed"

REPORT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

internal_path = DATA_DIR / "products_catalog.csv"
public_path = DATA_DIR / "PRODUCT_CATALOG_PUBLIC_REFERENCE.csv"

# --------------------------------------------------
# 2. Load data
# --------------------------------------------------

internal = pd.read_csv(
    internal_path,
    dtype={"product_id": "string"}
)

public = pd.read_csv(
    public_path,
    dtype={"product_id": "string"}
)

# --------------------------------------------------
# 3. Validate required columns
# --------------------------------------------------

required_internal = {
    "product_id", "product_name_ar", "category_en",
    "audience", "listed_price_EGP", "source_url"
}

required_public = {
    "product_id", "product_name_ar",
    "category", "listed_price_EGP"
}

missing_internal = required_internal - set(internal.columns)
missing_public = required_public - set(public.columns)

if missing_internal or missing_public:
    raise ValueError(
        f"Missing internal columns: {missing_internal}\n"
        f"Missing public columns: {missing_public}"
    )

# Clean IDs without changing their actual identifiers
internal["product_id"] = internal["product_id"].str.strip()
public["product_id"] = public["product_id"].str.strip()

if internal["product_id"].isna().any():
    raise ValueError("Internal product_id contains null values.")

if public["product_id"].isna().any():
    raise ValueError("Public product_id contains null values.")

if internal["product_id"].duplicated().any():
    raise ValueError("Duplicate product IDs in internal catalog.")

if public["product_id"].duplicated().any():
    raise ValueError("Duplicate product IDs in public reference.")

# --------------------------------------------------
# 4. Preserve source-specific columns
# --------------------------------------------------

internal = internal.rename(columns={
    "product_name_ar": "internal_product_name_ar",
    "listed_price_EGP": "internal_listed_price_EGP"
})

public = public.rename(columns={
    "product_name_ar": "public_product_name_ar",
    "category": "category_public",
    "listed_price_EGP": "public_listed_price_EGP"
})

# --------------------------------------------------
# 5. Full outer join
# --------------------------------------------------

dim_product = internal.merge(
    public,
    on="product_id",
    how="outer",
    validate="one_to_one",
    indicator=True
)

dim_product["match_status"] = dim_product["_merge"].map({
    "both": "matched",
    "left_only": "internal_only",
    "right_only": "public_only"
})

dim_product["is_internal_product"] = (
    dim_product["_merge"].isin(["both", "left_only"])
)

dim_product["is_public_reference_product"] = (
    dim_product["_merge"].isin(["both", "right_only"])
)

# --------------------------------------------------
# 6. Compare names and prices for matched products
# --------------------------------------------------

def normalize_text(value):
    if pd.isna(value):
        return None
    return " ".join(str(value).strip().split()).casefold()

matched = dim_product["match_status"].eq("matched")

dim_product["name_match"] = pd.Series(
    pd.NA, index=dim_product.index, dtype="boolean"
)

dim_product.loc[matched, "name_match"] = (
    dim_product.loc[matched, "internal_product_name_ar"]
    .map(normalize_text)
    ==
    dim_product.loc[matched, "public_product_name_ar"]
    .map(normalize_text)
)

internal_price = pd.to_numeric(
    dim_product["internal_listed_price_EGP"],
    errors="coerce"
)

public_price = pd.to_numeric(
    dim_product["public_listed_price_EGP"],
    errors="coerce"
)

dim_product["price_match"] = pd.Series(
    pd.NA, index=dim_product.index, dtype="boolean"
)

price_comparable = matched & internal_price.notna() & public_price.notna()

dim_product.loc[price_comparable, "price_match"] = np.isclose(
    internal_price[price_comparable],
    public_price[price_comparable],
    atol=0.01,
    rtol=0
)

# --------------------------------------------------
# 7. Save the unified product dimension
# --------------------------------------------------

dim_product = dim_product.drop(columns=["_merge"])

dim_product = dim_product.sort_values(
    "product_id"
).reset_index(drop=True)

dimension_path = OUTPUT_DIR / "dim_product.csv"
dim_product.to_csv(dimension_path, index=False, encoding="utf-8-sig")

# --------------------------------------------------
# 8. Save review reports
# --------------------------------------------------

name_differences = dim_product[
    matched & dim_product["name_match"].eq(False)
]

price_differences = dim_product[
    price_comparable & dim_product["price_match"].eq(False)
]

public_only = dim_product[
    dim_product["match_status"].eq("public_only")
]

name_differences.to_csv(
    REPORT_DIR / "17_product_name_differences.csv",
    index=False,
    encoding="utf-8-sig"
)

price_differences.to_csv(
    REPORT_DIR / "18_product_price_differences.csv",
    index=False,
    encoding="utf-8-sig"
)

public_only.to_csv(
    REPORT_DIR / "19_public_only_products.csv",
    index=False,
    encoding="utf-8-sig"
)

# --------------------------------------------------
# 9. Summary
# --------------------------------------------------

summary = pd.DataFrame([
    ["Internal products", len(internal)],
    ["Public reference products", len(public)],
    ["Unified dimension products", len(dim_product)],
    ["Matched products", int(matched.sum())],
    ["Internal only", int((dim_product["match_status"] == "internal_only").sum())],
    ["Public only", int((dim_product["match_status"] == "public_only").sum())],
    ["Matched names that differ", len(name_differences)],
    ["Matched prices that differ", len(price_differences)]
], columns=["metric", "value"])

summary.to_csv(
    REPORT_DIR / "20_product_dimension_summary.csv",
    index=False,
    encoding="utf-8-sig"
)

print("\nPRODUCT DIMENSION BUILD COMPLETE")
print(summary.to_string(index=False))
print(f"\nDimension saved to: {dimension_path}")
print(f"Reports saved to: {REPORT_DIR}")
