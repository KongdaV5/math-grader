import { useCallback, useEffect, useMemo, useState } from "react";
import { api, imageUrl, type AssignmentExamTemplate, type ExamQuestionDraft,
  type GradingResult, type Submission, type TemplateGroup } from "./api";

const statusText: Record<string, string> = {
  READY: "可开始批改", QUEUED: "等待批改", PROCESSING: "正在识别与判分",
  REVIEW_REQUIRED: "等待人工复核", COMPLETED: "已完成", FAILED: "处理失败",
};
const answerTypes = ["integer", "decimal", "choice", "boolean", "comparison_symbol", "fraction", "formula", "short_text", "sequence", "multi_blank"];

type Props = {
  assignmentId: string;
  assignmentLabel: string;
  workflowMode?: string;
  requestedSubmissionId: string;
  onOpened: () => void;
  onAssignmentModeChanged: () => void;
};

export function SubmissionWorkspace({ assignmentId, assignmentLabel, workflowMode, requestedSubmissionId, onOpened, onAssignmentModeChanged }: Props) {
  const [rows, setRows] = useState<Submission[]>([]);
  const [submission, setSubmission] = useState<Submission | null>(null);
  const [exam, setExam] = useState<AssignmentExamTemplate | null>(null);
  const [groups, setGroups] = useState<TemplateGroup[]>([]);
  const [libraryId, setLibraryId] = useState("");
  const [grade, setGrade] = useState<GradingResult | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadRows = useCallback(async () => {
    if (!assignmentId) { setRows([]); return; }
    const next = await api.submissions(assignmentId);
    setRows(next);
    setSubmission((current) => {
      const refreshed = current && next.find((item) => item.id === current.id);
      return refreshed ? {...current, ...refreshed} : current;
    });
  }, [assignmentId]);

  const openSubmission = useCallback(async (id: string) => {
    setBusy("open"); setError(""); setNotice("");
    try {
      const [opened, template] = await Promise.all([api.submission(id), api.assignmentExam(assignmentId)]);
      setSubmission(opened); setExam(template);
      if (["QUEUED", "PROCESSING", "REVIEW_REQUIRED", "COMPLETED"].includes(opened.status)) {
        setGrade(await api.gradingResult(id));
      } else setGrade(null);
      document.getElementById("submission-workspace")?.scrollIntoView({behavior: "smooth", block: "start"});
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "无法打开这份提交");
    } finally { setBusy(""); }
  }, [assignmentId]);

  useEffect(() => {
    if (!requestedSubmissionId) return;
    void openSubmission(requestedSubmissionId);
    onOpened();
  }, [onOpened, openSubmission, requestedSubmissionId]);

  useEffect(() => {
    setRows([]); setSubmission(null); setGrade(null); setExam(null);
    if (!assignmentId) return;
    void loadRows().catch((cause: Error) => setError(cause.message));
    const timer = window.setInterval(() => { void loadRows().catch(() => {}); }, 2000);
    void api.templateGroups().then(setGroups).catch(() => {});
    void api.assignmentExam(assignmentId).then(setExam).catch((cause: Error) => setError(cause.message));
    return () => window.clearInterval(timer);
  }, [assignmentId, loadRows]);

  useEffect(() => {
    if (!submission || !["QUEUED", "PROCESSING"].includes(submission.status)) return;
    const timer = window.setInterval(() => {
      void Promise.all([api.submission(submission.id), api.gradingResult(submission.id)])
        .then(([next, result]) => {setSubmission(next); setGrade(result);})
        .catch((cause: Error) => setError(cause.message));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [submission?.id, submission?.status]);

  const pageByNumber = useMemo(() => new Map((submission?.pages ?? []).map((page) => [page.page_index, page])), [submission?.pages]);

  async function run(action: string, operation: () => Promise<void>) {
    setBusy(action); setError(""); setNotice("");
    try { await operation(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "操作失败"); }
    finally { setBusy(""); }
  }

  function updateQuestion(pageIndex: number, questionIndex: number, patch: Partial<ExamQuestionDraft>) {
    setExam((current) => {
      if (!current) return current;
      const pages = current.draft.pages.map((page) => page.page_index !== pageIndex ? page : ({
        ...page, questions: page.questions.map((question, index) => index === questionIndex ? {...question, ...patch} : question),
      }));
      return {...current, draft: {pages}};
    });
  }

  async function saveDraft() {
    if (!exam) return;
    const saved = await api.updateExamDraft(assignmentId, exam.draft);
    setExam(saved); setNotice("答案区域和答案候选已保存。");
  }

  async function confirmExam() {
    if (!exam) return;
    await api.updateExamDraft(assignmentId, exam.draft);
    const confirmed = await api.confirmExam(assignmentId);
    setExam(confirmed);
    setNotice(confirmed.temporary_template_created ? "本次测验临时模板已确认；后续学生将复用这份结构。" : "题册已绑定到本次作业。后续学生将复用这份结构。");
  }

  async function startGrading() {
    if (!submission) return;
    await api.startGrading(submission.id);
    const next = await api.submission(submission.id);
    setSubmission(next); setGrade(await api.gradingResult(submission.id));
    setNotice("已开始识别与判分，完成后会显示需要复核的题目。");
    await loadRows();
  }

  return <section id="submission-workspace" className="card submission-workspace">
    <div className="section-heading"><div><p className="eyebrow">ASSIGNMENT → STUDENT → SUBMISSION → PAGES</p><h2>作业页面与批改工作区</h2></div></div>
    {error && <div className="notice error" role="alert">{error}</div>}
    {notice && <div className="notice success" role="status">{notice}</div>}
    {!assignmentId && <p className="empty-copy">先选择一项作业，查看学生已提交的页面。</p>}
    {assignmentId && <>
      <div className="submission-list-heading"><strong>{assignmentLabel || "当前作业"}</strong><span>{rows.length} 份学生提交</span></div>
      {workflowMode !== "TEACHER_WORKFLOW" && rows.every((item) => item.status === "EMPTY") && <div className="legacy-workflow-notice">
        <p>这项作业还没有开始拍摄。启用老师批改流程后，可以选择已有题册，或对一份新试卷做一次 AI 分析。</p>
        <button className="button secondary" type="button" disabled={Boolean(busy)} onClick={() => void run("enable",async () => {await api.enableTeacherWorkflow(assignmentId);onAssignmentModeChanged();setNotice("老师批改流程已启用。");})}>启用老师批改流程</button>
      </div>}
      {rows.length ? <ul className="submission-workspace-list">{rows.map((item) => <li key={item.id}>
        <div><strong>{item.student_no} · {item.student_name ?? item.student_id.slice(0, 8)}</strong><span>{item.page_count} 页 · {statusText[item.status] ?? item.status}{item.score !== null && item.score !== undefined ? ` · ${item.score}/${item.max_score}` : ""}</span></div>
        <button type="button" className="button secondary" onClick={() => void openSubmission(item.id)} disabled={busy === "open"}>查看并开始批改</button>
      </li>)}</ul> : <p className="empty-copy">手机完成一名学生后，照片会自动出现在这里。</p>}
    </>}

    {submission && <div className="submission-detail">
      <div className="submission-detail-heading"><div><span className="eyebrow">{submission.status}</span><h3>Submission · {submission.id.slice(0, 8)}</h3></div>
        <span className="status-badge">{statusText[submission.status] ?? submission.status}</span></div>
      <div className="submission-photo-grid">{submission.pages.map((page) => <figure key={page.id} className="submission-photo">
        {page.source_ref.startsWith("placeholder://")
          ? <div className="submission-photo-placeholder">测试占位页</div>
          : <a href={imageUrl("original", page.id)} target="_blank" rel="noreferrer" aria-label={`打开第 ${page.page_index} 页原图`}>
            <img src={imageUrl("original", page.id)} alt={`第 ${page.page_index} 页学生作业`} loading="lazy" />
          </a>}
        <figcaption>第 {page.page_index} 页{page.original_filename ? ` · ${page.original_filename}` : ""}</figcaption>
      </figure>)}</div>

      {workflowMode === "TEACHER_WORKFLOW" && submission.status !== "CAPTURING" && <div className="exam-setup">
        <div className="product-card-heading"><div><span className="eyebrow">ONE-TIME EXAM SETUP</span><h3>本次测验试卷结构</h3></div>
          {exam?.status === "CONFIRMED" && <span className="status-badge status-completed">已确认 · 学生共用</span>}
        </div>
        {!exam && <div className="exam-entry-options">
          <article><h4>使用已有题册</h4><p>选择模板库中的题册，答案和页面结构会用于本次作业。</p>
            <label className="field-label" htmlFor="library-template">题册</label>
            <select id="library-template" value={libraryId} onChange={(event) => setLibraryId(event.target.value)}>
              <option value="">选择已有题册</option>{groups.map((group) => <option key={group.id} value={group.id}>{group.name} · {group.book_name}</option>)}
            </select>
            <button className="button secondary" type="button" disabled={!libraryId || Boolean(busy)} onClick={() => void run("library", async () => {setExam(await api.chooseLibraryTemplate(assignmentId, libraryId));})}>载入题册</button>
          </article>
          <article><h4>分析一份新试卷</h4><p>使用当前选中的多页作业作为试卷样本。Qwen3-VL 4B 会逐页提出题目、答案区域和标准答案候选。</p>
            <button className="button primary" type="button" disabled={!submission.pages.length || Boolean(busy) || !["READY", "COMPLETED", "REVIEW_REQUIRED"].includes(submission.status)} onClick={() => void run("analyze", async () => {setExam(await api.analyzeExam(assignmentId, submission.id));})}>
              {busy === "analyze" ? "正在分析整页试卷…" : "自动分析本次试卷"}
            </button>
          </article>
        </div>}
        {exam?.status === "DRAFT" && <div className="answer-key-builder">
          <div className="answer-key-heading"><div><h4>答案区域与标准答案候选</h4><p>逐题检查 AI 给出的题目、框选区域和答案；修改后再一次确认整份试卷。</p></div>
            <span>{exam.draft.pages.reduce((total, page) => total + page.questions.length, 0)} 题</span></div>
          {exam.draft.pages.map((page) => {
            const sourcePage = pageByNumber.get(page.page_index);
            return <section className="exam-draft-page" key={page.page_index}>
              <div className="exam-draft-page-title"><strong>第 {page.page_index} 页 · {page.questions.length} 题</strong>
                {sourcePage && !sourcePage.source_ref.startsWith("placeholder://") && <a href={imageUrl("original", sourcePage.id)} target="_blank" rel="noreferrer">查看原图</a>}
              </div>
              {sourcePage && !sourcePage.source_ref.startsWith("placeholder://") && <div className="exam-template-canvas" aria-label={`第 ${page.page_index} 页试卷与答案区域候选`}>
                <img src={imageUrl("original", sourcePage.id)} alt={`第 ${page.page_index} 页试卷`} loading="lazy" />
                {page.questions.map((question) => question.answer_region && <div key={`region-${question.question_no}`} className="exam-region-overlay"
                  style={{left:`${question.answer_region.x*100}%`,top:`${question.answer_region.y*100}%`,width:`${question.answer_region.width*100}%`,height:`${question.answer_region.height*100}%`}}
                  aria-label={`第 ${question.question_no} 题答案区域候选`}>{question.question_no}</div>)}
              </div>}
              {page.questions.map((question, index) => <article className="exam-question" key={`${page.page_index}-${question.question_no}`}>
                <div className="exam-question-title"><strong>第 {question.question_no} 题</strong><span>{question.confidence === null ? "结构待确认" : `结构信心 ${Math.round(question.confidence * 100)}%`}</span></div>
                <label>题目描述<input value={question.question_text} onChange={(event) => updateQuestion(page.page_index,index,{question_text:event.target.value})} /></label>
                <div className="answer-key-fields">
                  <label>答案类型<select value={question.answer_type} onChange={(event) => updateQuestion(page.page_index,index,{answer_type:event.target.value})}>{answerTypes.map((type) => <option key={type}>{type}</option>)}</select></label>
                  <label>标准答案候选<input aria-label={`第 ${question.question_no} 题标准答案候选`} value={question.answer_key_candidate ?? ""} onChange={(event) => updateQuestion(page.page_index,index,{answer_key_candidate:event.target.value || null})} placeholder="老师输入或修正答案" /></label>
                  <label>分值<input type="number" min="0" step="0.5" value={question.score} onChange={(event) => updateQuestion(page.page_index,index,{score:Number(event.target.value)})} /></label>
                </div>
                <fieldset className="answer-region-fields"><legend>答案区域候选（相对整页 0–1）</legend>
                  {(["x","y","width","height"] as const).map((key) => <label key={key}>{key}<input type="number" min="0" max="1" step="0.01" value={question.answer_region?.[key] ?? ""} onChange={(event) => {
                    const current = question.answer_region ?? {x:0,y:0,width:0.2,height:0.08};
                    updateQuestion(page.page_index,index,{answer_region:{...current,[key]:event.target.value === "" ? 0 : Number(event.target.value)}});
                  }} /></label>)}
                </fieldset>
                {question.analysis_note && <small className="exam-analysis-note">分析提示：{question.analysis_note}</small>}
              </article>)}
            </section>;
          })}
          <div className="exam-template-actions">
            <button className="button secondary" type="button" disabled={Boolean(busy)} onClick={() => void run("save",saveDraft)}>保存修改</button>
            <button className="button primary" type="button" disabled={Boolean(busy) || !exam.draft.pages.every((page) => page.questions.every((question) => question.answer_region !== null))} onClick={() => void run("confirm",confirmExam)}>
              {busy === "confirm" ? "正在生成临时模板…" : "老师确认本次试卷"}
            </button>
          </div>
        </div>}
        {exam?.status === "CONFIRMED" && <div className="confirmed-exam">
          <p>{exam.draft.pages.length} 页 · {exam.draft.pages.reduce((total,page)=>total+page.questions.length,0)} 题。标准答案由老师确认，确定性规则负责判分；不确定答案进入人工复核。</p>
          <button className="button primary" type="button" disabled={Boolean(busy) || !["READY", "FAILED"].includes(submission.status)} onClick={() => void run("grade",startGrading)}>
            {busy === "grade" ? "正在排入批改…" : "识别答案并开始判分"}
          </button>
        </div>}
      </div>}

      {grade?.question_results.length ? <section className="grading-results">
        <div className="product-card-heading"><div><span className="eyebrow">QUESTION RESULTS</span><h3>逐题结果</h3></div>
          {grade.submission.score !== null && grade.submission.score !== undefined && <strong className="submission-score">{grade.submission.score} / {grade.submission.max_score}</strong>}
        </div>
        <ol>{grade.question_results.map((result) => <li key={result.id}><span>第 {result.question_no} 题</span><strong>{result.student_answer ?? "待人工复核"}</strong><span>{result.expected_answer ?? "答案待确认"}</span><b>{result.decision_status === "CORRECT" ? "正确" : result.decision_status === "INCORRECT" ? "错误" : "需要复核"}</b></li>)}</ol>
        {submission.status === "REVIEW_REQUIRED" && <a className="button secondary" href="#/review">前往人工复核</a>}
      </section> : null}
    </div>}
  </section>;
}
