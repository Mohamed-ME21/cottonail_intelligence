import { Activity, Banknote, CalendarDays, Percent, ShoppingBag, Store, TrendingUp, Undo2, Users, Wallet, Building2 } from "lucide-react";
import { BarList, Card, compact, Donut, Dots, egp, Grid, Heat, Kpis, n, Notice, Page, pct, Table, Trend, useT } from "../ui.jsx";

const OV = "/api/analytics/executive-overview", SP = "/api/analytics/sales-performance", BR = "/api/analytics/branches";

export function Overview() {
  const tr = useT();
  return (
    <Page urls={[OV, SP]}>
      {(o, s) => {
        const k = o.kpis;
        const p = s.period;
        return (
          <>
            <Kpis items={[
              { label: tr("Net sales", "صافي المبيعات"), value: k.net_sales, fmt: egp, icon: Wallet, delta: k.sales_yoy_pct, note: tr("vs same period last year", "مقارنة بنفس الفترة العام الماضي") },
              { label: tr("Gross margin", "هامش الربح الإجمالي"), value: k.margin_pct, fmt: pct, icon: Percent, tone: "blue", note: egp(k.gross_margin) },
              { label: tr("Orders", "الطلبات"), value: k.orders, icon: ShoppingBag, note: `${n(k.units_sold)} ${tr("units", "وحدة")}` },
              { label: tr("Average order", "متوسط الطلب"), value: k.aov, fmt: egp, icon: Activity, tone: "pink", note: tr("net, before tax", "صافي قبل الضريبة") },
              { label: tr("Customers with purchases", "عملاء لديهم مشتريات"), value: k.active_customers, icon: Users, note: tr("distinct customer IDs", "معرفات عملاء مميزة") },
              { label: tr("Return rate", "نسبة المرتجعات"), value: k.return_rate_value_pct, fmt: pct, icon: Undo2, tone: "pink", note: `${pct(k.return_rate_units_pct)} ${tr("by units", "بالوحدات")}` },
            ]} />
            {p?.partial_month && <Notice>{tr(`Data runs through ${p.data_through}, so ${p.partial_month} is a partial month.`, `البيانات حتى ${p.data_through}، لذلك شهر ${p.partial_month} غير مكتمل.`)}</Notice>}
            <Grid cols={3}>
              <Card span={2} title={tr("Monthly net sales and margin", "صافي المبيعات الشهرية والهامش")} sub={tr("EGP · margin on the right axis", "جنيه · الهامش على المحور الأيمن")}>
                <Trend data={o.monthly_sales_margin} dual fmtR={(v) => pct(v, 0)} series={[
                  { key: "net_sales", name: tr("Net sales", "صافي المبيعات"), type: "area", color: "#6D4AFF" },
                  { key: "margin_pct", name: tr("Margin %", "الهامش %"), type: "line", color: "#E96FC6", axis: "r", fmt: (v) => pct(v) },
                ]} />
              </Card>
              <Card title={tr("Sales by channel", "المبيعات حسب القناة")}>
                <Donut data={o.sales_by_channel} nameKey="sales_channel" valueKey="net_sales" fmt={egp} />
              </Card>
            </Grid>
            <Grid cols={2}>
              <Card title={tr("Top governorates", "أعلى المحافظات")} sub={tr("Net sales and margin", "صافي المبيعات والهامش")}>
                <BarList rows={o.sales_by_governorate.slice(0, 8).map((r) => ({ label: r.governorate_ar, value: r.net_sales, note: pct(r.margin_pct) }))} fmt={egp} />
              </Card>
              <Card title={tr("Categories", "الفئات")} sub={tr("Net sales and margin", "صافي المبيعات والهامش")}>
                <BarList rows={o.sales_by_category.slice(0, 8).map((r) => ({ label: r.category, value: r.net_sales, note: pct(r.margin_pct) }))} fmt={egp} color="#2F6FDE" />
              </Card>
            </Grid>
            {o.insights?.length > 0 && (
              <Card title={tr("What stands out", "أهم الملاحظات")}>
                <ul className="insights">{o.insights.map((x, i) => <li key={i} dir="auto">{typeof x === "string" ? x : x.message}</li>)}</ul>
              </Card>
            )}
          </>
        );
      }}
    </Page>
  );
}

const DAYS = ["Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];
export function Sales() {
  const tr = useT();
  return (
    <Page urls={[SP]}>
      {(s) => {
        const p = s.period;
        const trend = s.monthly_trend.map((r) => ({ ...r, net_sales_ly: r.net_sales_ly ?? null }));
        return (
          <>
            <Kpis items={[
              { label: tr(`Net sales ${p.data_through.slice(0, 4)} YTD`, `صافي المبيعات منذ بداية ${p.data_through.slice(0, 4)}`), value: p.net_sales_ytd, fmt: egp, icon: Wallet, note: tr(`to ${p.data_through}`, `حتى ${p.data_through}`) },
              { label: tr("Last complete month", "آخر شهر مكتمل"), value: p.latest_month_sales, fmt: egp, icon: CalendarDays, tone: "blue", note: p.latest_month },
              { label: tr("Month over month", "مقارنة بالشهر السابق"), value: p.sales_mom_pct, fmt: (v) => pct(v), icon: TrendingUp, tone: "pink", note: tr("complete months only", "الأشهر المكتملة فقط") },
              { label: tr("Previous month", "الشهر السابق"), value: p.previous_month_sales, fmt: egp, icon: Banknote, note: tr("for comparison", "للمقارنة") },
            ]} />
            {p.partial_month && <Notice>{tr(`${p.partial_month} is partial (data to ${p.data_through}), so it is excluded from month-over-month.`, `شهر ${p.partial_month} غير مكتمل (حتى ${p.data_through}) فاستُبعد من المقارنة الشهرية.`)}</Notice>}
            <Card title={tr("Monthly net sales vs last year", "صافي المبيعات الشهرية مقابل العام الماضي")}>
              <Trend data={trend} height={300} series={[
                { key: "net_sales", name: tr("Net sales", "صافي المبيعات"), type: "bar", color: "#6D4AFF" },
                { key: "net_sales_ly", name: tr("Same month last year", "نفس الشهر العام الماضي"), type: "line", color: "#E96FC6" },
              ]} />
            </Card>
            <Grid cols={2}>
              <Card title={tr("Month by weekday", "الشهر واليوم")} sub={tr("Net sales, darker = higher", "صافي المبيعات، الأغمق أعلى")}>
                <Heat rows={s.weekday_heatmap} rowKey="weekday" colKey="month_name" valKey="net_sales" rowOrder={DAYS} colOrder={[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]} fmt={(v) => compact(v, 0)} />
              </Card>
              <Card title={tr("Channels and payment", "القنوات والدفع")}>
                <BarList rows={s.sales_by_channel.map((r) => ({ label: r.sales_channel, value: r.net_sales }))} fmt={egp} />
                <hr className="sep" />
                <BarList rows={s.sales_by_payment_method.map((r) => ({ label: r.payment_method, value: r.net_sales }))} fmt={egp} color="#2F6FDE" />
              </Card>
            </Grid>
            <Card title={tr("Top products", "أعلى المنتجات")}>
              <Table cols={[
                { k: "product_name_ar", label: tr("Product", "المنتج") },
                { k: "net_sales", label: tr("Net sales", "صافي المبيعات"), r: egp, num: true },
                { k: "units_sold", label: tr("Units", "الوحدات"), r: n, num: true },
                { k: "margin_pct", label: tr("Margin", "الهامش"), r: pct, num: true },
              ]} rows={s.top_products} />
            </Card>
          </>
        );
      }}
    </Page>
  );
}

export function Branches() {
  const tr = useT();
  return (
    <Page urls={[BR]}>
      {(b) => {
        const s = b.summary;
        return (
          <>
            <Kpis items={[
              { label: tr("Branches", "الفروع"), value: s.branch_count, icon: Store, note: tr("in the branch table", "في جدول الفروع") },
              { label: tr("Net sales", "صافي المبيعات"), value: s.total_net_sales, fmt: egp, icon: Wallet, tone: "blue" },
              { label: tr("Branch operating expenses", "مصروفات الفروع"), value: s.total_branch_opex, fmt: egp, icon: Building2, tone: "pink" },
              { label: tr("Branch payroll", "رواتب الفروع"), value: s.total_branch_payroll, fmt: egp, icon: Users, note: tr("current branch assignment", "حسب فرع الموظف الحالي") },
            ]} />
            <Grid cols={2}>
              <Card title={tr("Sales vs margin by branch", "المبيعات مقابل الهامش لكل فرع")} sub={tr("Each dot is a branch; size = operating profit proxy", "كل نقطة فرع؛ الحجم = الربح التشغيلي التقريبي")}>
                <Dots data={b.branches} xKey="net_sales" yKey="margin_pct" zKey="operating_profit_proxy" nameKey="branch_name_ar" xLabel={tr("Net sales", "صافي المبيعات")} yLabel={tr("Margin", "الهامش")} xFmt={compact} />
              </Card>
              <Card title={tr("Governorates", "المحافظات")} sub={tr("Net sales and operating profit proxy", "صافي المبيعات والربح التشغيلي التقريبي")}>
                <BarList rows={b.governorate_performance.slice(0, 9).map((r) => ({ label: r.governorate_ar, value: r.net_sales, note: egp(r.operating_profit_proxy) }))} fmt={egp} />
              </Card>
            </Grid>
            <Card title={tr("Store formats", "أنواع الفروع")}>
              <Table cols={[
                { k: "retail_location_type", label: tr("Format", "النوع") },
                { k: "branch_count", label: tr("Branches", "الفروع"), r: n, num: true },
                { k: "net_sales", label: tr("Net sales", "صافي المبيعات"), r: egp, num: true },
                { k: "margin_pct", label: tr("Margin", "الهامش"), r: pct, num: true },
                { k: "operating_profit_proxy", label: tr("Operating profit proxy", "الربح التشغيلي التقريبي"), r: egp, num: true },
              ]} rows={b.retail_location_performance} />
            </Card>
            <Card title={tr("Branch ranking", "ترتيب الفروع")}>
              <Table max={12} cols={[
                { k: "sales_rank", label: "#", num: true },
                { k: "branch_name_ar", label: tr("Branch", "الفرع") },
                { k: "governorate_ar", label: tr("Governorate", "المحافظة") },
                { k: "net_sales", label: tr("Net sales", "صافي المبيعات"), r: egp, num: true },
                { k: "margin_pct", label: tr("Margin", "الهامش"), r: pct, num: true },
                { k: "employee_count", label: tr("Staff", "الموظفون"), r: n, num: true },
                { k: "sales_per_employee", label: tr("Sales / employee", "مبيعات / موظف"), r: egp, num: true },
                { k: "operating_profit_proxy", label: tr("Profit proxy", "الربح التقريبي"), r: egp, num: true },
              ]} rows={b.branches} />
            </Card>
            <Notice>{tr(`Operating profit is a proxy: gross margin − branch expenses − assigned payroll. Warehouse expenses (${egp(s.department_expenses_not_allocated)}) are not allocated to branches.`, `الربح التشغيلي تقريبي: الهامش الإجمالي − مصروفات الفرع − الرواتب المسندة. مصروفات المخازن (${egp(s.department_expenses_not_allocated)}) غير موزعة على الفروع.`)}</Notice>
          </>
        );
      }}
    </Page>
  );
}
