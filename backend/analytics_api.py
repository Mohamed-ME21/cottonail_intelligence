from pathlib import Path
from functools import lru_cache
from contextvars import ContextVar
import math

import pandas as pd
from fastapi import APIRouter, HTTPException


router = APIRouter(prefix="/api/analytics", tags=["Dashboard Analytics"])

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PROCESSED_DIR = DATA_DIR / "processed"
GLOBAL_FILTERS = ContextVar("cottonil_global_filters", default={})

def apply_global_filters(df: pd.DataFrame, date_col: str = "order_date") -> pd.DataFrame:
    if df is None or df.empty: return df
    f = GLOBAL_FILTERS.get()
    out = df.copy()
    if date_col in out.columns:
        dates = pd.to_datetime(out[date_col], errors="coerce")
        if f.get("date_from"): out = out.loc[dates >= pd.Timestamp(f["date_from"])]
        if f.get("date_to"): out = out.loc[dates < pd.Timestamp(f["date_to"]) + pd.Timedelta(days=1)]
    for key, col in (("branches", "branch_id"), ("products", "product_id"), ("categories", "category_en"), ("channels", "sales_channel")):
        vals = f.get(key, [])
        if vals and col in out.columns: out = out[out[col].astype(str).isin(vals)]
    govs = f.get("governorates", [])
    if govs and "branch_id" in out.columns:
        branches = get_branches()
        if not branches.empty and {"branch_id", "governorate_ar"}.issubset(branches.columns):
            ids = branches.loc[branches.governorate_ar.astype(str).isin(govs), "branch_id"].astype(str)
            out = out[out.branch_id.astype(str).isin(ids)]
    return out



# ---------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------

def _read_csv(path: Path, required: bool = True) -> pd.DataFrame:
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Required data file not found: {path}")
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


@lru_cache(maxsize=1)
def get_fact_sales() -> pd.DataFrame:
    df = _read_csv(PROCESSED_DIR / "fact_sales.csv")
    if "order_date" in df.columns:
        df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
    return df


@lru_cache(maxsize=1)
def get_sales_orders() -> pd.DataFrame:
    df = _read_csv(DATA_DIR / "sales_orders.csv")
    if "order_date" in df.columns:
        df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
    return df


@lru_cache(maxsize=1)
def get_fact_returns() -> pd.DataFrame:
    return _read_csv(PROCESSED_DIR / "fact_returns.csv", required=False)


@lru_cache(maxsize=1)
def get_branches() -> pd.DataFrame:
    return _read_csv(DATA_DIR / "branches.csv", required=False)


@lru_cache(maxsize=1)
def get_employees() -> pd.DataFrame:
    return _read_csv(DATA_DIR / "employees.csv", required=False)


@lru_cache(maxsize=1)
def get_payroll() -> pd.DataFrame:
    return _read_csv(DATA_DIR / "payroll.csv", required=False)


@lru_cache(maxsize=1)
def get_operating_expenses() -> pd.DataFrame:
    return _read_csv(DATA_DIR / "operating_expenses.csv", required=False)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def money(value) -> float:
    try:
        value = float(value)
        return round(value, 2) if math.isfinite(value) else 0.0
    except (TypeError, ValueError):
        return 0.0


def safe_divide(numerator, denominator, multiplier=1.0):
    try:
        numerator = float(numerator)
        denominator = float(denominator)
        if denominator == 0 or not math.isfinite(denominator):
            return None
        result = numerator / denominator * multiplier
        return round(result, 2) if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def records(df: pd.DataFrame) -> list:
    if df is None or df.empty:
        return []
    clean = df.copy()
    clean = clean.replace([float("inf"), float("-inf")], None)
    clean = clean.astype(object).where(pd.notna(clean), None)
    return clean.to_dict(orient="records")


def numeric_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    for column in columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)
    return df


def clean_sales() -> pd.DataFrame:
    sales = apply_global_filters(get_fact_sales()).copy()
    required = [
        "order_date", "net_line_EGP", "gross_line_EGP",
        "discount_line_EGP", "quantity", "margin_EGP"
    ]
    missing = [column for column in required if column not in sales.columns]
    if missing:
        raise HTTPException(
            status_code=500,
            detail=f"Missing columns in fact_sales.csv: {', '.join(missing)}"
        )

    sales["order_date"] = pd.to_datetime(sales["order_date"], errors="coerce")
    sales = sales.dropna(subset=["order_date"])
    return numeric_columns(
        sales,
        [
            "net_line_EGP", "gross_line_EGP", "discount_line_EGP",
            "quantity", "margin_EGP"
        ]
    )


# ---------------------------------------------------------------------
# 1. Executive Overview
# ---------------------------------------------------------------------

@router.get("/filters/options")
def filter_options():
    s = get_fact_sales()
    b = get_branches()
    return {"governorates": sorted(b.governorate_ar.dropna().astype(str).unique().tolist()) if "governorate_ar" in b else [],
            "branches": records(b[[c for c in ["branch_id", "branch_name_ar", "governorate_ar"] if c in b.columns]].drop_duplicates()) if not b.empty else [],
            "categories": sorted(s.category_en.dropna().astype(str).unique().tolist()) if "category_en" in s else [],
            "products": records(s[[c for c in ["product_id", "product_name_ar"] if c in s.columns]].drop_duplicates().sort_values("product_name_ar")) if {"product_id", "product_name_ar"}.issubset(s.columns) else [],
            "channels": sorted(s.sales_channel.dropna().astype(str).unique().tolist()) if "sales_channel" in s else []}


@router.get("/executive-overview")
def executive_overview():
    sales = clean_sales()

    if sales.empty:
        return {
            "success": True,
            "kpis": {},
            "monthly_sales_margin": [],
            "sales_by_governorate": [],
            "sales_by_category": [],
            "sales_by_channel": [],
            "insights": []
        }

    net_sales = sales["net_line_EGP"].sum()
    gross_sales = sales["gross_line_EGP"].sum()
    discount = sales["discount_line_EGP"].sum()
    units_sold = sales["quantity"].sum()
    gross_margin = sales["margin_EGP"].sum()

    orders_df = get_sales_orders().copy()
    if not orders_df.empty and "sales_order_id" in orders_df.columns:
        orders_count = int(orders_df["sales_order_id"].nunique())
        active_customers = (
            int(orders_df["customer_id"].dropna().nunique())
            if "customer_id" in orders_df.columns else 0
        )
    else:
        orders_count = (
            int(sales["sales_order_id"].nunique())
            if "sales_order_id" in sales.columns else 0
        )
        active_customers = (
            int(sales["customer_id"].dropna().nunique())
            if "customer_id" in sales.columns else 0
        )

    returns = get_fact_returns().copy()
    if not returns.empty:
        numeric_columns(returns, ["refund_amount_EGP", "return_quantity"])
        refund_amount = (
            returns["refund_amount_EGP"].sum()
            if "refund_amount_EGP" in returns.columns else 0
        )
        returned_units = (
            returns["return_quantity"].sum()
            if "return_quantity" in returns.columns else 0
        )
    else:
        refund_amount = 0
        returned_units = 0

    # Like-for-like YoY: current YTD through latest date vs same period last year.
    latest_date = sales["order_date"].max()
    current_year = int(latest_date.year)
    previous_year = current_year - 1

    current_period_sales = sales.loc[
        (sales["order_date"].dt.year == current_year)
        & (sales["order_date"] <= latest_date),
        "net_line_EGP"
    ].sum()

    # DateOffset handles leap-year boundaries (Feb 29 -> Feb 28).
    previous_period_end = latest_date - pd.DateOffset(years=1)
    previous_period_sales = sales.loc[
        (sales["order_date"].dt.year == previous_year)
        & (sales["order_date"] <= previous_period_end),
        "net_line_EGP"
    ].sum()

    sales_yoy_pct = safe_divide(
        current_period_sales - previous_period_sales,
        previous_period_sales,
        100
    )

    # Monthly trend
    sales["year_month"] = sales["order_date"].dt.to_period("M").astype(str)
    monthly = (
        sales.groupby("year_month", as_index=False)
        .agg(
            net_sales=("net_line_EGP", "sum"),
            gross_margin=("margin_EGP", "sum")
        )
        .sort_values("year_month")
    )
    monthly["margin_pct"] = monthly.apply(
        lambda row: safe_divide(row["gross_margin"], row["net_sales"], 100),
        axis=1
    )
    monthly["net_sales"] = monthly["net_sales"].round(2)
    monthly["gross_margin"] = monthly["gross_margin"].round(2)

    # Sales by governorate
    sales_by_governorate = []
    branches = get_branches().copy()
    if (
        not branches.empty
        and {"branch_id", "governorate_ar"}.issubset(branches.columns)
        and "branch_id" in sales.columns
    ):
        branch_sales = (
            sales.groupby("branch_id", as_index=False)
            .agg(
                net_sales=("net_line_EGP", "sum"),
                gross_margin=("margin_EGP", "sum")
            )
        )
        branch_sales = branch_sales.merge(
            branches[["branch_id", "governorate_ar"]].drop_duplicates("branch_id"),
            on="branch_id",
            how="left"
        )
        branch_sales["governorate_ar"] = branch_sales["governorate_ar"].fillna("غير محدد")
        governorates = (
            branch_sales.groupby("governorate_ar", as_index=False)
            .agg(
                net_sales=("net_sales", "sum"),
                gross_margin=("gross_margin", "sum")
            )
            .sort_values("net_sales", ascending=False)
        )
        governorates["margin_pct"] = governorates.apply(
            lambda row: safe_divide(row["gross_margin"], row["net_sales"], 100),
            axis=1
        )
        governorates[["net_sales", "gross_margin"]] = governorates[
            ["net_sales", "gross_margin"]
        ].round(2)
        sales_by_governorate = records(governorates)

    # Sales by category
    sales_by_category = []
    category_column = (
        "category_en" if "category_en" in sales.columns
        else "category_public" if "category_public" in sales.columns
        else None
    )
    if category_column:
        category = (
            sales.groupby(category_column, dropna=False, as_index=False)
            .agg(
                net_sales=("net_line_EGP", "sum"),
                gross_margin=("margin_EGP", "sum"),
                units_sold=("quantity", "sum")
            )
            .sort_values("net_sales", ascending=False)
            .rename(columns={category_column: "category"})
        )
        category["category"] = category["category"].fillna("غير محدد")
        category["margin_pct"] = category.apply(
            lambda row: safe_divide(row["gross_margin"], row["net_sales"], 100),
            axis=1
        )
        category[["net_sales", "gross_margin"]] = category[
            ["net_sales", "gross_margin"]
        ].round(2)
        sales_by_category = records(category)

    # Sales by channel
    sales_by_channel = []
    if "sales_channel" in sales.columns:
        aggregation = {"net_sales": ("net_line_EGP", "sum")}
        if "sales_order_id" in sales.columns:
            aggregation["orders"] = ("sales_order_id", "nunique")
        channel = (
            sales.groupby("sales_channel", dropna=False)
            .agg(**aggregation)
            .reset_index()
            .sort_values("net_sales", ascending=False)
        )
        channel["sales_channel"] = channel["sales_channel"].fillna("غير محدد")
        channel["net_sales"] = channel["net_sales"].round(2)
        sales_by_channel = records(channel)

    kpis = {
        "net_sales": money(net_sales),
        "gross_sales": money(gross_sales),
        "discount": money(discount),
        "discount_pct": safe_divide(discount, gross_sales, 100),
        "units_sold": int(units_sold),
        "orders": orders_count,
        "aov": safe_divide(net_sales, orders_count),
        "units_per_order": safe_divide(units_sold, orders_count),
        "gross_margin": money(gross_margin),
        "margin_pct": safe_divide(gross_margin, net_sales, 100),
        "active_customers": active_customers,
        # Retain this key for compatibility with the previous API response.
        "net_sales_ly": money(previous_period_sales),
        "sales_yoy_pct": sales_yoy_pct,
        "yoy_comparison_period": {
            "current_from": f"{current_year}-01-01",
            "current_to": latest_date.strftime("%Y-%m-%d"),
            "previous_from": f"{previous_year}-01-01",
            "previous_to": previous_period_end.strftime("%Y-%m-%d")
        },
        "refund_amount": money(refund_amount),
        "return_rate_value_pct": safe_divide(refund_amount, net_sales, 100),
        "return_rate_units_pct": safe_divide(returned_units, units_sold, 100)
    }

    insights = []
    if sales_yoy_pct is not None:
        trend_word = "زيادة" if sales_yoy_pct >= 0 else "انخفاض"
        insights.append(
            f"{trend_word} المبيعات بنسبة {abs(sales_yoy_pct):.2f}% "
            "مقارنة بنفس الفترة من السنة السابقة."
        )
    insights.append(
        f"هامش الربح الإجمالي {kpis['margin_pct'] or 0:.2f}%."
    )
    insights.append(
        f"المرتجعات تمثل {kpis['return_rate_value_pct'] or 0:.2f}% "
        "من صافي المبيعات بالقيمة."
    )

    return {
        "success": True,
        "kpis": kpis,
        "monthly_sales_margin": records(monthly),
        "sales_by_governorate": sales_by_governorate,
        "sales_by_category": sales_by_category,
        "sales_by_channel": sales_by_channel,
        "insights": insights
    }


# ---------------------------------------------------------------------
# 2. Sales Performance
# ---------------------------------------------------------------------

@router.get("/sales-performance")
def sales_performance():
    sales = clean_sales()

    if sales.empty:
        return {
            "success": True,
            "period": {},
            "monthly_trend": [],
            "weekday_heatmap": [],
            "sales_by_channel": [],
            "sales_by_payment_method": [],
            "top_products": []
        }

    latest_date = sales["order_date"].max()
    latest_period = latest_date.to_period("M")
    previous_period = latest_period - 1

    sales["period"] = sales["order_date"].dt.to_period("M")
    sales["year_month"] = sales["period"].astype(str)

    monthly = (
        sales.groupby(["period", "year_month"], as_index=False)
        .agg(net_sales=("net_line_EGP", "sum"))
        .sort_values("period")
    )
    monthly_lookup = {
        row["period"]: float(row["net_sales"])
        for _, row in monthly.iterrows()
    }

    monthly["net_sales_ly"] = monthly["period"].map(
        lambda period: monthly_lookup.get(period - 12)
    )
    monthly["net_sales"] = monthly["net_sales"].round(2)
    monthly["net_sales_ly"] = monthly["net_sales_ly"].apply(
        lambda value: round(value, 2) if pd.notna(value) else None
    )

    # The data usually ends mid-month. Comparing a partial month with a full one
    # produces a false drop, so MoM uses the last complete month.
    is_partial = latest_date.day != latest_date.days_in_month
    complete_period = latest_period - 1 if is_partial else latest_period
    current_month_sales = monthly_lookup.get(complete_period, 0)
    previous_month_sales = monthly_lookup.get(complete_period - 1, 0)
    monthly["partial"] = monthly["period"] == latest_period if is_partial else False
    ytd_sales = sales.loc[
        sales["order_date"].dt.year == latest_date.year,
        "net_line_EGP"
    ].sum()

    period_summary = {
        "latest_month": str(complete_period),
        "latest_month_sales": money(current_month_sales),
        "previous_month_sales": money(previous_month_sales),
        "sales_mom_pct": safe_divide(
            current_month_sales - previous_month_sales,
            previous_month_sales,
            100
        ),
        "net_sales_ytd": money(ytd_sales),
        "data_through": latest_date.strftime("%Y-%m-%d"),
        "partial_month": str(latest_period) if is_partial else None,
    }

    # Month x weekday heatmap
    sales["month_name"] = sales["order_date"].dt.month
    sales["weekday"] = sales["order_date"].dt.day_name()
    heatmap = (
        sales.groupby(["month_name", "weekday"], as_index=False)
        .agg(net_sales=("net_line_EGP", "sum"))
    )
    heatmap["net_sales"] = heatmap["net_sales"].round(2)

    # Channel breakdown
    sales_by_channel = []
    if "sales_channel" in sales.columns:
        agg = {"net_sales": ("net_line_EGP", "sum")}
        if "sales_order_id" in sales.columns:
            agg["orders"] = ("sales_order_id", "nunique")
        channel = (
            sales.groupby("sales_channel", dropna=False)
            .agg(**agg)
            .reset_index()
            .sort_values("net_sales", ascending=False)
        )
        channel["sales_channel"] = channel["sales_channel"].fillna("غير محدد")
        channel["net_sales"] = channel["net_sales"].round(2)
        sales_by_channel = records(channel)

    # Payment method breakdown
    sales_by_payment_method = []
    if "payment_method" in sales.columns:
        agg = {"net_sales": ("net_line_EGP", "sum")}
        if "sales_order_id" in sales.columns:
            agg["orders"] = ("sales_order_id", "nunique")
        payment = (
            sales.groupby("payment_method", dropna=False)
            .agg(**agg)
            .reset_index()
            .sort_values("net_sales", ascending=False)
        )
        payment["payment_method"] = payment["payment_method"].fillna("غير محدد")
        payment["net_sales"] = payment["net_sales"].round(2)
        sales_by_payment_method = records(payment)

    # Top 10 products
    top_products = []
    if "product_id" in sales.columns:
        group_columns = ["product_id"]
        if "product_name_ar" in sales.columns:
            group_columns.append("product_name_ar")

        products = (
            sales.groupby(group_columns, dropna=False, as_index=False)
            .agg(
                net_sales=("net_line_EGP", "sum"),
                units_sold=("quantity", "sum"),
                gross_margin=("margin_EGP", "sum")
            )
            .sort_values("net_sales", ascending=False)
            .head(10)
        )
        products["margin_pct"] = products.apply(
            lambda row: safe_divide(row["gross_margin"], row["net_sales"], 100),
            axis=1
        )
        products[["net_sales", "gross_margin"]] = products[
            ["net_sales", "gross_margin"]
        ].round(2)
        top_products = records(products)

    return {
        "success": True,
        "period": period_summary,
        "monthly_trend": records(
            monthly[["year_month", "net_sales", "net_sales_ly", "partial"]]
        ),
        "weekday_heatmap": records(heatmap),
        "sales_by_channel": sales_by_channel,
        "sales_by_payment_method": sales_by_payment_method,
        "top_products": top_products
    }


# ---------------------------------------------------------------------
# 3. Branches & Geography
# ---------------------------------------------------------------------

@router.get("/branches")
def branches_performance():
    sales = clean_sales()
    branches = get_branches().copy()

    if branches.empty:
        raise HTTPException(
            status_code=500,
            detail="branches.csv is empty or missing"
        )

    if "branch_id" not in branches.columns:
        raise HTTPException(
            status_code=500,
            detail="Missing branch_id in branches.csv"
        )

    # Sales and margin by branch
    if "branch_id" in sales.columns:
        branch_sales = (
            sales.groupby("branch_id", as_index=False)
            .agg(
                net_sales=("net_line_EGP", "sum"),
                gross_margin=("margin_EGP", "sum"),
                units_sold=("quantity", "sum"),
                orders=("sales_order_id", "nunique")
                if "sales_order_id" in sales.columns
                else ("net_line_EGP", "size")
            )
        )
    else:
        branch_sales = pd.DataFrame(
            columns=[
                "branch_id", "net_sales", "gross_margin",
                "units_sold", "orders"
            ]
        )

    result = branches.drop_duplicates("branch_id").merge(
        branch_sales, on="branch_id", how="left"
    )
    numeric_columns(
        result,
        ["net_sales", "gross_margin", "units_sold", "orders"]
    )
    result["margin_pct"] = result.apply(
        lambda row: safe_divide(row["gross_margin"], row["net_sales"], 100),
        axis=1
    )

    # Employee count by currently assigned branch
    employees = get_employees().copy()
    if (
        not employees.empty
        and {"employee_id", "branch_id"}.issubset(employees.columns)
    ):
        employee_counts = (
            employees.dropna(subset=["branch_id"])
            .groupby("branch_id", as_index=False)
            .agg(employee_count=("employee_id", "nunique"))
        )
        result = result.merge(employee_counts, on="branch_id", how="left")
    else:
        result["employee_count"] = 0

    result["employee_count"] = pd.to_numeric(
        result["employee_count"], errors="coerce"
    ).fillna(0)

    # Payroll accumulated by employee, mapped to current branch assignment.
    payroll = get_payroll().copy()
    if (
        not payroll.empty
        and {"employee_id", "net_paid_EGP"}.issubset(payroll.columns)
        and not employees.empty
        and {"employee_id", "branch_id"}.issubset(employees.columns)
    ):
        numeric_columns(payroll, ["net_paid_EGP"])
        employee_payroll = (
            payroll.groupby("employee_id", as_index=False)
            .agg(payroll_cost=("net_paid_EGP", "sum"))
        )
        payroll_by_branch = employee_payroll.merge(
            employees[["employee_id", "branch_id"]].drop_duplicates("employee_id"),
            on="employee_id",
            how="left"
        )
        payroll_by_branch = (
            payroll_by_branch.dropna(subset=["branch_id"])
            .groupby("branch_id", as_index=False)
            .agg(payroll_cost=("payroll_cost", "sum"))
        )
        result = result.merge(payroll_by_branch, on="branch_id", how="left")
    else:
        result["payroll_cost"] = 0

    result["payroll_cost"] = pd.to_numeric(
        result["payroll_cost"], errors="coerce"
    ).fillna(0)

    # Assign only expenses whose entity ID matches a branch ID.
    # Department costs are deliberately not allocated to branches.
    expenses = get_operating_expenses().copy()
    total_all_expenses = 0.0
    total_branch_opex = 0.0
    department_expenses_not_allocated = 0.0

    if (
        not expenses.empty
        and {"branch_or_department_id", "amount_EGP"}.issubset(expenses.columns)
    ):
        numeric_columns(expenses, ["amount_EGP"])
        total_all_expenses = expenses["amount_EGP"].sum()

        branch_ids = set(branches["branch_id"].dropna().astype(str))
        expenses["_entity_id"] = (
            expenses["branch_or_department_id"].astype(str)
        )
        branch_expenses = expenses[
            expenses["_entity_id"].isin(branch_ids)
        ].copy()

        branch_opex = (
            branch_expenses.groupby("_entity_id", as_index=False)
            .agg(opex=("amount_EGP", "sum"))
            .rename(columns={"_entity_id": "branch_id"})
        )

        total_branch_opex = branch_expenses["amount_EGP"].sum()
        department_expenses_not_allocated = (
            total_all_expenses - total_branch_opex
        )

        result["branch_id"] = result["branch_id"].astype(str)
        result = result.merge(branch_opex, on="branch_id", how="left")
    else:
        result["opex"] = 0

    result["opex"] = pd.to_numeric(
        result["opex"], errors="coerce"
    ).fillna(0)

    # Management proxy only; not accounting/statutory operating profit.
    result["operating_profit_proxy"] = (
        result["gross_margin"]
        - result["opex"]
        - result["payroll_cost"]
    )
    result["sales_per_employee"] = result.apply(
        lambda row: safe_divide(
            row["net_sales"], row["employee_count"]
        ),
        axis=1
    )

    total_net_sales = result["net_sales"].sum()
    result["sales_share_pct"] = result["net_sales"].apply(
        lambda value: safe_divide(value, total_net_sales, 100)
    )
    result = result.sort_values("net_sales", ascending=False)
    result["sales_rank"] = range(1, len(result) + 1)

    # Governorate summary
    governorate_performance = []
    if "governorate_ar" in result.columns:
        governorates = (
            result.groupby("governorate_ar", dropna=False, as_index=False)
            .agg(
                net_sales=("net_sales", "sum"),
                gross_margin=("gross_margin", "sum"),
                opex=("opex", "sum"),
                payroll_cost=("payroll_cost", "sum"),
                employee_count=("employee_count", "sum"),
                operating_profit_proxy=("operating_profit_proxy", "sum")
            )
            .sort_values("net_sales", ascending=False)
        )
        governorates["governorate_ar"] = (
            governorates["governorate_ar"].fillna("غير محدد")
        )
        governorates["margin_pct"] = governorates.apply(
            lambda row: safe_divide(
                row["gross_margin"], row["net_sales"], 100
            ),
            axis=1
        )
        money_cols = [
            "net_sales", "gross_margin", "opex",
            "payroll_cost", "operating_profit_proxy"
        ]
        governorates[money_cols] = governorates[money_cols].round(2)
        governorate_performance = records(governorates)

    # Retail location type summary
    retail_location_performance = []
    if "retail_location_type" in result.columns:
        retail = (
            result.groupby(
                "retail_location_type", dropna=False, as_index=False
            )
            .agg(
                branch_count=("branch_id", "nunique"),
                net_sales=("net_sales", "sum"),
                gross_margin=("gross_margin", "sum"),
                opex=("opex", "sum"),
                payroll_cost=("payroll_cost", "sum"),
                employee_count=("employee_count", "sum"),
                operating_profit_proxy=("operating_profit_proxy", "sum")
            )
            .sort_values("net_sales", ascending=False)
        )
        retail["retail_location_type"] = (
            retail["retail_location_type"].fillna("غير محدد")
        )
        retail["margin_pct"] = retail.apply(
            lambda row: safe_divide(
                row["gross_margin"], row["net_sales"], 100
            ),
            axis=1
        )
        retail_location_performance = records(retail)

    summary = {
        "branch_count": int(result["branch_id"].nunique()),
        "total_net_sales": money(result["net_sales"].sum()),
        "total_branch_opex": money(total_branch_opex),
        "total_all_expenses": money(total_all_expenses),
        "department_expenses_not_allocated": money(
            department_expenses_not_allocated
        ),
        "total_branch_payroll": money(result["payroll_cost"].sum())
    }

    # Round monetary/ratio fields in branch-level output.
    for column in [
        "net_sales", "gross_margin", "margin_pct", "payroll_cost",
        "opex", "operating_profit_proxy", "sales_per_employee",
        "sales_share_pct"
    ]:
        if column in result.columns:
            result[column] = pd.to_numeric(
                result[column], errors="coerce"
            ).round(2)

    return {
        "success": True,
        "summary": summary,
        "branches": records(result),
        "governorate_performance": governorate_performance,
        "retail_location_performance": retail_location_performance
    }
