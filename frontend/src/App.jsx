import { useEffect, useMemo, useState } from "react";
import { BarChart3, Boxes, Briefcase, LayoutDashboard, Megaphone, Package, RefreshCw, Store, Truck, Undo2, Users, Bot } from "lucide-react";
import { clearCache, Lang, useApi } from "./ui.jsx";
import { Branches, Overview, Sales } from "./pages/core.jsx";
import { Customers, Inventory, Products, Returns } from "./pages/more.jsx";
import { Marketing, Procurement, Workforce } from "./pages/ops.jsx";
import RAGFloating, { RAGPage } from "./RAGAssistant.jsx";
import "./rag.css";

const NAV = [
  { id: "ai", icon: Bot, Page: RAGPage, en: "AI & RAG Assistant", ar: "مساعد الذكاء الاصطناعي", qen: "Ask all company data with evidence", qar: "اسأل كل بيانات الشركة مع المصادر" },
  { id: "overview", icon: LayoutDashboard, Page: Overview, en: "Executive Overview", ar: "نظرة تنفيذية", qen: "How is the business doing?", qar: "كيف حال النشاط؟" },
  { id: "sales", icon: BarChart3, Page: Sales, en: "Sales Performance", ar: "أداء المبيعات", qen: "Trends, seasonality and channels", qar: "الاتجاهات والموسمية والقنوات" },
  { id: "branches", icon: Store, Page: Branches, en: "Branches & Geography", ar: "الفروع والجغرافيا", qen: "Which branches and regions earn the most?", qar: "أي الفروع والمناطق تحقق أعلى ربح؟" },
  { id: "products", icon: Package, Page: Products, en: "Products & Profitability", ar: "المنتجات والربحية", qen: "What to grow and where discounts hurt", qar: "ما الذي ننميه وأين تضر الخصومات؟" },
  { id: "customers", icon: Users, Page: Customers, en: "Customer Intelligence", ar: "ذكاء العملاء", qen: "Who buys, how often, who is drifting away", qar: "من يشتري وكم مرة ومن يبتعد" },
  { id: "returns", icon: Undo2, Page: Returns, en: "Returns & Delivery", ar: "المرتجعات والتوصيل", qen: "Why items come back and how delivery performs", qar: "لماذا تعود المنتجات وكيف يؤدي التوصيل" },
  { id: "inventory", icon: Boxes, Page: Inventory, en: "Inventory & Transfers", ar: "المخزون والتحويلات", qen: "Stock cover, risk and movement", qar: "تغطية المخزون والخطر والحركة" },
  { id: "procurement", icon: Truck, Page: Procurement, en: "Procurement & Imports", ar: "المشتريات والاستيراد", qen: "Suppliers, lead time and landed cost", qar: "الموردون ومدة التوريد والتكلفة" },
  { id: "marketing", icon: Megaphone, Page: Marketing, en: "Marketing ROI", ar: "عائد التسويق", qen: "What campaigns cost and deliver", qar: "تكلفة الحملات وما تحققه" },
  { id: "workforce", icon: Briefcase, Page: Workforce, en: "Workforce & Costs", ar: "الموارد البشرية والتكاليف", qen: "How much of sales payroll and expenses take", qar: "حصة الرواتب والمصروفات من المبيعات" },
];

const fromHash = () => NAV.find((x) => x.id === window.location.hash.slice(1))?.id || "overview";

export default function App() {
  const [lang, setLang] = useState(() => localStorage.getItem("lang") || "en");
  const [active, setActive] = useState(fromHash);
  const [version, setVersion] = useState(0);
  const health = useApi("/api/health");

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    localStorage.setItem("lang", lang);
  }, [lang]);
  useEffect(() => {
    const on = () => { setActive(fromHash()); window.scrollTo({ top: 0 }); };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  const ctx = useMemo(() => ({ lang, tr: (en, ar) => (lang === "ar" ? ar : en) }), [lang]);
  const cur = NAV.find((x) => x.id === active);
  const L = (x) => x[lang === "ar" ? "ar" : "en"];
  const online = health.data && !health.error;

  return (
    <Lang.Provider value={ctx}>
      <div className="app">
        <aside className="glass sidebar">
          <div className="brand">
            <img className="logo-full" src="/cottonil-logo.png" alt="Cottonil" />
            <span className="logo-mark" aria-hidden="true">C</span>
          </div>
          <nav aria-label={ctx.tr("Pages", "الصفحات")}>
            {NAV.map((x) => (
              <a key={x.id} href={`#${x.id}`} className={`nav-item ${x.id === active ? "active" : ""}`} aria-current={x.id === active ? "page" : undefined} title={L(x)}>
                <x.icon size={19} /><span>{L(x)}</span>
              </a>
            ))}
          </nav>
          <div className="side-foot"><i className={`dot ${online ? "on" : ""}`} /><span>{online ? ctx.tr("API connected", "الخادم متصل") : ctx.tr("API offline", "الخادم غير متصل")}</span></div>
        </aside>
        <main>
          <header className="topbar">
            <div><h1>{L(cur)}</h1><p>{lang === "ar" ? cur.qar : cur.qen}</p></div>
            <div className="tools">
              <div className="seg" role="group" aria-label="Language">
                <button className={lang === "en" ? "on" : ""} onClick={() => setLang("en")}>EN</button>
                <button className={lang === "ar" ? "on" : ""} onClick={() => setLang("ar")}>عربي</button>
              </div>
              <button className="btn" onClick={() => { clearCache(); setVersion((v) => v + 1); }} title={ctx.tr("Reload data", "إعادة تحميل البيانات")}><RefreshCw size={16} /><span>{ctx.tr("Refresh", "تحديث")}</span></button>
            </div>
          </header>
          <cur.Page key={`${active}-${version}`} />
          <RAGFloating />
        </main>
      </div>
    </Lang.Provider>
  );
}
