import { Boxes, Clock, Package, Percent, Repeat, Tag, Truck, Undo2, UserPlus, Users, Wallet, Warehouse } from "lucide-react";
import { BarList, Card, compact, Donut, egp, Grid, Heat, Kpis, n, Notice, Page, pct, Table, Trend, useT } from "../ui.jsx";

const A = "/api/analytics/";

export function Products() {
  const tr = useT();
  return (
    <Page urls={[A + "products"]}>
      {(d) => {
        const k = d.kpis;
        return (
          <>
            <Kpis items={[
              { label: tr("Products sold", "منتجات تم بيعها"), value: k.products_sold, icon: Package, note: `${k.categories} ${tr("categories", "فئة")}` },
              { label: tr("Net sales", "صافي المبيعات"), value: k.net_sales, fmt: egp, icon: Wallet, tone: "blue" },
              { label: tr("Gross margin", "هامش الربح"), value: k.margin_pct, fmt: pct, icon: Percent, note: tr("of net sales", "من صافي المبيعات") },
              { label: tr("Discount rate", "نسبة الخصم"), value: k.discount_pct, fmt: pct, icon: Tag, tone: "pink", note: tr("of gross sales", "من المبيعات الإجمالية") },
              { label: tr("Average selling price", "متوسط سعر البيع"), value: k.avg_selling_price, fmt: egp, icon: Wallet, tone: "blue", note: tr("per unit, net", "للوحدة، صافي") },
              { label: tr("Units sold", "الوحدات المباعة"), value: k.units_sold, icon: Boxes },
            ]} />
            <Grid cols={2}>
              <Card title={tr("Categories by net sales", "الفئات حسب صافي المبيعات")} sub={tr("With margin", "مع الهامش")}>
                <BarList rows={d.category_performance.map((r) => ({ label: r.category_en, value: r.net_sales, note: pct(r.margin_pct) }))} fmt={egp} />
              </Card>
              <Card title={tr("Audience mix", "توزيع الجمهور")}>
                <Donut data={d.audience_performance} nameKey="audience" valueKey="net_sales" fmt={egp} />
              </Card>
            </Grid>
            <Card title={tr("Margin by category and audience", "الهامش حسب الفئة والجمهور")} sub={tr("Darker = higher margin", "الأغمق = هامش أعلى")}>
              <Heat rows={d.category_audience_matrix} rowKey="category_en" colKey="audience" valKey="margin_pct" fmt={(v) => pct(v, 0)} />
            </Card>
            <Grid cols={2}>
              <Card title={tr("Top 15 products", "أعلى 15 منتج")}>
                <Table max={8} cols={[
                  { k: "product_name_ar", label: tr("Product", "المنتج") },
                  { k: "net_sales", label: tr("Net sales", "صافي المبيعات"), r: egp, num: true },
                  { k: "margin_pct", label: tr("Margin", "الهامش"), r: pct, num: true },
                  { k: "discount_pct", label: tr("Discount", "الخصم"), r: pct, num: true },
                ]} rows={d.top_products} />
              </Card>
              <Card title={tr("Lowest margins among larger products", "أقل هامش بين المنتجات الأكبر")} sub={tr("Products above median sales", "منتجات أعلى من متوسط المبيعات")}>
                <Table max={8} cols={[
                  { k: "product_name_ar", label: tr("Product", "المنتج") },
                  { k: "margin_pct", label: tr("Margin", "الهامش"), r: pct, num: true },
                  { k: "discount_pct", label: tr("Discount", "الخصم"), r: pct, num: true },
                  { k: "net_sales", label: tr("Net sales", "صافي المبيعات"), r: egp, num: true },
                ]} rows={d.low_margin_products} />
              </Card>
            </Grid>
            <Grid cols={2}>
              <Card title={tr("Units by size", "الوحدات حسب المقاس")}><BarList rows={d.size_demand.map((r) => ({ label: r.size, value: r.units }))} fmt={n} color="#2F6FDE" /></Card>
              <Card title={tr("Top colors", "أكثر الألوان")}><BarList rows={d.color_demand.map((r) => ({ label: r.color_ar, value: r.units }))} fmt={n} color="#E96FC6" /></Card>
            </Grid>
          </>
        );
      }}
    </Page>
  );
}

export function Customers() {
  const tr = useT();
  return (
    <Page urls={[A + "customers"]}>
      {(d) => {
        const k = d.kpis;
        const bar = (rows, key, val = "net_sales") => rows.map((r) => ({ label: String(r[key]), value: r[val], note: val === "net_sales" ? `${n(r.customers)} ${tr("customers", "عميل")}` : undefined }));
        return (
          <>
            <Kpis items={[
              { label: tr("Registered customers", "العملاء المسجلون"), value: k.customers_total, icon: Users, note: `${n(k.purchasing_customers)} ${tr("have purchases", "لديهم مشتريات")}` },
              { label: tr("Repeat customers", "عملاء متكررون"), value: k.repeat_rate_pct, fmt: pct, icon: Repeat, tone: "blue", note: `${n(k.repeat_customers)} ${tr("with 2+ orders", "لديهم طلبان فأكثر")}` },
              { label: tr("Revenue per customer", "الإيراد لكل عميل"), value: k.revenue_per_customer, fmt: egp, icon: Wallet },
              { label: tr("Orders per customer", "الطلبات لكل عميل"), value: k.orders_per_customer, fmt: (v) => n(v, 1), icon: Package, tone: "pink" },
              { label: tr("Orders without customer ID", "طلبات بلا معرف عميل"), value: k.orders_without_customer_id, icon: Users, tone: "pink", note: `${pct(k.net_sales_without_customer_id_pct)} ${tr("of net sales", "من صافي المبيعات")}` },
            ]} />
            <Notice>{tr(`${pct(k.net_sales_without_customer_id_pct)} of net sales come from orders with no customer ID, so customer metrics cover the rest only.`, `${pct(k.net_sales_without_customer_id_pct)} من صافي المبيعات طلبات بلا معرف عميل، لذلك تغطي مؤشرات العملاء الباقي فقط.`)}</Notice>
            <Grid cols={2}>
              <Card title={tr("Segments", "الشرائح")} sub={tr("Net sales, with average order", "صافي المبيعات مع متوسط الطلب")}>
                <BarList rows={d.segments.map((r) => ({ label: r.customer_segment, value: r.net_sales, note: `${tr("AOV", "متوسط الطلب")} ${egp(r.aov)}` }))} fmt={egp} />
              </Card>
              <Card title={tr("Age bands", "الفئات العمرية")}><BarList rows={bar(d.age_bands, "age_band")} fmt={egp} color="#2F6FDE" /></Card>
            </Grid>
            <Grid cols={3}>
              <Card title={tr("Days since last order", "الأيام منذ آخر طلب")} sub={tr("Customers per bucket", "عدد العملاء")}><BarList rows={bar(d.recency, "bucket", "customers")} fmt={n} color="#E96FC6" /></Card>
              <Card title={tr("Orders per customer", "الطلبات لكل عميل")}><BarList rows={bar(d.frequency, "bucket", "customers")} fmt={n} /></Card>
              <Card title={tr("Top governorates", "أعلى المحافظات")}><BarList rows={d.governorates.slice(0, 7).map((r) => ({ label: r.governorate_ar, value: r.net_sales }))} fmt={egp} color="#2F6FDE" /></Card>
            </Grid>
            <Card title={tr("New customers by month", "العملاء الجدد شهريًا")} sub={tr("By registration date", "حسب تاريخ التسجيل")}>
              <Trend data={d.new_customers_monthly} series={[{ key: "customers", name: tr("New customers", "عملاء جدد"), type: "area", color: "#6D4AFF" }]} fmtL={(v) => n(v)} />
            </Card>
            <Card title={tr("Top customers", "أهم العملاء")}>
              <Table max={10} cols={[
                { k: "customer_name_ar", label: tr("Customer", "العميل") },
                { k: "customer_segment", label: tr("Segment", "الشريحة") },
                { k: "orders", label: tr("Orders", "الطلبات"), r: n, num: true },
                { k: "net", label: tr("Net sales", "صافي المبيعات"), r: egp, num: true },
                { k: "last", label: tr("Last order", "آخر طلب"), num: true },
              ]} rows={d.top_customers} />
            </Card>
          </>
        );
      }}
    </Page>
  );
}

export function Returns() {
  const tr = useT();
  return (
    <Page urls={[A + "returns"]}>
      {(d) => {
        const k = d.kpis;
        const slow = d.delivery_governorates.filter((r) => r.shipments >= 200).sort((a, b) => b.delayed_pct - a.delayed_pct).slice(0, 8);
        return (
          <>
            <Kpis items={[
              { label: tr("Return rate", "نسبة المرتجعات"), value: k.return_rate_value_pct, fmt: pct, icon: Undo2, tone: "pink", note: `${pct(k.return_rate_units_pct)} ${tr("by units", "بالوحدات")}` },
              { label: tr("Refunded", "المبالغ المستردة"), value: k.refund_amount, fmt: egp, icon: Wallet, note: `${n(k.returns)} ${tr("returns", "مرتجع")}` },
              { label: tr("Days to return", "الأيام حتى الإرجاع"), value: k.avg_days_to_return, fmt: (v) => n(v, 1), icon: Clock, tone: "blue", note: tr("average", "متوسط") },
              { label: tr("Delivery time", "زمن التوصيل"), value: k.avg_delivery_days, fmt: (v) => `${n(v, 1)} ${tr("days", "يوم")}`, icon: Truck, note: `${n(k.shipments)} ${tr("shipments", "شحنة")}` },
              { label: tr("Delayed shipments", "الشحنات المتأخرة"), value: k.delayed_pct, fmt: pct, icon: Clock, tone: "pink" },
              { label: tr("Shipping fees", "رسوم الشحن"), value: k.shipping_fee_pct_of_ecommerce_sales, fmt: pct, icon: Truck, tone: "blue", note: tr("of e-commerce sales", "من مبيعات التجارة الإلكترونية") },
            ]} />
            <Grid cols={3}>
              <Card span={2} title={tr("Return rate by month", "نسبة المرتجعات شهريًا")} sub={tr("Refunds ÷ net sales of the same month", "المبالغ المستردة ÷ صافي مبيعات نفس الشهر")}>
                <Trend data={d.monthly} fmtL={(v) => pct(v, 1)} series={[{ key: "return_rate_pct", name: tr("Return rate", "نسبة المرتجعات"), type: "area", color: "#E96FC6" }]} />
              </Card>
              <Card title={tr("Reasons", "الأسباب")} sub={tr("Share of refunds", "حصة المبالغ المستردة")}>
                <Donut data={d.reasons} nameKey="reason" valueKey="refund" fmt={egp} />
              </Card>
            </Grid>
            <Grid cols={3}>
              <Card title={tr("Return rate by size", "نسبة الإرجاع حسب المقاس")} sub={tr("Returned ÷ sold units", "الوحدات المرتجعة ÷ المباعة")}><BarList rows={d.by_size.map((r) => ({ label: r.size, value: r.return_rate_pct }))} fmt={(v) => pct(v, 2)} color="#E96FC6" /></Card>
              <Card title={tr("Return rate by category", "نسبة الإرجاع حسب الفئة")}><BarList rows={d.by_category.slice(0, 8).map((r) => ({ label: r.category_en, value: r.return_rate_pct }))} fmt={(v) => pct(v, 2)} /></Card>
              <Card title={tr("Days until return", "الأيام حتى الإرجاع")}><BarList rows={d.days_to_return.map((r) => ({ label: r.bucket, value: r.returns }))} fmt={n} color="#2F6FDE" /></Card>
            </Grid>
            <Grid cols={2}>
              <Card title={tr("Carriers", "شركات الشحن")}>
                <Table cols={[
                  { k: "carrier", label: tr("Carrier", "الشركة") },
                  { k: "shipments", label: tr("Shipments", "الشحنات"), r: n, num: true },
                  { k: "avg_days", label: tr("Avg days", "متوسط الأيام"), r: (v) => n(v, 1), num: true },
                  { k: "delayed_pct", label: tr("Delayed", "متأخر"), r: pct, num: true },
                  { k: "avg_fee", label: tr("Avg fee", "متوسط الرسوم"), r: egp, num: true },
                ]} rows={d.carriers} />
              </Card>
              <Card title={tr("Slowest governorates", "أبطأ المحافظات")} sub={tr("Share of delayed shipments (200+ shipments)", "نسبة الشحنات المتأخرة (200 شحنة فأكثر)")}>
                <BarList rows={slow.map((r) => ({ label: r.ship_to_governorate, value: r.delayed_pct, note: `${n(r.avg_days, 1)} ${tr("days", "يوم")}` }))} fmt={(v) => pct(v)} color="#F5A524" />
              </Card>
            </Grid>
            <Notice>{tr(d.notes.delivery, "الشحنات موجودة لطلبات التجارة الإلكترونية فقط، لذلك تُقارن رسوم الشحن بمبيعات التجارة الإلكترونية.")}</Notice>
          </>
        );
      }}
    </Page>
  );
}

export function Inventory() {
  const tr = useT();
  return (
    <Page urls={[A + "inventory"]}>
      {(d) => {
        const k = d.kpis;
        return (
          <>
            <Kpis items={[
              { label: tr("Units in stock", "الوحدات في المخزون"), value: k.stock_units, icon: Boxes, note: tr(`as of ${d.snapshot_month}`, `حتى ${d.snapshot_month}`) },
              { label: tr("Stock value", "قيمة المخزون"), value: k.stock_value, fmt: egp, icon: Wallet, tone: "blue" },
              { label: tr("Stockout risk", "خطر النفاد"), value: k.avg_stockout_risk, fmt: (v) => n(v, 2), icon: Clock, tone: "pink", note: tr("average score", "متوسط الدرجة") },
              { label: tr("Stock cover", "تغطية المخزون"), value: k.stock_cover_months, fmt: (v) => `${n(v, 1)} ${tr("months", "شهر")}`, icon: Warehouse, note: tr("at last-12-month sales", "بمعدل مبيعات آخر 12 شهرًا") },
              { label: tr("Transfers", "التحويلات"), value: k.transfers, icon: Truck, note: `${compact(k.units_transferred)} ${tr("units", "وحدة")}` },
              { label: tr("Transfer cost", "تكلفة التحويل"), value: k.transfer_cost_per_unit, fmt: (v) => `EGP ${n(v, 2)}`, icon: Wallet, tone: "blue", note: tr("per unit", "للوحدة") },
            ]} />
            {d.warnings.map((w) => w.code === "over_capacity" && <Notice key={w.code} tone="warn">{tr(`${w.warehouses} of ${w.total} warehouses hold more units than their stated capacity.`, `${w.warehouses} من ${w.total} مخازن بها وحدات أكثر من سعتها المعلنة.`)}</Notice>)}
            <Grid cols={3}>
              <Card span={2} title={tr("Stock value over time", "قيمة المخزون عبر الزمن")}>
                <Trend data={d.stock_trend} series={[{ key: "stock_value", name: tr("Stock value", "قيمة المخزون"), type: "area", color: "#6D4AFF" }]} fmtL={compact} />
              </Card>
              <Card title={tr("Stock cover by category", "تغطية المخزون حسب الفئة")} sub={tr("Months of sales in stock", "أشهر المبيعات في المخزون")}>
                <BarList rows={[...d.by_category].sort((a, b) => b.cover_months - a.cover_months).slice(0, 8).map((r) => ({ label: r.product_category, value: r.cover_months, color: r.avg_risk > 0.35 ? "#E96FC6" : "#6D4AFF" }))} fmt={(v) => n(v, 0)} />
              </Card>
            </Grid>
            <Grid cols={2}>
              <Card title={tr("Warehouse utilization", "استغلال المخازن")} sub={tr("Units ÷ capacity", "الوحدات ÷ السعة")}>
                <BarList max={130} rows={d.warehouses.map((r) => ({ label: r.warehouse_label, value: r.utilization_pct, color: r.utilization_pct > 100 ? "#E96FC6" : "#6D4AFF" }))} fmt={(v) => pct(v, 0)} />
              </Card>
              <Card title={tr("Highest stockout risk (branches)", "أعلى خطر نفاد (الفروع)")}>
                <Table max={8} cols={[
                  { k: "branch_name_ar", label: tr("Branch", "الفرع") },
                  { k: "governorate_ar", label: tr("Governorate", "المحافظة") },
                  { k: "units", label: tr("Units", "الوحدات"), r: n, num: true },
                  { k: "avg_risk", label: tr("Risk", "الخطر"), r: (v) => n(v, 2), num: true },
                ]} rows={d.highest_risk_branches} />
              </Card>
            </Grid>
            <Grid cols={3}>
              <Card span={2} title={tr("Transfers by month", "التحويلات شهريًا")}>
                <Trend data={d.transfers_monthly} dual fmtL={(v) => n(v)} fmtR={compact} series={[
                  { key: "units", name: tr("Units", "الوحدات"), type: "bar", color: "#9B83FF", fmt: n },
                  { key: "cost", name: tr("Cost (EGP)", "التكلفة (جنيه)"), type: "line", color: "#E96FC6", axis: "r" },
                ]} />
              </Card>
              <Card title={tr("Factories by focus", "المصانع حسب التخصص")}><BarList rows={d.factories.map((r) => ({ label: r.production_focus, value: r.factories }))} fmt={n} color="#2F6FDE" /></Card>
            </Grid>
            <Card title={tr("Top transfer destinations", "أكثر وجهات التحويل")}>
              <Table max={8} cols={[
                { k: "branch_name_ar", label: tr("Branch", "الفرع") },
                { k: "transfers", label: tr("Transfers", "التحويلات"), r: n, num: true },
                { k: "units", label: tr("Units", "الوحدات"), r: n, num: true },
                { k: "cost", label: tr("Cost", "التكلفة"), r: egp, num: true },
                { k: "cost_per_unit", label: tr("Cost / unit", "التكلفة / وحدة"), r: (v) => `EGP ${n(v, 2)}`, num: true },
              ]} rows={d.top_destinations} />
            </Card>
            <Notice>{tr(d.notes.snapshot, "المخزون يعتمد على آخر شهر مكتمل. التغطية = الوحدات في المخزون ÷ متوسط المبيعات الشهرية لآخر 12 شهرًا مكتملة.")}</Notice>
          </>
        );
      }}
    </Page>
  );
}
