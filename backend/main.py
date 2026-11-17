
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from backend.analytics_api import router as analytics_router
from backend.pages_api import router as pages_router, warm_up
from backend.rag_api import router as rag_router
BASE_DIR = Path(__file__).resolve().parent.parent

PROCESSED_DIR = BASE_DIR / "data" / "processed"

REPORTS_DIR = BASE_DIR / "reports"


@asynccontextmanager
async def lifespan(_app):
    # Load the big CSV files once at start-up so the first page view is fast.
    threading.Thread(target=warm_up, daemon=True).start()
    yield


app = FastAPI(
    title="Cottonil Intelligence Hub API",
    version="0.4.0",
    lifespan=lifespan,
)

app.include_router(analytics_router)
app.include_router(pages_router)
app.include_router(rag_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "Cottonil Intelligence Hub API",
        "processed_directory_exists": PROCESSED_DIR.exists(),
    }


@app.get("/api/dashboard/status")
def dashboard_status():
    expected_files = [
        "fact_sales.csv",
        "fact_returns.csv",
    ]

    file_status = {
        name: (PROCESSED_DIR / name).exists()
        for name in expected_files
    }

    ready = all(file_status.values())

    return {
        "ready": ready,
        "data_directory": str(PROCESSED_DIR),
        "files": file_status,
        "message": (
            "Core fact files found."
            if ready
            else "One or more core fact files are missing."
        ),
    }


@app.get("/api/dashboard/diagnostics")
def dashboard_diagnostics():
    expected_files = [
        "fact_sales.csv",
        "fact_returns.csv",
    ]

    result = {}

    for filename in expected_files:
        path = PROCESSED_DIR / filename

        if not path.exists():
            result[filename] = {
                "exists": False,
                "columns": [],
            }
            continue

        sample = pd.read_csv(path, nrows=1000)

        result[filename] = {
            "exists": True,
            "columns": list(sample.columns),
            "sample_dtypes": {
                column: str(dtype)
                for column, dtype in sample.dtypes.items()
            },
        }

    return {
        "data_directory": str(PROCESSED_DIR),
        "datasets": result,
    }


@app.get("/api/dashboard/overview")
def dashboard_overview():
    sales_path = PROCESSED_DIR / "fact_sales.csv"
    returns_path = PROCESSED_DIR / "fact_returns.csv"
    catalog_path = PROCESSED_DIR / "products_catalog.csv"

    if not sales_path.exists() or not returns_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Required fact files were not found.",
        )

    try:
        # Read only the columns needed for the KPIs.
        sales = pd.read_csv(
            sales_path,
            usecols=[
                "sales_order_id",
                "product_id",
                "quantity",
                "net_line_EGP",
                "margin_EGP",
                "year_month",
            ],
        )

        returns = pd.read_csv(
            returns_path,
            usecols=[
                "return_quantity",
                "refund_amount_EGP",
            ],
        )

        total_quantity_sold = int(sales["quantity"].sum())
        total_quantity_returned = int(
            returns["return_quantity"].sum()
        )

        return_rate = (
            total_quantity_returned / total_quantity_sold * 100
            if total_quantity_sold > 0
            else 0
        )

        total_products = int(sales["product_id"].nunique())
        product_count_source = "fact_sales"

        if catalog_path.exists():
            catalog = pd.read_csv(
                catalog_path,
                usecols=["product_id"],
            )
            total_products = int(catalog["product_id"].nunique())
            product_count_source = "products_catalog"

        # Monthly net sales trend.
        monthly = (
            sales.groupby("year_month", as_index=False)
            ["net_line_EGP"]
            .sum()
            .sort_values("year_month")
        )

        monthly_sales = [
            {
                "month": str(row["year_month"]),
                "net_sales": round(float(row["net_line_EGP"]), 2),
            }
            for _, row in monthly.iterrows()
        ]

        return {
            "success": True,
            "currency": "EGP",
            "kpis": {
                "net_sales": round(
                    float(sales["net_line_EGP"].sum()), 2
                ),
                "gross_margin": round(
                    float(sales["margin_EGP"].sum()), 2
                ),
                "orders": int(
                    sales["sales_order_id"].nunique()
                ),
                "return_rate_pct": round(return_rate, 4),
                "refund_value": round(
                    float(returns["refund_amount_EGP"].sum()), 2
                ),
                "active_products": total_products,
            },
            "return_details": {
                "quantity_sold": total_quantity_sold,
                "quantity_returned": total_quantity_returned,
                "return_records": int(len(returns)),
            },
            "monthly_sales": monthly_sales,
            "metadata": {
                "sales_rows": int(len(sales)),
                "returns_rows": int(len(returns)),
                "product_count_source": product_count_source,
            },
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Dashboard calculation failed: {str(exc)}",
        )


@app.get("/api/dashboard/hotspots")
def get_dashboard_hotspots(limit: int = 5):
    """
    Return the highest-priority eligible product/branch return hotspots.
    Source: reports/52_product_branch_hotspots_ranked.csv
    """

    report_path = REPORTS_DIR / "52_product_branch_hotspots_ranked.csv"

    if not report_path.exists():
        return {
            "success": False,
            "message": "Hotspots report file was not found.",
            "hotspots": [],
        }

    try:
        df = pd.read_csv(report_path)

        required_columns = [
            "product_id",
            "branch_id",
            "product_name_ar",
            "sold_quantity",
            "returned_quantity",
            "refund_amount_EGP",
            "quantity_return_rate_pct",
            "excess_returned_quantity_vs_overall",
            "excess_return_quantity_rank",
            "eligible_hotspot",
        ]

        missing_columns = [
            col for col in required_columns if col not in df.columns
        ]

        if missing_columns:
            return {
                "success": False,
                "message": "Required columns are missing from the report.",
                "missing_columns": missing_columns,
                "hotspots": [],
            }

        # Keep only eligible hotspots.
        eligible = df[
            df["eligible_hotspot"]
            .astype(str)
            .str.strip()
            .str.lower()
            .isin(["true", "1"])
        ].copy()

        # Ensure ranking and numeric fields are valid.
        numeric_columns = [
            "sold_quantity",
            "returned_quantity",
            "refund_amount_EGP",
            "quantity_return_rate_pct",
            "excess_returned_quantity_vs_overall",
            "excess_return_quantity_rank",
        ]

        for column in numeric_columns:
            eligible[column] = pd.to_numeric(
                eligible[column], errors="coerce"
            )

        eligible = eligible.dropna(
            subset=[
                "excess_return_quantity_rank",
                "quantity_return_rate_pct",
                "excess_returned_quantity_vs_overall",
            ]
        )

        eligible = eligible.sort_values(
            "excess_return_quantity_rank",
            ascending=True,
        )

        # Keep the requested number of rows.
        limit = max(1, min(int(limit), 20))
        top_rows = eligible.head(limit)

        hotspots = []

        for _, row in top_rows.iterrows():
            hotspots.append({
                "product_id": str(row["product_id"]),
                "branch_id": str(row["branch_id"]),
                "product_name_ar": str(row["product_name_ar"]),
                "sold_quantity": int(row["sold_quantity"]),
                "returned_quantity": int(row["returned_quantity"]),
                "refund_amount_EGP": round(
                    float(row["refund_amount_EGP"]), 2
                ),
                "quantity_return_rate_pct": round(
                    float(row["quantity_return_rate_pct"]), 2
                ),
                "excess_returned_quantity": round(
                    float(row["excess_returned_quantity_vs_overall"]), 2
                ),
                "rank": int(row["excess_return_quantity_rank"]),
            })

        return {
            "success": True,
            "source": "52_product_branch_hotspots_ranked.csv",
            "total_eligible_hotspots": int(len(eligible)),
            "returned_hotspots": len(hotspots),
            "hotspots": hotspots,
        }

    except Exception as error:
        return {
            "success": False,
            "message": str(error),
            "hotspots": [],
        }


@app.get("/api/dashboard/hotspots/{product_id}/{branch_id}")
def get_hotspot_details(product_id: str, branch_id: str):
    """
    Return detailed return reasons for one product/branch hotspot.
    Source: reports/54_hotspot_reason_breakdown.csv
    """

    report_path = REPORTS_DIR / "54_hotspot_reason_breakdown.csv"

    if not report_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Hotspot reason breakdown report was not found.",
        )

    try:
        df = pd.read_csv(
        report_path,
        dtype={
            "product_id": "string",
            "branch_id": "string",
        },
    )

        # Normalize IDs to avoid whitespace mismatches.
        df["product_id"] = df["product_id"].str.strip()
        df["branch_id"] = df["branch_id"].str.strip()

        product_id = product_id.strip()
        branch_id = branch_id.strip()

        required_columns = [
            "product_id",
            "branch_id",
            "reason",
            "reason_return_records",
            "reason_returned_quantity",
            "reason_refund_amount_EGP",
            "sold_quantity",
            "returned_quantity",
            "refund_amount_EGP",
            "quantity_return_rate_pct",
            "refund_to_net_sales_pct",
            "excess_returned_quantity_vs_overall",
            "reason_records_share_pct",
            "reason_quantity_share_pct",
            "reason_refund_share_pct",
        ]

        missing_columns = [
            column
            for column in required_columns
            if column not in df.columns
        ]

        if missing_columns:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "Required columns are missing.",
                    "missing_columns": missing_columns,
                },
            )

        # Match the requested product and branch.
        matched = df[
    (df["product_id"] == product_id)
    & (df["branch_id"] == branch_id)
        ].copy()

        if matched.empty:
            raise HTTPException(
                status_code=404,
                detail="No details found for this product and branch.",
            )

        # Convert numerical columns safely.
        numeric_columns = [
            "reason_return_records",
            "reason_returned_quantity",
            "reason_refund_amount_EGP",
            "sold_quantity",
            "returned_quantity",
            "refund_amount_EGP",
            "quantity_return_rate_pct",
            "refund_to_net_sales_pct",
            "excess_returned_quantity_vs_overall",
            "reason_records_share_pct",
            "reason_quantity_share_pct",
            "reason_refund_share_pct",
        ]

        for column in numeric_columns:
            matched[column] = pd.to_numeric(
                matched[column],
                errors="coerce",
            ).fillna(0)

        # Shared hotspot metrics are repeated across reason rows.
        first = matched.iloc[0]

        reasons = []

        # Sort by returned quantity, highest first.
        matched = matched.sort_values(
            "reason_returned_quantity",
            ascending=False,
        )

        for _, row in matched.iterrows():
            reasons.append({
                "reason": str(row["reason"]),
                "return_records": int(row["reason_return_records"]),
                "returned_quantity": int(
                    row["reason_returned_quantity"]
                ),
                "refund_amount_EGP": round(
                    float(row["reason_refund_amount_EGP"]),
                    2,
                ),
                "records_share_pct": round(
                    float(row["reason_records_share_pct"]),
                    2,
                ),
                "quantity_share_pct": round(
                    float(row["reason_quantity_share_pct"]),
                    2,
                ),
                "refund_share_pct": round(
                    float(row["reason_refund_share_pct"]),
                    2,
                ),
            })

        return {
            "success": True,
            "source": "54_hotspot_reason_breakdown.csv",
            "product_id": product_id,
            "branch_id": branch_id,
            "summary": {
                "sold_quantity": int(first["sold_quantity"]),
                "returned_quantity": int(first["returned_quantity"]),
                "refund_amount_EGP": round(
                    float(first["refund_amount_EGP"]),
                    2,
                ),
                "quantity_return_rate_pct": round(
                    float(first["quantity_return_rate_pct"]),
                    2,
                ),
                "refund_to_net_sales_pct": round(
                    float(first["refund_to_net_sales_pct"]),
                    2,
                ),
                "excess_returned_quantity": round(
                    float(
                        first["excess_returned_quantity_vs_overall"]
                    ),
                    2,
                ),
            },
            "reason_count": len(reasons),
            "reasons": reasons,
        }

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Hotspot details calculation failed: {str(error)}",
        )

    
@app.get("/api/data/catalog")
def data_catalog():
    """Inspect all processed CSV files and their schemas."""
    result = []

    for path in sorted(PROCESSED_DIR.glob("*.csv")):
        try:
            df = pd.read_csv(path, nrows=5)
            row_count = sum(
                1 for _ in open(path, "r", encoding="utf-8-sig")
            ) - 1

            result.append({
                "file": path.name,
                "rows": row_count,
                "columns": list(df.columns),
            })

        except Exception as exc:
            result.append({
                "file": path.name,
                "error": str(exc),
            })

    return {
        "success": True,
        "dataset_count": len(result),
        "datasets": result,
    }

@app.get("/api/data/source-catalog")
def source_data_catalog():
    """Inspect original source CSV schemas without loading full datasets."""
    data_dir = BASE_DIR / "data"
    result = []

    for path in sorted(data_dir.glob("*.csv")):
        try:
            # Read only the header; do not load the full dataset.
            columns = pd.read_csv(
                path,
                nrows=0,
                encoding="utf-8-sig"
            ).columns.tolist()

            result.append({
                "file": path.name,
                "size_mb": round(path.stat().st_size / (1024 * 1024), 2),
                "column_count": len(columns),
                "columns": columns,
                "status": "success"
            })

        except Exception as exc:
            result.append({
                "file": path.name,
                "status": "error",
                "error": str(exc)
            })

    return {
        "success": True,
        "source_dataset_count": len(result),
        "datasets": result
    }

@app.get("/api/data/relationship-checks")
def relationship_checks():
    """Check key relationships and basic data coverage."""

    data_dir = BASE_DIR / "data"

    def load_csv(name, columns=None):
        return pd.read_csv(
            data_dir / name,
            usecols=columns,
            encoding="utf-8-sig"
        )

    checks = {}

    # Branch relationship
    branches = load_csv("branches.csv", ["branch_id"])
    sales = load_csv("sales_orders.csv", ["branch_id"])

    checks["sales_branch"] = {
        "sales_branch_ids": int(sales["branch_id"].nunique()),
        "known_branch_ids": int(branches["branch_id"].nunique()),
        "unmatched_sales_branches": int(
            (~sales["branch_id"].isin(branches["branch_id"])).sum()
        )
    }

    # Customer relationship
    customers = load_csv("customers.csv", ["customer_id"])
    customer_sales = load_csv("sales_orders.csv", ["customer_id"])

    checks["sales_customer"] = {
        "known_customers": int(customers["customer_id"].nunique()),
        "unmatched_customer_orders": int(
            (~customer_sales["customer_id"].isin(
                customers["customer_id"]
            ) & customer_sales["customer_id"].notna()).sum()
        ),
        "null_customer_orders": int(
            customer_sales["customer_id"].isna().sum()
        )
    }

    # Product relationship
    products = load_csv("products_catalog.csv", ["product_id"])
    sales_products = load_csv(
        "sales_order_items.csv", ["product_id"]
    )

    checks["sales_product"] = {
        "known_products": int(products["product_id"].nunique()),
        "unmatched_sales_lines": int(
            (~sales_products["product_id"].isin(
                products["product_id"]
            )).sum()
        )
    }

    # SKU relationship
    skus = load_csv("sku_variants.csv", ["sku_id"])
    sales_skus = load_csv("sales_order_items.csv", ["sku_id"])

    checks["sales_sku"] = {
        "known_skus": int(skus["sku_id"].nunique()),
        "unmatched_sales_lines": int(
            (~sales_skus["sku_id"].isin(skus["sku_id"])).sum()
        )
    }

    # Warehouse relationship
    warehouses = load_csv("warehouses.csv", ["warehouse_id"])
    stock = load_csv(
        "monthly_stock.csv", ["stock_location_id"]
    )

    checks["stock_warehouse"] = {
        "warehouse_ids": int(warehouses["warehouse_id"].nunique()),
        "stock_location_ids": int(stock["stock_location_id"].nunique()),
        "unmatched_stock_locations": int(
            (~stock["stock_location_id"].isin(
                warehouses["warehouse_id"]
            )).sum()
        )
    }

    # Purchase currency distribution
    purchase_orders = load_csv(
        "purchase_orders.csv", ["currency", "po_status"]
    )

    checks["purchase_currency"] = {
        "currency_counts": (
            purchase_orders["currency"]
            .fillna("NULL")
            .value_counts()
            .to_dict()
        ),
        "status_counts": (
            purchase_orders["po_status"]
            .fillna("NULL")
            .value_counts()
            .to_dict()
        )
    }

    return {
        "success": True,
        "checks": checks
    }

@app.get("/api/data/stock-location-diagnostics")
def stock_location_diagnostics():
    data_dir = BASE_DIR / "data"

    stock = pd.read_csv(
        data_dir / "monthly_stock.csv",
        usecols=[
            "year_month",
            "stock_location_id",
            "stock_location_type",
            "closing_units",
            "closing_stock_value_EGP",
            "stockout_risk_score"
        ],
        encoding="utf-8-sig"
    )

    warehouses = pd.read_csv(
        data_dir / "warehouses.csv",
        encoding="utf-8-sig"
    )

    warehouse_ids = set(
        warehouses["warehouse_id"].dropna().astype(str)
    )

    stock["location_id_text"] = (
        stock["stock_location_id"].astype(str)
    )

    type_summary = (
        stock.groupby("stock_location_type", dropna=False)
        .agg(
            records=("stock_location_id", "size"),
            unique_locations=("stock_location_id", "nunique"),
            total_units=("closing_units", "sum"),
            total_stock_value=("closing_stock_value_EGP", "sum"),
            avg_stockout_risk=("stockout_risk_score", "mean")
        )
        .reset_index()
    )

    location_summary = (
        stock.groupby(
            ["stock_location_type", "stock_location_id"],
            dropna=False
        )
        .agg(
            records=("year_month", "size"),
            latest_month=("year_month", "max"),
            latest_units=("closing_units", "last"),
            latest_stock_value=("closing_stock_value_EGP", "last")
        )
        .reset_index()
    )

    location_summary["matches_warehouse"] = (
        location_summary["stock_location_id"]
        .astype(str)
        .isin(warehouse_ids)
    )

    return {
        "success": True,
        "stock_rows": len(stock),
        "warehouse_count": len(warehouses),
        "stock_location_types": type_summary.to_dict("records"),
        "locations": location_summary.to_dict("records"),
        "warehouse_reference": warehouses.to_dict("records")
    }

