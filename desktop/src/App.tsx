import { useCallback, useEffect, useMemo, useState } from "react";
import { api, fileAsBase64, type Assignment, type ClassRecord, type Student, type Submission } from "./api";

const now = new Date();
const today = new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);

const statusLabels: Record<string, string> = {
  EMPTY: "未开始",
  CAPTURING: "采集中",
  READY: "已就绪",
  QUEUED: "排队中",
  PROCESSING: "处理中",
  REVIEW_REQUIRED: "需要复核",
  COMPLETED: "处理完成",
  FAILED: "处理失败",
};
const captureStages = ["CAPTURING", "READY", "QUEUED", "PROCESSING", "COMPLETED"];

function App() {
  const [serviceReady, setServiceReady] = useState(false);
  const [classes, setClasses] = useState<ClassRecord[]>([]);
  const [classId, setClassId] = useState("");
  const [students, setStudents] = useState<Student[]>([]);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [studentId, setStudentId] = useState("");
  const [assignmentId, setAssignmentId] = useState("");
  const [submission, setSubmission] = useState<Submission | null>(null);
  const [className, setClassName] = useState("");
  const [studentNo, setStudentNo] = useState("");
  const [studentName, setStudentName] = useState("");
  const [assignmentName, setAssignmentName] = useState("");
  const [assignmentDate, setAssignmentDate] = useState(today);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const selectedStudent = useMemo(() => students.find((student) => student.id === studentId), [students, studentId]);
  const selectedAssignment = useMemo(() => assignments.find((assignment) => assignment.id === assignmentId), [assignments, assignmentId]);

  const refreshClassData = useCallback(async (selectedClassId: string) => {
    if (!selectedClassId) {
      setStudents([]);
      setAssignments([]);
      setStudentId("");
      setAssignmentId("");
      return;
    }
    const [studentRows, assignmentRows] = await Promise.all([
      api.students(selectedClassId),
      api.assignments(selectedClassId),
    ]);
    setStudents(studentRows);
    setAssignments(assignmentRows);
    setStudentId((current) => studentRows.some((student) => student.id === current) ? current : studentRows[0]?.id ?? "");
    setAssignmentId((current) => assignmentRows.some((assignment) => assignment.id === current) ? current : assignmentRows[0]?.id ?? "");
  }, []);

  const load = useCallback(async () => {
    try {
      await api.health();
      setServiceReady(true);
      const rows = await api.classes();
      setClasses(rows);
      setClassId((current) => rows.some((item) => item.id === current) ? current : rows[0]?.id ?? "");
      setError("");
    } catch (cause) {
      setServiceReady(false);
      setError(cause instanceof Error ? cause.message : "本地服务连接失败");
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 3000);
    return () => window.clearInterval(timer);
  }, [load]);

  useEffect(() => {
    void refreshClassData(classId).catch((cause: unknown) => {
      setError(cause instanceof Error ? cause.message : "读取班级数据失败");
    });
  }, [classId, refreshClassData]);

  useEffect(() => {
    if (!submission || !["QUEUED", "PROCESSING", "READY"].includes(submission.status)) return;
    const timer = window.setInterval(() => {
      void api.submission(submission.id).then(setSubmission).catch((cause: unknown) => {
        setError(cause instanceof Error ? cause.message : "读取批改状态失败");
      });
    }, 500);
    return () => window.clearInterval(timer);
  }, [submission?.id, submission?.status]);

  async function withBusy(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }

  async function createClass() {
    await withBusy(async () => {
      const created = await api.createClass(className);
      setClassName("");
      const rows = await api.classes();
      setClasses(rows);
      setClassId(created.id);
    });
  }

  async function createStudent() {
    if (!classId) return;
    await withBusy(async () => {
      const created = await api.createStudent(classId, studentNo, studentName);
      setStudentNo("");
      setStudentName("");
      await refreshClassData(classId);
      setStudentId(created.id);
    });
  }

  async function createAssignment() {
    if (!classId) return;
    await withBusy(async () => {
      const created = await api.createAssignment(classId, assignmentName, assignmentDate);
      setAssignmentName("");
      await refreshClassData(classId);
      setAssignmentId(created.id);
    });
  }

  async function startSubmission() {
    if (!studentId || !assignmentId) return;
    await withBusy(async () => {
      const created = await api.createSubmission(assignmentId, studentId);
      setSubmission(await api.startSubmission(created.id));
    });
  }

  async function addPlaceholder() {
    if (!submission) return;
    await withBusy(async () => {
      const response = await api.addPlaceholderPage(submission.id);
      setSubmission(response.submission);
    });
  }

  async function addImages(files: FileList | null) {
    if (!submission || !files?.length) return;
    await withBusy(async () => {
      let updated = submission;
      for (const file of Array.from(files)) {
        const encoded = await fileAsBase64(file);
        const response = await api.addImagePage(submission.id, file.name, encoded);
        updated = response.submission;
      }
      setSubmission(updated);
    });
  }

  async function finishStudent() {
    if (!submission) return;
    await withBusy(async () => {
      setSubmission(await api.finishSubmission(submission.id));
    });
  }

  const canCapture = submission?.status === "CAPTURING";
  const canStart = serviceReady && !submission && Boolean(studentId && assignmentId);

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand-mark" aria-hidden="true">数</div>
        <div className="brand-copy">
          <p className="eyebrow">LOCAL CLASSROOM TOOLS</p>
          <h1>作业批改系统</h1>
        </div>
        <div className={`service-pill ${serviceReady ? "online" : "offline"}`}>
          <span className="service-dot" />
          {serviceReady ? "本地服务已连接" : "本地服务未连接"}
        </div>
      </header>

      {error && <div className="notice error" role="alert">{error}</div>}

      <section className="workspace-grid">
        <div className="main-column">
          <section className="card setup-card">
            <div className="section-heading">
              <div>
                <p className="eyebrow">01 / CLASSROOM</p>
                <h2>班级与作业</h2>
              </div>
              <span className="step-number">01</span>
            </div>

            <label className="field-label" htmlFor="class-select">当前班级</label>
            <div className="inline-controls">
              <select id="class-select" value={classId} onChange={(event) => { setClassId(event.target.value); setSubmission(null); }} disabled={!serviceReady}>
                <option value="">选择班级</option>
                {classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
            </div>
            <form className="form-row class-create" onSubmit={(event) => { event.preventDefault(); void createClass(); }}>
              <input aria-label="新班级名称" placeholder="新建班级名称" value={className} onChange={(event) => setClassName(event.target.value)} required />
              <button className="button secondary" disabled={busy || !serviceReady}>创建班级</button>
            </form>

            {classId && <div className="entity-grid">
              <form className="mini-form" onSubmit={(event) => { event.preventDefault(); void createStudent(); }}>
                <div className="mini-heading"><span className="mini-icon">人</span><h3>学生</h3><span className="count">{students.length}</span></div>
                <label className="field-label" htmlFor="student-select">当前学生</label>
                <select id="student-select" value={studentId} onChange={(event) => { setStudentId(event.target.value); setSubmission(null); }}>
                  <option value="">选择学生</option>
                  {students.map((item) => <option key={item.id} value={item.id}>{item.student_no} · {item.name}</option>)}
                </select>
                <div className="stacked-fields">
                  <input aria-label="学号" placeholder="学号" value={studentNo} onChange={(event) => setStudentNo(event.target.value)} required />
                  <input aria-label="学生姓名" placeholder="学生姓名" value={studentName} onChange={(event) => setStudentName(event.target.value)} required />
                </div>
                <button className="button subtle full-width" disabled={busy || !serviceReady}>添加学生</button>
              </form>

              <form className="mini-form" onSubmit={(event) => { event.preventDefault(); void createAssignment(); }}>
                <div className="mini-heading"><span className="mini-icon assignment-icon">作</span><h3>作业</h3><span className="count">{assignments.length}</span></div>
                <label className="field-label" htmlFor="assignment-select">当前作业</label>
                <select id="assignment-select" value={assignmentId} onChange={(event) => { setAssignmentId(event.target.value); setSubmission(null); }}>
                  <option value="">选择作业</option>
                  {assignments.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.date}</option>)}
                </select>
                <div className="stacked-fields">
                  <input aria-label="作业名称" placeholder="作业名称" value={assignmentName} onChange={(event) => setAssignmentName(event.target.value)} required />
                  <input aria-label="作业日期" type="date" value={assignmentDate} onChange={(event) => setAssignmentDate(event.target.value)} required />
                </div>
                <button className="button subtle full-width" disabled={busy || !serviceReady}>创建作业</button>
              </form>
            </div>}
          </section>

          <section className="card capture-card">
            <div className="section-heading">
              <div>
                <p className="eyebrow">02 / SUBMISSION</p>
                <h2>学生作业采集</h2>
              </div>
              <span className="step-number">02</span>
            </div>

            {!submission && <div className="start-panel">
              <div className="start-illustration" aria-hidden="true"><span>＋</span><i>页</i></div>
              <div className="start-copy">
                <strong>{selectedStudent?.name ?? "选择一名学生"}</strong>
                <span>{selectedAssignment?.name ?? "选择一项作业"}</span>
                <p>开始后可连续添加多页。拍完一页不会自动切换学生。</p>
              </div>
              <button className="button primary" onClick={() => void startSubmission()} disabled={!canStart || busy}>开始该生</button>
            </div>}

            {submission && <div className="submission-panel">
              <div className="submission-person">
                <div className="avatar">{selectedStudent?.name.slice(0, 1) ?? "学"}</div>
                <div className="person-copy">
                  <span className="eyebrow">当前 Submission</span>
                  <strong>{selectedStudent?.name ?? "当前学生"}</strong>
                  <span>{selectedAssignment?.name ?? "当前作业"}</span>
                </div>
                <span className={`status-badge status-${submission.status.toLowerCase()}`}>
                  {statusLabels[submission.status] ?? submission.status}
                </span>
              </div>

              <div className="page-counter">
                <span className="page-icon">▤</span>
                <div><strong>{submission.page_count}</strong><span>已添加页面</span></div>
                <span className="page-hint">可继续添加，完成按钮不会自动切换学生</span>
              </div>

              <ol className="status-timeline" aria-label="Submission 处理状态">
                {captureStages.map((stage) => {
                  const currentIndex = captureStages.indexOf(submission.status);
                  const stageIndex = captureStages.indexOf(stage);
                  const done = currentIndex >= 0 && stageIndex < currentIndex;
                  const active = submission.status === stage;
                  return <li className={`${done ? "done" : ""} ${active ? "active" : ""}`} key={stage}>
                    <span>{done ? "✓" : stageIndex + 1}</span>{statusLabels[stage]}
                  </li>;
                })}
              </ol>

              {canCapture && <div className="capture-actions">
                <button className="button secondary" onClick={() => void addPlaceholder()} disabled={busy}>添加占位页</button>
                <label className={`button subtle file-button ${busy ? "disabled" : ""}`}>
                  选择图片
                  <input type="file" accept="image/*" multiple disabled={busy} onChange={(event) => { void addImages(event.target.files); event.target.value = ""; }} />
                </label>
                <button className="button primary finish-button" onClick={() => void finishStudent()} disabled={busy || submission.page_count < 1}>完成该生</button>
              </div>}

              {submission.pages.length > 0 && <ol className="page-list">
                {submission.pages.map((page) => <li key={page.id}><span className="page-index">{String(page.page_index).padStart(2, "0")}</span><span>第 {page.page_index} 页</span><code>{page.source_ref.startsWith("placeholder://") ? "测试占位页" : "本地图片"}</code></li>)}
              </ol>}

              {submission.error && <div className="notice error result-error">{submission.error}</div>}

              {(submission.status === "QUEUED" || submission.status === "PROCESSING") && <div className="processing-note"><span className="spinner" />后台正在处理，你可以继续管理班级数据。</div>}

              {submission.status === "COMPLETED" && <div className="results-panel">
                <div className="results-title"><span className="success-mark">✓</span><div><strong>Mock 识别完成</strong><span>结果已保存在本地 SQLite</span></div></div>
                {submission.results.map((result) => <div className="result-row" key={result.id}>
                  <span>第 {submission.pages.find((page) => page.id === result.page_id)?.page_index ?? "?"} 页</span>
                  <strong>{result.text ?? "无识别文本"}</strong>
                  <span>{result.provider} / {result.model}</span>
                  <span>{result.confidence === null ? "—" : `${Math.round(result.confidence * 100)}%`}</span>
                </div>)}
              </div>}

              {submission.status === "FAILED" && <div className="notice error">本次处理失败。错误已保存，可以记录问题后重新开始。</div>}
            </div>}
          </section>
        </div>

        <aside className="side-column">
          <section className="card flow-card">
            <p className="eyebrow">WORKFLOW</p>
            <h2>本地处理流程</h2>
            <ol className="flow-list">
              <li className="flow-done"><span>1</span><div><strong>选择学生</strong><small>每次作业创建一个 Submission</small></div></li>
              <li className={submission ? "flow-done" : ""}><span>2</span><div><strong>添加作业页面</strong><small>支持多页和本地图片</small></div></li>
              <li className={submission && ["QUEUED", "PROCESSING", "COMPLETED"].includes(submission.status) ? "flow-done" : ""}><span>3</span><div><strong>完成该生</strong><small>明确点击后才进入处理队列</small></div></li>
              <li className={submission?.status === "COMPLETED" ? "flow-done" : ""}><span>4</span><div><strong>Mock 识别与保存</strong><small>后台顺序处理并写回结果</small></div></li>
            </ol>
            <div className="local-note"><span>⌂</span><p>班级、学生、页面引用和批改结果均保存在此 Mac。</p></div>
          </section>

          <section className="card provider-card">
            <p className="eyebrow">RECOGNITION</p>
            <div className="provider-heading"><span className="provider-mark">M</span><div><h3>Mock Provider</h3><span>mock-v1 · 可插拔接口</span></div></div>
            <p>当前使用本地配置的模拟识别结果。后续增加模型时不需要改动此页面或 Submission 流程。</p>
          </section>
        </aside>
      </section>
      <footer className="footer"><span>MATH GRADER</span><span>Application Foundation · Local-first</span></footer>
    </main>
  );
}

export default App;
