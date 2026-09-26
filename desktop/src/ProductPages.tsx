import { TemplateEditor } from "./TemplateEditor";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, fileAsBase64, type Assignment, type ClassRecord, type ModelStatus, type Overview,
  imageUrl, type PageTemplate, type ProviderHealth, type ReviewQueueItem, type Student, type Submission, type SystemInfo, type TemplateGroup } from "./api";

function Message({ text, error = false }: { text: string; error?: boolean }) {
  return <div className={`product-message ${error ? "is-error" : ""}`} role={error ? "alert" : "status"}>{text}</div>;
}

function useClasses() {
  const [classes, setClasses] = useState<ClassRecord[]>([]);
  const [classId, setClassId] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    void api.classes().then((rows) => { setClasses(rows); setClassId(rows[0]?.id ?? ""); }).catch((e: Error) => setError(e.message));
  }, []);
  return { classes, classId, setClassId, error };
}

export function DashboardPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [capture, setCapture] = useState("读取中");
  const [error, setError] = useState("");
  const load = useCallback(() => {
    void Promise.all([api.overview(), api.captureSession()]).then(([data, session]) => {
      setOverview(data); setCapture(session.status === "ACTIVE" ? "拍摄进行中" : "未开启拍摄"); setError("");
    }).catch((e: Error) => setError(e.message));
  }, []);
  useEffect(() => { load(); const timer = setInterval(load, 4000); return () => clearInterval(timer); }, [load]);
  if (error) return <Message text={error} error />;
  if (!overview) return <Message text="正在读取本地概览…" />;
  return <div className="page-stack">
    <div className="metric-grid">
      {[ ["班级", overview.counts.classes], ["学生", overview.counts.students],
         ["排队中", overview.counts.queued], ["处理中", overview.counts.processing] ].map(([label, value]) =>
        <article className="metric-card" key={label}><span>{label}</span><strong>{value}</strong></article>)}
    </div>
    <div className="product-grid-two">
      <section className="product-card"><div className="product-card-heading"><h2>最近作业</h2><a href="#/assignments">查看作业</a></div>
        {overview.recent_assignments.length ? <ul className="simple-list">{overview.recent_assignments.map((item) =>
          <li key={item.id}><strong>{item.name}</strong><span>{item.date} · {item.status}</span></li>)}</ul> : <p className="empty-copy">还没有作业。先在“开始批改”创建班级和作业。</p>}</section>
      <section className="product-card"><div className="product-card-heading"><h2>最近提交</h2><a href="#/grading">开始批改</a></div>
        {overview.recent_submissions.length ? <ul className="simple-list">{overview.recent_submissions.map((item) =>
          <li key={item.id}><strong>{item.id.slice(0, 8)}</strong><span>{item.page_count} 页 · {item.status}</span></li>)}</ul> : <p className="empty-copy">暂无学生作业提交。</p>}</section>
    </div>
    <section className="product-card capture-shortcut"><div><h2>手机拍摄</h2><p>{capture}</p></div><a className="button secondary" href="#/grading">前往拍摄</a></section>
  </div>;
}

export function AssignmentsPage() {
  const { classes, classId, setClassId, error: classError } = useClasses();
  const [rows, setRows] = useState<Assignment[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [name, setName] = useState("");
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    if (!classId) { setRows([]); return; }
    const assignments = await api.assignments(classId);
    setRows(assignments);
    const entries = await Promise.all(assignments.map(async (item) => [item.id, (await api.submissions(item.id)).length] as const));
    setCounts(Object.fromEntries(entries));
  }, [classId]);
  useEffect(() => { void load().catch((e: Error) => setError(e.message)); }, [load]);
  return <div className="page-stack"><section className="product-card"><div className="product-card-heading"><h2>作业管理</h2></div>
    {classError && <Message text={classError} error />}{error && <Message text={error} error />}
    <label className="field-label" htmlFor="assignment-class">班级</label>
    <select id="assignment-class" value={classId} onChange={(e) => setClassId(e.target.value)}><option value="">选择班级</option>{classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
    <form className="product-form" onSubmit={(e) => { e.preventDefault(); setBusy(true); void api.createTeacherAssignment(classId, name, date).then(() => {setName(""); return load();}).catch((cause: Error) => setError(cause.message)).finally(() => setBusy(false)); }}>
      <input aria-label="新作业名称" placeholder="作业名称" value={name} onChange={(e) => setName(e.target.value)} required />
      <input aria-label="作业日期" type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
      <button className="button primary" disabled={!classId || busy}>创建批改作业</button>
    </form></section>
    <section className="product-card"><h2>作业列表</h2>{rows.length ? <ul className="simple-list">{rows.map((item) =>
      <li key={item.id}><div><strong>{item.name}</strong><small>{item.date}</small></div><span>{item.status} · {counts[item.id] ?? "…"} 份提交</span></li>)}</ul> : <p className="empty-copy">当前班级暂无作业。</p>}</section></div>;
}

export function StudentsPage() {
  const { classes, classId, setClassId, error: classError } = useClasses();
  const [rows, setRows] = useState<Student[]>([]);
  const [studentNo, setStudentNo] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<Submission[]>([]);
  const [historyStudent, setHistoryStudent] = useState("");
  const load = useCallback(async () => {
    if (!classId) {setRows([]); setHistory([]); return;}
    const [students, assignments] = await Promise.all([api.students(classId), api.assignments(classId)]);
    setRows(students);
    setHistory((await Promise.all(assignments.map((item) => api.submissions(item.id)))).flat());
  }, [classId]);
  useEffect(() => { void load().catch((e: Error) => setError(e.message)); }, [load]);
  return <div className="page-stack"><section className="product-card"><h2>学生名册</h2>
    {classError && <Message text={classError} error />}{error && <Message text={error} error />}
    <label className="field-label" htmlFor="student-class">班级</label>
    <select id="student-class" value={classId} onChange={(e) => setClassId(e.target.value)}><option value="">选择班级</option>{classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
    <form className="product-form" onSubmit={(e) => {e.preventDefault(); setBusy(true); void api.createStudent(classId, studentNo, name).then(() => {setStudentNo(""); setName(""); return load();}).catch((cause: Error) => setError(cause.message)).finally(() => setBusy(false));}}>
      <input aria-label="学号" placeholder="学号" value={studentNo} onChange={(e) => setStudentNo(e.target.value)} required />
      <input aria-label="姓名" placeholder="姓名" value={name} onChange={(e) => setName(e.target.value)} required />
      <button className="button primary" disabled={!classId || busy}>添加学生</button>
    </form></section>
    <section className="product-card"><h2>学生列表</h2>{rows.length ? <ul className="simple-list">{rows.map((item) =>
      <li key={item.id}><div><strong>{item.name}</strong><small>学号 {item.student_no}</small></div><div className="list-actions"><span>{item.active ? "在读" : "停用"}</span><button className="text-action" onClick={() => setHistoryStudent(item.id)}>查看 {history.filter((submission) => submission.student_id === item.id).length} 份提交</button></div></li>)}</ul> : <p className="empty-copy">当前班级暂无学生。</p>}</section>
    {historyStudent && <section className="product-card"><h2>{rows.find((item) => item.id === historyStudent)?.name} · 提交历史</h2>
      {history.some((item) => item.student_id === historyStudent) ? <ul className="simple-list">{history.filter((item) => item.student_id === historyStudent).map((item) =>
        <li key={item.id}><strong>{item.created_at}</strong><span>{item.page_count} 页 · {item.status}</span></li>)}</ul> : <p className="empty-copy">暂无提交记录。</p>}</section>}
  </div>;
}

export function ReviewPage() {
  const [queue, setQueue] = useState<ReviewQueueItem[]>([]);
  const [answers, setAnswers] = useState<Record<string,string>>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const load = useCallback(() => {void api.reviewQueue().then((rows) => {setQueue(rows);setError("");}).catch((cause:Error)=>setError(cause.message));},[]);
  useEffect(() => {load();const timer=setInterval(load,3000);return()=>clearInterval(timer);},[load]);
  async function review(resultId:string,decision:"CORRECT"|"INCORRECT") {
    setBusy(resultId);setError("");
    try {await api.reviewQuestion(resultId,decision,answers[resultId] ?? "");load();}
    catch(cause) {setError(cause instanceof Error?cause.message:"保存复核结果失败");}
    finally {setBusy("");}
  }
  return <div className="page-stack review-workspace"><section className="product-card"><div className="product-card-heading"><div><h2>人工复核</h2><p>识别不确定、缺少答案键或题页不匹配的项目会停在这里。</p></div><a href="#/grading">返回作业工作区</a></div>
    {error && <Message text={error} error />}
    {!queue.length && <p className="empty-copy">当前没有待复核题目。</p>}
    {queue.map((item) => <article className="review-submission" key={item.submission.id}>
      <div className="review-submission-heading"><div><span className="eyebrow">{item.assignment_name}</span><h3>{item.student_no} · {item.student_name}</h3></div>
        <span className="status-badge">{item.submission.pages.length} 页 · 待复核 {item.question_results.filter((result)=>result.review_status==="PENDING").length} 题</span></div>
      <div className="review-question-list">{item.question_results.filter((result)=>result.review_status==="PENDING").map((result) => {
        const page=item.submission.pages.find((row)=>row.id===result.page_id);
        return <section className="review-question" key={result.id}>
          {page && !page.source_ref.startsWith("placeholder://") && <a href={imageUrl("original",page.id)} target="_blank" rel="noreferrer"><img src={imageUrl("original",page.id)} alt={`${item.student_name} 第 ${page.page_index} 页作业`} loading="lazy" /></a>}
          <div className="review-question-content"><div className="exam-question-title"><strong>第 {result.question_no} 题</strong><span>{result.rule_code ?? "需要老师判断"}</span></div>
            <p>识别答案：<strong>{result.student_answer ?? "未能可靠识别"}</strong> · 标准答案：{result.expected_answer ?? "未提供"}</p>
            <label>老师确认的答案<input value={answers[result.id] ?? result.student_answer ?? ""} onChange={(event)=>setAnswers((current)=>({...current,[result.id]:event.target.value}))} placeholder="可先修正识别文字" /></label>
            <div className="review-actions"><button className="button primary" disabled={busy===result.id} onClick={()=>void review(result.id,"CORRECT")}>判为正确</button>
              <button className="button secondary" disabled={busy===result.id} onClick={()=>void review(result.id,"INCORRECT")}>判为错误</button></div>
          </div>
        </section>;
      })}</div>
    </article>)}
  </section></div>;
}

export function AnalyticsPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { void api.overview().then(setData).catch((e: Error) => setError(e.message)); }, []);
  return <div className="page-stack"><section className="product-card"><h2>现有数据概览</h2>{error && <Message text={error} error />}
    {data ? <p>当前记录 {data.counts.classes} 个班级、{data.counts.students} 名学生、{data.counts.queued} 份排队中提交。</p> : <p>正在读取…</p>}</section>
    <section className="product-card empty-page"><h2>学习分析</h2><p>将在后续学习分析阶段启用。</p></section></div>;
}

const modelGroups = [{key: "ocr", title: "基础 OCR"}, {key: "formula", title: "数学公式"}, {key: "vision", title: "视觉复核"}];
export function ModelCenterPage() {
  const [models, setModels] = useState<ModelStatus[]>([]);
  const [health, setHealth] = useState<Record<string, ProviderHealth>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const load = useCallback(() => { void api.models().then((rows) => {
    rows.filter((item)=>item.state==="INSTALLED").forEach((item)=>{void api.modelHealth(item.model.id).then((value)=>setHealth((old)=>({...old,[item.model.id]:value}))).catch(()=>{});});
    setModels(rows);
    setHealth((old) => Object.fromEntries(Object.entries(old).filter(([id]) =>
      rows.some((item) => item.model.id === id && item.state === "INSTALLED"))));
    setError("");
  }).catch((e: Error) => setError(e.message)); }, []);
  useEffect(() => {load(); const timer = setInterval(load, 1500); return () => clearInterval(timer);}, [load]);
  async function action(id: string, name: string) {
    setBusy(id); setError("");
    try { await api.modelAction(id, name); load(); }
    catch (e) {setError((e as Error).message);} finally {setBusy("");}
  }
  return <div className="page-stack">{error && <Message text={error} error />}
    {!models.length && !error && <Message text="正在读取模型目录…" />}
    {modelGroups.map((group) => <section className="model-group" key={group.key}><h2>{group.title}</h2>
      <div className="model-grid">{models.filter((item) => item.model.category === group.key).map(({model, state, path, progress, error: modelError}) =>
        <article className="product-card model-card" key={model.id}>
          <div className="model-card-top"><div><h3>{model.display_name}</h3><p>{model.description}</p></div><span className={`model-state state-${state.toLowerCase()}`}>{state}</span></div>
          <dl><div><dt>来源</dt><dd>{model.source}</dd></div><div><dt>运行环境</dt><dd>{model.runtime}</dd></div>
            <div><dt>预计大小</dt><dd>{(model.approximate_size_bytes / 1e9).toFixed(2)} GB</dd></div>
            <div><dt>定位</dt><dd>{model.recommended === "optional" ? "可选候选" : "测试候选"}</dd></div>
            <div><dt>许可</dt><dd>{model.license}</dd></div>
            {model.upstream_repo && <div><dt>原始模型</dt><dd>{model.upstream_repo}</dd></div>}
            {path && <div><dt>本地路径</dt><dd className="path-value">{path}</dd></div>}</dl>
          {progress && <p className="model-progress">{progress.total_files === null ? "准备下载文件列表…" : `已完成 ${progress.completed_files}/${progress.total_files} 个文件`}{progress.current_file ? ` · ${progress.current_file}` : ""}</p>}
          {modelError && <Message text={`${modelError.code}: ${modelError.message}`} error />}
          {health[model.id] && <p className="model-health">Provider：{health[model.id].state} · {health[model.id].lifecycle}</p>}
          <div className="model-actions">
            {state === "NOT_INSTALLED" && <button className="button primary" disabled={busy === model.id} onClick={() => void action(model.id, "install")}>下载</button>}
            {state === "ERROR" && <button className="button primary" disabled={busy === model.id} onClick={() => void action(model.id, "retry")}>重试</button>}
            {state === "ERROR" && path && <button className="button destructive" onClick={() => {if (window.confirm(`删除 ${model.display_name} 的无效本地目录？`)) void action(model.id, "remove");}}>清理无效目录</button>}
            {["QUEUED", "DOWNLOADING"].includes(state) && <button className="button secondary" onClick={() => void action(model.id, "cancel")}>取消</button>}
            {state === "INSTALLED" && <><button className="button secondary" onClick={() => void api.modelAction(model.id,"health",{load:true}).then((result) => setHealth((old) => ({...old, [model.id]: result as ProviderHealth}))).catch((e: Error) => setError(e.message))}>健康检查</button>
              <button className="button secondary" onClick={() => void action(model.id, "open")}>打开目录</button>
              <button className="button destructive" onClick={() => {if (window.confirm(`删除 ${model.display_name} 的本地文件？`)) void action(model.id, "remove");}}>删除</button></>}
          </div>
        </article>)}</div></section>)}
  </div>;
}

export function TemplatesPage() {
  const [groups, setGroups] = useState<TemplateGroup[]>([]);
  const [groupId, setGroupId] = useState("");
  const [pages, setPages] = useState<PageTemplate[]>([]);
  const [pageId, setPageId] = useState("");
  const [detail, setDetail] = useState<PageTemplate | null>(null);
  const [groupForm, setGroupForm] = useState({name: "", grade: "", semester: "", book_name: ""});
  const [pageForm, setPageForm] = useState({page_number: "", name: ""});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const loadGroups = useCallback(async () => { const rows = await api.templateGroups(); setGroups(rows); setGroupId((id) => rows.some((r) => r.id === id) ? id : rows[0]?.id ?? ""); }, []);
  useEffect(() => { void loadGroups().catch((e: Error) => setError(e.message)); }, [loadGroups]);
  useEffect(() => { if (!groupId) {setPages([]); setPageId(""); return;} void api.templatePages(groupId).then((rows) => {setPages(rows); setPageId((id) => rows.some((r) => r.id === id) ? id : rows[0]?.id ?? "");}).catch((e: Error) => setError(e.message)); }, [groupId]);
  useEffect(() => { if (!pageId) {setDetail(null); return;} void api.templatePage(pageId).then(setDetail).catch((e: Error) => setError(e.message)); }, [pageId]);
  const selectedGroup = useMemo(() => groups.find((group) => group.id === groupId), [groups, groupId]);
  async function submitGroup() {
    setBusy(true); setError("");
    try { const created = await api.createTemplateGroup(groupForm); await loadGroups(); setGroupId(created.id); setGroupForm({name: "",grade: "",semester: "",book_name: ""}); }
    catch(e) {setError((e as Error).message);} finally {setBusy(false);}
  }
  async function submitPage() {
    setBusy(true); setError("");
    try {const created = await api.createTemplatePage(groupId, {page_number: Number(pageForm.page_number), name: pageForm.name}); setPages(await api.templatePages(groupId)); setPageId(created.id); setPageForm({page_number: "",name: ""});}
    catch(e) {setError((e as Error).message);} finally {setBusy(false);}
  }
  async function importReference(file: File | undefined) {
    if (!file || !pageId) return;
    setBusy(true); setError("");
    try {setDetail(await api.importTemplateReference(pageId, file.name, await fileAsBase64(file)));}
    catch(e) {setError((e as Error).message);} finally {setBusy(false);}
  }
  return <div className="page-stack">{error && <Message text={error} error />}
    <div className="product-grid-two"><section className="product-card"><h2>模板组</h2><label className="field-label" htmlFor="template-group">当前模板组</label>
      <select id="template-group" value={groupId} onChange={(e) => setGroupId(e.target.value)}><option value="">选择模板组</option>{groups.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
      {selectedGroup && <p className="details-line">{selectedGroup.grade} · {selectedGroup.semester} · {selectedGroup.book_name} · 版本 {selectedGroup.version}</p>}
      <form className="stack-form" onSubmit={(e) => {e.preventDefault(); void submitGroup();}}>
        <h3>创建模板组</h3>{(["name", "grade", "semester", "book_name"] as const).map((key) =>
          <input key={key} aria-label={{name:"名称",grade:"年级",semester:"学期",book_name:"教材名称"}[key]} placeholder={{name:"名称",grade:"年级",semester:"学期",book_name:"教材名称"}[key]} value={groupForm[key]} onChange={(e) => setGroupForm({...groupForm, [key]: e.target.value})} required />)}
        <button className="button primary" disabled={busy}>创建模板组</button></form></section>
      <section className="product-card"><h2>参考页</h2><label className="field-label" htmlFor="template-page">当前页面</label>
        <select id="template-page" value={pageId} onChange={(e) => setPageId(e.target.value)}><option value="">选择页面</option>{pages.map((item) => <option key={item.id} value={item.id}>第 {item.page_number} 页 · {item.name}</option>)}</select>
        <form className="stack-form" onSubmit={(e) => {e.preventDefault(); void submitPage();}}><h3>创建页面</h3>
          <input aria-label="页码" type="number" min="1" placeholder="页码" value={pageForm.page_number} onChange={(e) => setPageForm({...pageForm, page_number:e.target.value})} required />
          <input aria-label="页面名称" placeholder="页面名称" value={pageForm.name} onChange={(e) => setPageForm({...pageForm, name:e.target.value})} required />
          <button className="button primary" disabled={!groupId || busy}>创建页面</button></form></section></div>
    <section className="product-card"><h2>页面详情</h2>{detail ? <><p className="details-line">第 {detail.page_number} 页 · {detail.name} · {detail.active ? "启用" : "停用"}</p>
      <p className="details-line">参考图：{detail.reference_image ?? "尚未导入"}</p>
      <label className="button secondary import-button">导入参考页<input type="file" accept="image/*" disabled={busy} onChange={(e) => {void importReference(e.target.files?.[0]); e.target.value = "";}} /></label>
      <TemplateEditor detail={detail} reload={() => void api.templatePage(pageId).then(setDetail).catch((e:Error)=>setError(e.message))} /></> : <p className="empty-copy">选择或创建一个参考页。</p>}</section>
  </div>;
}

export function SettingsPage() {
  const [info, setInfo] = useState<SystemInfo | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {void api.system().then(setInfo).catch((e: Error) => setError(e.message));}, []);
  const pathLabels: Record<string, string> = {root:"Application Support",data:"数据",originals:"原图",processed:"处理图",crops:"答案裁图",models:"模型",cache:"缓存",logs:"日志",config:"配置"};
  return <div className="page-stack">{error && <Message text={error} error />}{!info && !error && <Message text="正在读取运行环境…" />}
    {info && <><section className="product-card"><h2>运行环境</h2><p>Python {info.runtime_version} · {info.python_supported ? "满足 3.9+ 要求" : "版本低于 3.9"}</p>
      <p className="details-line">识别配置版本 {info.recognition_config.schema_version} · 当前路由 {info.recognition_config.routes.join("、") || "无"}</p>
      <p className="details-line">模型候选路由：{Object.keys(info.recognition_config.model_routes).length ? "已配置" : "识别实验室使用候选路由"}</p>
      <ul className="simple-list">{Object.entries(info.dependencies).map(([name,ready])=><li key={name}><strong>{name}</strong><span>{ready ? "可用" : "缺失"}</span></li>)}</ul></section>
      <section className="product-card"><h2>高级工具</h2><p>检查模板裁图、模型输出及运行历史。</p><a className="button secondary" href="#/lab">打开识别实验室</a></section>
      <section className="product-card"><h2>本地目录</h2><ul className="simple-list">{Object.entries(pathLabels).map(([key, label]) =>
        <li key={key}><div><strong>{label}</strong><small className="path-value">{info.paths[key]}</small></div>
          <button className="button secondary" onClick={() => void api.openDirectory(key).catch((e: Error) => setError(e.message))}>在 Finder 中打开</button></li>)}</ul></section></>}
  </div>;
}
