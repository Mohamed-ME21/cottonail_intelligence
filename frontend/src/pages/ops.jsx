import { Banknote, Clock, Container, Megaphone, MousePointerClick, Package, Percent, ShoppingBag, Truck, Users, Wallet } from "lucide-react";
import { BarList, Card, compact, Donut, Dots, egp, Grid, Kpis, n, Notice, Page, pct, Table, Trend, usd, useT } from "../ui.jsx";

const A = "/api/analytics/";

export function Procurement() {
  const tr = useT();
  return (
    <Page urls={[A + "procurement"]}>
      {(d) => {
        const k = d.kpis;
        return (
          <>
            <Kpis items={[
              { label: tr("Purchase orders", "أوامر الشراء"), value: k.po_count, icon: ShoppingBag, note: `${k.suppliers} ${tr("suppliers", "مورد")}` },
              { label: tr("Purchase cost", "تكلفة المشتريات"), value: k.purchase_cost_egp, fmt: egp, icon: Wallet, tone: "blue" },
              { label: tr("Lead time", "مدة التوريد"), value: k.avg_lead_days, fmt: (v) => `${n(v, 1)} ${tr("days", "يوم")}`, icon: Clock, note: tr("order to delivery", "من الطلب إلى التسليم") },
              { label: tr("Partial receipts", "استلام جزئي"), value: k.partial_receipt_pct, fmt: pct, icon: Package, tone: "pink", note: tr("of purchase orders", "من أوامر الشراء") },
              { label: tr("Import landed cost", "تكلفة الاستيراد الواصلة"), value: k.import_landed_usd, fmt: usd, icon: Container, tone: "blue", note: `${n(k.import_shipments)} ${tr("shipments", "شحنة")}` },
              { label: tr("Freight + duty", "الشحن + الجمارك"), value: k.freight_duty_pct, fmt: pct, icon: Percent, tone: "pink", note: tr("of customs value", "من القيمة الجمركية") },
            ]} />
            {d.warnings.map((w) => w.code === "purchase_volume" && (
              <Notice key={w.code} tone="warn">{tr(`Purchase orders total ${compact(w.purchased_units)} units, about ${n(w.ratio, 0)}× the ${compact(w.sold_units)} units sold. Check the purchase data before using its cost totals.`, `أوامر الشراء تبلغ ${compact(w.purchased_units)} وحدة، أي نحو ${n(w.ratio, 0)} ضعف الوحدات المباعة (${compact(w.sold_units)}). راجع بيانات المشتريات قبل الاعتماد على إجمالي التكلفة.`)}</Notice>
            ))}
            <Grid cols={3}>
              <Card span={2} title={tr("Purchase cost by month", "تكلفة المشتريات شهريًا")} sub="EGP">
                <Trend data={d.monthly_cost} series={[{ key: "cost", name: tr("Cost", "التكلفة"), type: "area", color: "#6D4AFF" }]} />
              </Card>
              <Card title={tr("Purchase order status", "حالة أوامر الشراء")}><Donut data={d.po_status} nameKey="po_status" valueKey="orders" fmt={n} /></Card>
            </Grid>
            <Grid cols={2}>
              <Card title={tr("Top suppliers", "أكبر الموردين")} sub={tr(`Top 5 hold ${pct(k.top5_supplier_share_pct)} of cost`, `أكبر 5 يمثلون ${pct(k.top5_supplier_share_pct)} من التكلفة`)}>
                <Table max={8} cols={[
                  { k: "supplier_name_ar", label: tr("Supplier", "المورد") },
                  { k: "material_type", label: tr("Material", "الخامة") },
                  { k: "cost", label: tr("Cost", "التكلفة"), r: egp, num: true },
                  { k: "avg_lead_days", label: tr("Lead days", "أيام التوريد"), r: (v) => n(v, 1), num: true },
                  { k: "partial_receipt_pct", label: tr("Partial", "جزئي"), r: pct, num: true },
                ]} rows={d.suppliers} />
              </Card>
              <Card title={tr("Cost by material type", "التكلفة حسب نوع الخامة")}>
                <BarList rows={d.material_types.map((r) => ({ label: r.material_type, value: r.cost }))} fmt={egp} />
              </Card>
            </Grid>
            <Grid cols={3}>
              <Card span={2} title={tr("Imports by country", "الاستيراد حسب الدولة")} sub={tr("USD, landed = value + freight + duty", "دولار، الواصل = القيمة + الشحن + الجمارك")}>
                <Table max={8} cols={[
                  { k: "country", label: tr("Country", "الدولة") },
                  { k: "shipments", label: tr("Shipments", "الشحنات"), r: n, num: true },
                  { k: "customs_value", label: tr("Value", "القيمة"), r: usd, num: true },
                  { k: "landed", label: tr("Landed", "الواصل"), r: usd, num: true },
                  { k: "freight_duty_pct", label: tr("Freight+duty", "شحن+جمارك"), r: pct, num: true },
                ]} rows={d.imports_by_country} />
              </Card>
              <Card title={tr("Imports by goods class", "الاستيراد حسب نوع البضاعة")}><BarList rows={d.imports_by_commodity.map((r) => ({ label: r.commodity_class, value: r.landed }))} fmt={usd} color="#2F6FDE" /></Card>
            </Grid>
            <Notice>{tr(d.notes.currency, "أوامر الشراء بالجنيه والاستيراد بالدولار، ولا يُجمعان معًا.")}</Notice>
          </>
        );
      }}
    </Page>
  );
}

export function Marketing() {
  const tr = useT();
  return (
    <Page urls={[A + "marketing"]}>
      {(d) => {
        const k = d.kpis;
        return (
          <>
            <Kpis items={[
              { label: tr("Spend", "الإنفاق"), value: k.spend, fmt: egp, icon: Wallet, note: `${pct(k.budget_utilization_pct)} ${tr("of budget", "من الميزانية")}` },
              { label: tr("Spend vs sales", "الإنفاق مقابل المبيعات"), value: k.spend_pct_of_sales, fmt: pct, icon: Percent, tone: "pink", note: tr("of all-time net sales", "من صافي المبيعات الكلي") },
              { label: tr("Impressions", "مرات الظهور"), value: k.impressions, icon: Megaphone, tone: "blue" },
              { label: tr("Click-through rate", "نسبة النقر"), value: k.ctr_pct, fmt: pct, icon: MousePointerClick, note: `${n(k.clicks / 1e6, 1)}M ${tr("clicks", "نقرة")}` },
              { label: tr("Cost per click", "تكلفة النقرة"), value: k.cpc, fmt: (v) => `EGP ${n(v, 2)}`, icon: Banknote, tone: "blue" },
              { label: tr("Campaigns", "الحملات"), value: k.campaigns, icon: Megaphone, tone: "pink" },
            ]} />
            {d.warnings.map((w) => w.code === "attributed_orders" && (
              <Notice key={w.code} tone="warn">{tr(`Campaigns report ${compact(w.attributed)} attributed orders, ${n(w.ratio, 0)}× all ${n(w.total_orders)} orders in the sales data. Cost per order is therefore not shown; use clicks and spend until the source is checked.`, `الحملات تسجل ${compact(w.attributed)} طلبًا منسوبًا، أي ${n(w.ratio, 0)} ضعف كل الطلبات (${n(w.total_orders)}) في بيانات المبيعات. لذلك لا نعرض تكلفة الطلب؛ استخدم النقرات والإنفاق حتى تُراجع المصدر.`)}</Notice>
            ))}
            <Grid cols={3}>
              <Card span={2} title={tr("Spend and clicks by month", "الإنفاق والنقرات شهريًا")}>
                <Trend data={d.monthly} dual fmtR={compact} series={[
                  { key: "spend", name: tr("Spend (EGP)", "الإنفاق (جنيه)"), type: "bar", color: "#9B83FF" },
                  { key: "clicks", name: tr("Clicks", "النقرات"), type: "line", color: "#E96FC6", axis: "r" },
                ]} />
              </Card>
              <Card title={tr("Campaign funnel", "قمع الحملات")} sub={tr("Impressions → clicks", "الظهور ← النقرات")}>
                <BarList rows={d.funnel.slice(0, 2).map((r, i) => ({ label: r.stage === "Impressions" ? tr("Impressions", "مرات الظهور") : tr("Clicks", "النقرات"), value: r.value, color: i ? "#E96FC6" : "#6D4AFF" }))} fmt={compact} />
                <p className="muted">{tr("Click-through rate", "نسبة النقر")}: <b>{pct(k.ctr_pct, 2)}</b></p>
              </Card>
            </Grid>
            <Grid cols={2}>
              <Card title={tr("Channels", "القنوات")}>
                <Table cols={[
                  { k: "channel", label: tr("Channel", "القناة") },
                  { k: "spend", label: tr("Spend", "الإنفاق"), r: egp, num: true },
                  { k: "ctr_pct", label: "CTR", r: (v) => pct(v, 2), num: true },
                  { k: "cpc", label: "CPC", r: (v) => `EGP ${n(v, 2)}`, num: true },
                ]} rows={d.channels} />
              </Card>
              <Card title={tr("Target audiences", "الجمهور المستهدف")}>
                <BarList rows={d.audiences.map((r) => ({ label: r.target_audience, value: r.spend, note: `CTR ${pct(r.ctr_pct, 1)}` }))} fmt={egp} color="#2F6FDE" />
              </Card>
            </Grid>
            <Grid cols={2}>
              <Card title={tr("Spend vs sales by governorate", "الإنفاق مقابل المبيعات حسب المحافظة")} sub={tr("Correlation over all years, not campaign-driven revenue", "ارتباط عبر كل السنوات، وليس إيرادًا ناتجًا عن الحملات")}>
                <Dots data={d.governorates} xKey="spend" yKey="net_sales" nameKey="governorate_ar" xLabel={tr("Spend", "الإنفاق")} yLabel={tr("Net sales", "صافي المبيعات")} xFmt={compact} yFmt={compact} />
              </Card>
              <Card title={tr("Largest campaigns", "أكبر الحملات")}>
                <Table max={8} cols={[
                  { k: "campaign_id", label: "ID" },
                  { k: "channel", label: tr("Channel", "القناة") },
                  { k: "governorate_ar", label: tr("Governorate", "المحافظة") },
                  { k: "spend_EGP", label: tr("Spend", "الإنفاق"), r: egp, num: true },
                  { k: "utilization_pct", label: tr("Budget used", "الميزانية المستخدمة"), r: (v) => pct(v, 0), num: true },
                ]} rows={d.top_campaigns} />
              </Card>
            </Grid>
            <Notice>{tr(d.notes.attribution, "لا يوجد ربط بين الحملة والطلب. الارتباط بالمحافظة لا يعني أن الحملة سبب المبيعات.")}</Notice>
          </>
        );
      }}
    </Page>
  );
}

export function Workforce() {
  const tr = useT();
  return (
    <Page urls={[A + "workforce"]}>
      {(d) => {
        const k = d.kpis;
        const monthly = d.monthly.filter((r) => r.payroll > 0 || r.opex > 0);
        return (
          <>
            <Kpis items={[
              { label: tr("Employees", "الموظفون"), value: k.employees, icon: Users, note: `${tr("avg base", "متوسط الأساسي")} ${egp(k.avg_salary)}` },
              { label: tr("Payroll cost", "تكلفة الرواتب"), value: k.payroll_cost, fmt: egp, icon: Wallet, tone: "blue", note: `${pct(k.payroll_pct_of_sales)} ${tr("of sales", "من المبيعات")}` },
              { label: tr("Overtime", "الإضافي"), value: k.overtime_pct_of_base, fmt: pct, icon: Clock, tone: "pink", note: tr("of base pay", "من الأساسي") },
              { label: tr("Bonuses", "المكافآت"), value: k.bonus_pct_of_base, fmt: pct, icon: Banknote, note: tr("of base pay", "من الأساسي") },
              { label: tr("Operating expenses", "المصروفات التشغيلية"), value: k.opex, fmt: egp, icon: Truck, tone: "blue", note: `${pct(k.opex_pct_of_sales)} ${tr("of sales", "من المبيعات")}` },
              { label: tr("Operating result proxy", "النتيجة التشغيلية التقريبية"), value: k.operating_result_proxy, fmt: egp, icon: Percent, tone: "pink", note: tr("margin − payroll − expenses", "الهامش − الرواتب − المصروفات") },
            ]} />
            <Card title={tr("Payroll, expenses and margin", "الرواتب والمصروفات والهامش")} sub={tr("Monthly, EGP", "شهريًا، جنيه")}>
              <Trend data={monthly} height={280} series={[
                { key: "gross_margin", name: tr("Gross margin", "الهامش الإجمالي"), type: "area", color: "#6D4AFF" },
                { key: "opex", name: tr("Operating expenses", "المصروفات التشغيلية"), type: "line", color: "#E96FC6" },
                { key: "payroll", name: tr("Payroll", "الرواتب"), type: "line", color: "#2F6FDE" },
              ]} />
            </Card>
            <Grid cols={3}>
              <Card title={tr("Expenses by category", "المصروفات حسب الفئة")}><BarList rows={d.opex_by_category.slice(0, 8).map((r) => ({ label: r.expense_category, value: r.amount }))} fmt={egp} /></Card>
              <Card title={tr("Branches vs warehouses", "الفروع مقابل المخازن")}><Donut data={d.opex_by_scope} nameKey="scope" valueKey="amount" fmt={egp} /></Card>
              <Card title={tr("Payment methods", "طرق الدفع")}><Donut data={d.payment_methods} nameKey="payment_method" valueKey="amount" fmt={egp} /></Card>
            </Grid>
            <Grid cols={2}>
              <Card title={tr("Top vendors", "أكبر الموردين")}><BarList rows={d.top_vendors.map((r) => ({ label: r.vendor_name, value: r.amount }))} fmt={egp} color="#2F6FDE" /></Card>
              <Card title={tr("Positions", "الوظائف")}>
                <Table max={8} cols={[
                  { k: "position_en", label: tr("Position", "الوظيفة") },
                  { k: "headcount", label: tr("Headcount", "العدد"), r: n, num: true },
                  { k: "avg_salary", label: tr("Avg base salary", "متوسط الأساسي"), r: egp, num: true },
                ]} rows={d.positions} />
              </Card>
            </Grid>
            <Notice>{tr(d.notes.proxy, "النتيجة التشغيلية تقريبية: الهامش الإجمالي − تكلفة الرواتب − المصروفات التشغيلية، ولا تشمل المشتريات والتسويق والاستيراد.")}</Notice>
          </>
        );
      }}
    </Page>
  );
}
