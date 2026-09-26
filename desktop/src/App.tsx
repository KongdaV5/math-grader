import { useEffect, useState } from "react";
import { GradingPage } from "./GradingPage";
import { api } from "./api";
import { AnalyticsPage, AssignmentsPage, DashboardPage, ModelCenterPage, ReviewPage,
  SettingsPage, StudentsPage, TemplatesPage } from "./ProductPages";

const pages = [
  {id: "home", title: "首页", description: "本地数据与工作状态", marker: "⌂"},
  {id: "grading", title: "开始批改", description: "采集、提交与后台队列", marker: "▣"},
  {id: "assignments", title: "作业", description: "班级作业与提交", marker: "▤"},
  {id: "students", title: "学生", description: "学生名册", marker: "◉"},
  {id: "review", title: "人工复核", description: "后续启用", marker: "✓"},
  {id: "templates", title: "模板", description: "教材与参考页", marker: "▧"},
  {id: "analytics", title: "学习分析", description: "真实数据概览", marker: "▥"},
  {id: "models", title: "模型中心", description: "候选模型与安装", marker: "◫"},
  {id: "settings", title: "设置", description: "本地目录与运行环境", marker: "⚙"},
] as const;
type PageId = typeof pages[number]["id"];

function currentPage(): PageId {
  const id = window.location.hash.replace(/^#\//, "");
  return pages.find((page) => page.id === id)?.id ?? "home";
}

function App() {
  const [page, setPage] = useState<PageId>(currentPage);
  const [online, setOnline] = useState(false);
  useEffect(() => {
    const onHash = () => setPage(currentPage());
    window.addEventListener("hashchange", onHash);
    const poll = () => { void api.health().then((response) => setOnline(response.status === "ok")).catch(() => setOnline(false)); };
    poll();
    const timer = setInterval(poll, 3000);
    return () => {window.removeEventListener("hashchange", onHash); clearInterval(timer);};
  }, []);
  const selected = pages.find((item) => item.id === page)!;
  const body = {
    home: <DashboardPage />, grading: <GradingPage />, assignments: <AssignmentsPage />,
    students: <StudentsPage />, review: <ReviewPage />, templates: <TemplatesPage />,
    analytics: <AnalyticsPage />, models: <ModelCenterPage />, settings: <SettingsPage />,
  }[page];
  return <div className="app-frame">
    <aside className="app-sidebar"><a className="app-brand" href="#/home"><span className="app-brand-icon">数</span><span><strong>Math Grader</strong><small>本地作业批改</small></span></a>
      <nav aria-label="主导航">{pages.map((item) => <a key={item.id} href={`#/${item.id}`} className={page === item.id ? "active" : ""} aria-current={page === item.id ? "page" : undefined}>
        <span className="nav-marker" aria-hidden="true">{item.marker}</span>{item.title}</a>)}</nav>
      <div className="sidebar-foot"><span className={`service-dot ${online ? "online-dot" : ""}`} />{online ? "本地服务已连接" : "本地服务未连接"}<small>P3-X1 · 本地运行</small></div>
    </aside>
    <div className="app-main"><header className="page-header"><div><p className="eyebrow">MATH GRADER / {selected.id.toUpperCase()}</p><h1>{selected.title}</h1><p>{selected.description}</p></div>
      <span className={`service-pill ${online ? "online" : "offline"}`}><span className="service-dot" />{online ? "本地服务正常" : "服务未连接"}</span></header>
      <main className="app-content" id="main-content">{body}</main>
    </div>
  </div>;
}

export default App;
