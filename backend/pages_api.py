"""Analytics endpoints for Products, Customers, Returns, Inventory, Procurement, Marketing and Workforce.

Every figure is computed from the CSV files. Where a metric could mislead (partial months,
anonymous orders, USD imports, campaign attribution) the response carries an explicit note.
"""
from functools import lru_cache

import pandas as pd
from fastapi import APIRouter

from backend.analytics_api import (
    DATA_DIR, _read_csv, apply_global_filters, get_branches, get_employees, get_fact_returns, get_fact_sales,
    get_operating_expenses, get_payroll, get_sales_orders, money, records, safe_divide,
)

router = APIRouter(prefix="/api/analytics", tags=["Page Analytics"])


@lru_cache(maxsize=None)
def csv(name: str) -> pd.DataFrame:
    return _read_csv(DATA_DIR / name, required=False)


@lru_cache(maxsize=1)
def sales() -> pd.DataFrame:
    cols = ["sales_order_id", "branch_id", "customer_id", "sales_channel", "sku_id", "product_id",
            "product_name_ar", "category_en", "audience", "quantity", "gross_line_EGP",
            "discount_line_EGP", "net_line_EGP", "margin_EGP", "year_month"]
    return apply_global_filters(get_fact_sales())[cols]


def warm_up() -> None:
    for fn in (sales, get_sales_orders, get_fact_returns, get_branches, get_employees, get_payroll, get_operating_expenses):
        fn()


def pct(a, b):
    return safe_divide(a, b, 100)


def rec(df: pd.DataFrame, digits: int = 2) -> list:
    return records(df.round(digits))


def monthly_flag(ym: pd.Series) -> str | None:
    """Return the latest YYYY-MM when the sales data ends mid-month."""
    last = get_sales_orders()["order_date"].max()
    return last.strftime("%Y-%m") if last.day != last.days_in_month else None


def complete_months(n: int) -> list:
    last = get_sales_orders()["order_date"].max()
    end = last.to_period("M") - (1 if last.day != last.days_in_month else 0)
    return [str(end - i) for i in range(n)]


# ------------------------------------------------------------------ products
@router.get("/products")
def products():
    s = sales()
    net, units = s.net_line_EGP.sum(), s.quantity.sum()

    def perf(keys):
        g = s.groupby(keys).agg(net_sales=("net_line_EGP", "sum"), gross=("gross_line_EGP", "sum"),
                                discount=("discount_line_EGP", "sum"), margin=("margin_EGP", "sum"),
                                units=("quantity", "sum")).reset_index()
        g["margin_pct"] = g.margin / g.net_sales * 100
        g["discount_pct"] = g.discount / g.gross * 100
        g["avg_price"] = g.net_sales / g.units
        return g.sort_values("net_sales", ascending=False)

    prod = perf(["product_id", "product_name_ar", "category_en"])
    sku = csv("sku_variants.csv")[["sku_id", "size", "color_ar"]]
    by_sku = s.groupby("sku_id").agg(units=("quantity", "sum"), net_sales=("net_line_EGP", "sum")).reset_index().merge(sku, on="sku_id")
    matrix = s.groupby(["category_en", "audience"]).agg(net=("net_line_EGP", "sum"), margin=("margin_EGP", "sum")).reset_index()
    matrix["margin_pct"] = matrix.margin / matrix.net * 100
    dim = csv("processed/dim_product.csv")
    return {
        "success": True,
        "kpis": {"products_sold": int(s.product_id.nunique()), "categories": int(s.category_en.nunique()),
                 "net_sales": money(net), "margin_pct": pct(s.margin_EGP.sum(), net),
                 "discount_pct": pct(s.discount_line_EGP.sum(), s.gross_line_EGP.sum()),
                 "avg_selling_price": safe_divide(net, units), "units_sold": int(units)},
        "category_performance": rec(perf(["category_en"])),
        "audience_performance": rec(perf(["audience"])),
        "top_products": rec(prod.head(15)),
        "low_margin_products": rec(prod[prod.net_sales >= prod.net_sales.median()].nsmallest(10, "margin_pct")),
        "size_demand": rec(by_sku.groupby("size").agg(units=("units", "sum"), net_sales=("net_sales", "sum")).reset_index().sort_values("units", ascending=False)),
        "color_demand": rec(by_sku.groupby("color_ar").agg(units=("units", "sum"), net_sales=("net_sales", "sum")).reset_index().sort_values("units", ascending=False).head(10)),
        "category_audience_matrix": rec(matrix[["category_en", "audience", "net", "margin_pct"]]),
        "catalog_match": rec(dim.groupby("match_status").size().rename("products").reset_index()) if "match_status" in dim else [],
    }


# ----------------------------------------------------------------- customers
@router.get("/customers")
def customers():
    c, o = csv("customers.csv"), get_sales_orders()
    known = o[o.customer_id.notna()]
    asof = o.order_date.max()
    per = known.groupby("customer_id").agg(orders=("sales_order_id", "nunique"), net=("net_before_tax_EGP", "sum"),
                                           last=("order_date", "max")).reset_index()
    per = per.merge(c[["customer_id", "customer_segment", "age_band", "governorate_ar", "customer_name_ar"]], on="customer_id", how="left")

    def by(col):
        g = per.groupby(col).agg(customers=("customer_id", "count"), orders=("orders", "sum"), net_sales=("net", "sum")).reset_index()
        g["aov"] = g.net_sales / g.orders
        g["share_pct"] = g.net_sales / g.net_sales.sum() * 100
        return g.sort_values("net_sales", ascending=False)

    per["days_since"] = (asof - per["last"]).dt.days
    rec_bins = pd.cut(per.days_since, [-1, 30, 90, 180, 365, 10**6], labels=["0-30 days", "31-90 days", "91-180 days", "181-365 days", "Over 365 days"])
    freq = pd.cut(per.orders, [0, 1, 2, 3, 5, 10**6], labels=["1 order", "2 orders", "3 orders", "4-5 orders", "6+ orders"])
    joined = pd.to_datetime(c.joined_date, errors="coerce").dt.strftime("%Y-%m")
    return {
        "success": True,
        "kpis": {"customers_total": int(len(c)), "purchasing_customers": int(len(per)),
                 "repeat_customers": int((per.orders > 1).sum()), "repeat_rate_pct": pct((per.orders > 1).sum(), len(per)),
                 "revenue_per_customer": money(per.net.mean()), "orders_per_customer": money(per.orders.mean()),
                 "orders_without_customer_id": int(o.customer_id.isna().sum()),
                 "net_sales_without_customer_id_pct": pct(o.loc[o.customer_id.isna(), "net_before_tax_EGP"].sum(), o.net_before_tax_EGP.sum())},
        "segments": rec(by("customer_segment")), "age_bands": rec(by("age_band")),
        "governorates": rec(by("governorate_ar").head(12)),
        "recency": rec(per.groupby(rec_bins, observed=False).agg(customers=("customer_id", "count"), net_sales=("net", "sum")).reset_index().rename(columns={"days_since": "bucket"})),
        "frequency": rec(per.groupby(freq, observed=False).agg(customers=("customer_id", "count")).reset_index().rename(columns={"orders": "bucket"})),
        "new_customers_monthly": rec(joined.value_counts().sort_index().rename_axis("year_month").reset_index(name="customers")),
        "top_customers": rec(per.nlargest(10, "net")[["customer_id", "customer_name_ar", "customer_segment", "orders", "net", "last"]].assign(last=lambda d: d["last"].dt.strftime("%Y-%m-%d"))),
        "notes": {"data_through": asof.strftime("%Y-%m-%d"),
                  "anonymous_orders": "Orders without a customer ID are excluded from customer metrics."},
    }


# ------------------------------------------------------------------- returns
@router.get("/returns")
def returns_and_delivery():
    fr, s, ds = apply_global_filters(get_fact_returns(), "return_date"), sales(), csv("delivery_shipments.csv").copy()
    net, units = s.net_line_EGP.sum(), s.quantity.sum()
    sku = csv("sku_variants.csv")[["sku_id", "size"]]
    sold_size = s.merge(sku, on="sku_id").groupby("size").quantity.sum()
    ret_size = fr.merge(sku, on="sku_id").groupby("size").return_quantity.sum()
    size = pd.DataFrame({"returned_units": ret_size, "sold_units": sold_size}).dropna().reset_index()
    size["return_rate_pct"] = size.returned_units / size.sold_units * 100
    cat = fr.groupby("category_en").agg(refund=("refund_amount_EGP", "sum"), returned_units=("return_quantity", "sum")).join(s.groupby("category_en").quantity.sum().rename("sold_units")).reset_index()
    cat["return_rate_pct"] = cat.returned_units / cat.sold_units * 100
    reasons = fr.groupby("reason").agg(returns=("return_id", "count"), units=("return_quantity", "sum"), refund=("refund_amount_EGP", "sum")).reset_index()
    reasons["share_pct"] = reasons.refund / reasons.refund.sum() * 100
    mon = fr.groupby("return_year_month").agg(refund=("refund_amount_EGP", "sum"), units=("return_quantity", "sum")).join(s.groupby("year_month").net_line_EGP.sum().rename("net_sales")).reset_index().rename(columns={"return_year_month": "year_month"})
    mon["return_rate_pct"] = mon.refund / mon.net_sales * 100
    days = pd.cut(fr.days_to_return, [-1, 7, 14, 30, 60, 10**6], labels=["0-7 days", "8-14 days", "15-30 days", "31-60 days", "Over 60 days"])
    for col in ("ship_date", "delivery_date"):
        ds[col] = pd.to_datetime(ds[col], errors="coerce")
    ds["days"] = (ds.delivery_date - ds.ship_date).dt.days
    ds["delayed"] = ds.fulfillment_status.eq("Delayed")

    def dl(col):
        g = ds.groupby(col).agg(shipments=("shipment_id", "count"), avg_days=("days", "mean"), delayed_pct=("delayed", "mean"), avg_fee=("shipping_fee_EGP", "mean"), total_fee=("shipping_fee_EGP", "sum")).reset_index()
        g["delayed_pct"] *= 100
        return g.sort_values("shipments", ascending=False)

    ecom = s.loc[s.sales_channel == "E-commerce", "net_line_EGP"].sum()
    dmon = ds.groupby(ds.ship_date.dt.strftime("%Y-%m")).agg(shipments=("shipment_id", "count"), delayed_pct=("delayed", "mean")).reset_index().rename(columns={"ship_date": "year_month"})
    dmon["delayed_pct"] *= 100
    return {
        "success": True,
        "kpis": {"refund_amount": money(fr.refund_amount_EGP.sum()), "returns": int(len(fr)), "returned_units": int(fr.return_quantity.sum()),
                 "return_rate_value_pct": pct(fr.refund_amount_EGP.sum(), net), "return_rate_units_pct": pct(fr.return_quantity.sum(), units),
                 "avg_days_to_return": money(fr.days_to_return.mean()), "shipments": int(len(ds)),
                 "avg_delivery_days": money(ds.days.mean()), "delayed_pct": money(ds.delayed.mean() * 100),
                 "shipping_fees": money(ds.shipping_fee_EGP.sum()), "shipping_fee_pct_of_ecommerce_sales": pct(ds.shipping_fee_EGP.sum(), ecom)},
        "reasons": rec(reasons.sort_values("refund", ascending=False)), "by_category": rec(cat.sort_values("return_rate_pct", ascending=False)),
        "by_size": rec(size.sort_values("return_rate_pct", ascending=False)), "monthly": rec(mon),
        "days_to_return": rec(fr.groupby(days, observed=False).size().rename("returns").reset_index().rename(columns={"days_to_return": "bucket"})),
        "carriers": rec(dl("carrier")), "delivery_governorates": rec(dl("ship_to_governorate")),
        "delivery_monthly": rec(dmon),
        "notes": {"delivery": "Shipments exist for e-commerce orders only, so shipping fees are compared with e-commerce sales."},
    }


# ----------------------------------------------------------------- inventory
@router.get("/inventory")
def inventory():
    ms, wh, br = csv("monthly_stock.csv"), csv("warehouses.csv"), get_branches()
    snap = complete_months(1)[0]
    cur = ms[ms.year_month == snap]
    s = sales()
    last12 = complete_months(12)
    monthly_units = s[s.year_month.isin(last12)].groupby("category_en").quantity.sum() / 12
    cat = cur.groupby("product_category").agg(units=("closing_units", "sum"), value=("closing_stock_value_EGP", "sum"), avg_risk=("stockout_risk_score", "mean")).join(monthly_units.rename("monthly_units_sold")).reset_index()
    cat["cover_months"] = cat.units / cat.monthly_units_sold
    wmap = cur[cur.stock_location_type == "Warehouse"].groupby("stock_location_id").agg(units=("closing_units", "sum"), avg_risk=("stockout_risk_score", "mean")).reset_index()
    wh_u = wh.merge(wmap, left_on="warehouse_id", right_on="stock_location_id", how="left")
    wh_u["utilization_pct"] = wh_u.units / wh_u.capacity_units * 100
    bmap = cur[cur.stock_location_type == "Branch"].groupby("stock_location_id").agg(units=("closing_units", "sum"), avg_risk=("stockout_risk_score", "mean")).reset_index().merge(br[["branch_id", "branch_name_ar", "governorate_ar"]], left_on="stock_location_id", right_on="branch_id", how="left")
    tr, items = csv("inventory_transfers.csv").copy(), csv("inventory_transfer_items.csv")
    tr = tr.merge(items.groupby("transfer_id").quantity_units.sum().rename("units").reset_index(), on="transfer_id", how="left")
    tr["month"] = tr.transfer_date.astype(str).str[:7]
    dest = tr.groupby("destination_branch_id").agg(transfers=("transfer_id", "count"), units=("units", "sum"), cost=("transport_cost_EGP", "sum")).reset_index().merge(br[["branch_id", "branch_name_ar"]], left_on="destination_branch_id", right_on="branch_id", how="left")
    dest["cost_per_unit"] = dest.cost / dest.units
    trend = ms.groupby("year_month").agg(stock_value=("closing_stock_value_EGP", "sum"), units=("closing_units", "sum"), avg_risk=("stockout_risk_score", "mean")).reset_index()
    fac = csv("factories.csv")
    over = wh_u[wh_u.utilization_pct > 100]
    warnings = [{"code": "over_capacity", "warehouses": int(len(over)), "total": int(len(wh_u))}] if len(over) else []
    return {
        "success": True, "snapshot_month": snap, "warnings": warnings,
        "kpis": {"stock_units": int(cur.closing_units.sum()), "stock_value": money(cur.closing_stock_value_EGP.sum()),
                 "avg_stockout_risk": money(cur.stockout_risk_score.mean()), "stock_cover_months": safe_divide(cur.closing_units.sum(), monthly_units.sum()),
                 "transfers": int(len(tr)), "units_transferred": int(tr.units.sum()), "transfer_cost": money(tr.transport_cost_EGP.sum()),
                 "transfer_cost_per_unit": safe_divide(tr.transport_cost_EGP.sum(), tr.units.sum())},
        "by_category": rec(cat.sort_values("value", ascending=False)), "stock_trend": rec(trend),
        "warehouses": rec(wh_u[["warehouse_label", "governorate_ar", "warehouse_kind", "capacity_units", "units", "utilization_pct", "avg_risk"]].sort_values("utilization_pct", ascending=False)),
        "highest_risk_branches": rec(bmap.nlargest(10, "avg_risk")[["branch_name_ar", "governorate_ar", "units", "avg_risk"]]),
        "transfers_monthly": rec(tr.groupby("month").agg(transfers=("transfer_id", "count"), units=("units", "sum"), cost=("transport_cost_EGP", "sum")).reset_index()),
        "transfer_status": rec(tr.groupby("transfer_status").size().rename("transfers").reset_index()),
        "top_destinations": rec(dest.nlargest(10, "units")[["branch_name_ar", "transfers", "units", "cost", "cost_per_unit"]]),
        "factories": rec(fac.groupby("production_focus").size().rename("factories").reset_index()),
        "notes": {"snapshot": "Stock uses the last complete month. Cover = units in stock / average monthly units sold over the last 12 complete months."},
    }


# -------------------------------------------------------------- procurement
@router.get("/procurement")
def procurement():
    po, poi, sup = csv("purchase_orders.csv"), csv("purchase_order_items.csv"), csv("suppliers.csv")
    imp, ip = csv("import_shipments.csv"), csv("import_partners.csv")
    m = poi.merge(po[["po_id", "supplier_id", "po_date", "po_status", "po_purpose"]], on="po_id", how="left")
    m["lead"] = (pd.to_datetime(m.delivery_date, errors="coerce") - pd.to_datetime(m.po_date, errors="coerce")).dt.days
    m["month"] = m.po_date.astype(str).str[:7]
    cost = m.line_cost_EGP.sum()
    sp = m.groupby("supplier_id").agg(cost=("line_cost_EGP", "sum"), po_count=("po_id", "nunique"), avg_lead_days=("lead", "mean")).reset_index().merge(sup, on="supplier_id", how="left")
    partial = po.groupby("supplier_id").po_status.apply(lambda x: (x == "Partial receipt").mean() * 100).rename("partial_receipt_pct").reset_index()
    sp = sp.merge(partial, on="supplier_id", how="left")
    sp["share_pct"] = sp.cost / cost * 100
    sp = sp.sort_values("cost", ascending=False)
    i = imp.merge(ip, on="import_partner_id", how="left")
    i["landed"] = i.customs_value_USD + i.freight_USD + i.duty_and_tax_USD
    i["month"] = i.shipment_date.astype(str).str[:7]

    def ib(col):
        g = i.groupby(col).agg(shipments=("import_shipment_id", "count"), customs_value=("customs_value_USD", "sum"), freight=("freight_USD", "sum"), duty=("duty_and_tax_USD", "sum"), landed=("landed", "sum")).reset_index()
        g["freight_duty_pct"] = (g.freight + g.duty) / g.customs_value * 100
        return g.sort_values("landed", ascending=False)

    sold_units = int(sales().quantity.sum())
    warnings = []
    if m.quantity.sum() > 5 * sold_units:
        warnings.append({"code": "purchase_volume", "purchased_units": int(m.quantity.sum()), "sold_units": sold_units,
                         "ratio": safe_divide(m.quantity.sum(), sold_units)})
    return {
        "success": True, "warnings": warnings,
        "kpis": {"purchase_cost_egp": money(cost), "purchased_units": int(m.quantity.sum()), "po_count": int(len(po)), "avg_unit_cost": safe_divide(cost, m.quantity.sum()),
                 "avg_lead_days": money(m.lead.mean()), "partial_receipt_pct": pct((po.po_status == "Partial receipt").sum(), len(po)),
                 "top5_supplier_share_pct": money(sp.share_pct.head(5).sum()), "suppliers": int(len(sup)),
                 "import_customs_value_usd": money(i.customs_value_USD.sum()), "import_landed_usd": money(i.landed.sum()),
                 "freight_duty_pct": pct(i.freight_USD.sum() + i.duty_and_tax_USD.sum(), i.customs_value_USD.sum()), "import_shipments": int(len(i))},
        "suppliers": rec(sp[["supplier_name_ar", "material_type", "cost", "share_pct", "po_count", "avg_lead_days", "partial_receipt_pct"]].head(15)),
        "material_types": rec(sp.groupby("material_type").cost.sum().reset_index().sort_values("cost", ascending=False)),
        "monthly_cost": rec(m.groupby("month").line_cost_EGP.sum().rename("cost").reset_index()),
        "po_status": rec(po.groupby("po_status").size().rename("orders").reset_index()),
        "po_purpose": rec(m.groupby("po_purpose").line_cost_EGP.sum().rename("cost").reset_index().sort_values("cost", ascending=False)),
        "imports_by_country": rec(ib("country")), "imports_by_commodity": rec(ib("commodity_class")), "imports_by_port": rec(ib("port_name")),
        "imports_monthly": rec(i.groupby("month").landed.sum().rename("landed").reset_index()),
        "notes": {"currency": "Purchase orders are in EGP. Imports are in USD and are never added to EGP totals."},
    }


# ----------------------------------------------------------------- marketing
@router.get("/marketing")
def marketing():
    mk, s, br = csv("marketing_campaigns.csv").copy(), sales(), get_branches()
    mk["month"] = mk.start_date.astype(str).str[:7]

    def by(col):
        g = mk.groupby(col).agg(campaigns=("campaign_id", "count"), spend=("spend_EGP", "sum"), budget=("budget_EGP", "sum"), impressions=("impressions", "sum"), clicks=("clicks", "sum"), orders=("orders_attributed", "sum")).reset_index()
        g["ctr_pct"], g["cpc"], g["cost_per_order"] = g.clicks / g.impressions * 100, g.spend / g.clicks, g.spend / g.orders
        return g.sort_values("spend", ascending=False)

    gov_sales = s.merge(br[["branch_id", "governorate_ar"]], on="branch_id", how="left").groupby("governorate_ar").net_line_EGP.sum().rename("net_sales")
    gov = by("governorate_ar").merge(gov_sales, left_on="governorate_ar", right_index=True, how="left")
    gov["sales_per_spend_egp"] = gov.net_sales / gov.spend
    top = mk.nlargest(15, "spend_EGP").assign(ctr_pct=lambda d: d.clicks / d.impressions * 100, cost_per_order=lambda d: d.spend_EGP / d.orders_attributed, utilization_pct=lambda d: d.spend_EGP / d.budget_EGP * 100)
    tot = {k: float(mk[c].sum()) for k, c in [("impressions", "impressions"), ("clicks", "clicks"), ("orders", "orders_attributed")]}
    total_orders = int(s.sales_order_id.nunique())
    warnings = []
    if tot["orders"] > total_orders:
        warnings.append({"code": "attributed_orders", "attributed": int(tot["orders"]), "total_orders": total_orders,
                         "ratio": safe_divide(tot["orders"], total_orders)})
    return {
        "success": True, "warnings": warnings,
        "kpis": {"spend": money(mk.spend_EGP.sum()), "spend_pct_of_sales": pct(mk.spend_EGP.sum(), s.net_line_EGP.sum()), "budget": money(mk.budget_EGP.sum()), "budget_utilization_pct": pct(mk.spend_EGP.sum(), mk.budget_EGP.sum()),
                 "impressions": int(tot["impressions"]), "clicks": int(tot["clicks"]), "ctr_pct": pct(tot["clicks"], tot["impressions"]),
                 "cpc": safe_divide(mk.spend_EGP.sum(), tot["clicks"]), "attributed_orders": int(tot["orders"]),
                 "cost_per_order": safe_divide(mk.spend_EGP.sum(), tot["orders"]), "campaigns": int(len(mk)),
                 "attributed_orders_share_pct": pct(tot["orders"], s.sales_order_id.nunique())},
        "channels": rec(by("channel")), "audiences": rec(by("target_audience")), "governorates": rec(gov),
        "monthly": rec(mk.groupby("month").agg(spend=("spend_EGP", "sum"), clicks=("clicks", "sum"), orders=("orders_attributed", "sum")).reset_index()),
        "top_campaigns": rec(top[["campaign_id", "start_date", "end_date", "channel", "governorate_ar", "spend_EGP", "utilization_pct", "ctr_pct", "cost_per_order"]]),
        "funnel": [{"stage": "Impressions", "value": tot["impressions"]}, {"stage": "Clicks", "value": tot["clicks"]}, {"stage": "Attributed orders", "value": tot["orders"]}],
        "notes": {"attribution": "Campaigns have no order-level link. Sales per spend by governorate shows correlation over all years, not revenue caused by a campaign."},
    }


# ----------------------------------------------------------------- workforce
@router.get("/workforce")
def workforce():
    emp, pay, ox, s = get_employees(), get_payroll(), get_operating_expenses(), sales()
    pay = pay.copy()
    pay["month"] = pay.pay_month.astype(str).str[:7]
    pay["gross"] = pay.base_salary_EGP + pay.overtime_EGP + pay.bonus_EGP
    ox = ox.copy()
    ox["month"] = ox.expense_date.astype(str).str[:7]
    ox["scope"] = ox.branch_or_department_id.astype(str).str[:2].map({"BR": "Branches", "WH": "Warehouses"}).fillna("Other")
    net, gm = s.net_line_EGP.sum(), s.margin_EGP.sum()
    sm = s.groupby("year_month").agg(net_sales=("net_line_EGP", "sum"), gross_margin=("margin_EGP", "sum"))
    monthly = sm.join(pay.groupby("month").gross.sum().rename("payroll"), how="outer").join(ox.groupby("month").amount_EGP.sum().rename("opex"), how="outer").fillna(0).reset_index().rename(columns={"index": "year_month"})
    pos = emp.groupby("position_en").agg(headcount=("employee_id", "count"), avg_salary=("salary_base_EGP_2026", "mean")).reset_index().sort_values("headcount", ascending=False)
    return {
        "success": True,
        "kpis": {"employees": int(len(emp)), "payroll_cost": money(pay.gross.sum()), "net_paid": money(pay.net_paid_EGP.sum()),
                 "payroll_pct_of_sales": pct(pay.gross.sum(), net), "overtime_pct_of_base": pct(pay.overtime_EGP.sum(), pay.base_salary_EGP.sum()),
                 "bonus_pct_of_base": pct(pay.bonus_EGP.sum(), pay.base_salary_EGP.sum()), "deductions": money(pay.deductions_EGP.sum()),
                 "opex": money(ox.amount_EGP.sum()), "opex_pct_of_sales": pct(ox.amount_EGP.sum(), net),
                 "operating_result_proxy": money(gm - pay.gross.sum() - ox.amount_EGP.sum()), "avg_salary": money(emp.salary_base_EGP_2026.mean())},
        "monthly": rec(monthly), "opex_by_category": rec(ox.groupby("expense_category").amount_EGP.sum().rename("amount").reset_index().sort_values("amount", ascending=False)),
        "opex_by_scope": rec(ox.groupby("scope").amount_EGP.sum().rename("amount").reset_index()),
        "top_vendors": rec(ox.groupby("vendor_name").amount_EGP.sum().rename("amount").reset_index().nlargest(10, "amount")),
        "payment_methods": rec(ox.groupby("payment_method").amount_EGP.sum().rename("amount").reset_index().sort_values("amount", ascending=False)),
        "positions": rec(pos),
        "notes": {"proxy": "Operating result proxy = gross margin - payroll cost (base + overtime + bonus) - operating expenses. It excludes purchasing, marketing and import costs."},
    }
