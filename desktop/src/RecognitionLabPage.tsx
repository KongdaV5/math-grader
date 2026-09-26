import {useEffect,useState} from "react";
import {api,fileAsBase64,imageUrl,type Assignment,type ClassRecord,type LabDetail,type ModelStatus,type PageTemplate,type Submission,type TemplateGroup} from "./api";

export function RecognitionLabPage(){
  const [classes,setClasses]=useState<ClassRecord[]>([]),[classId,setClassId]=useState("");
  const [assignments,setAssignments]=useState<Assignment[]>([]),[assignmentId,setAssignmentId]=useState("");
  const [submissions,setSubmissions]=useState<Submission[]>([]),[submissionId,setSubmissionId]=useState("");
  const [pageId,setPageId]=useState(""),[detail,setDetail]=useState<LabDetail|null>(null);
  const [groups,setGroups]=useState<TemplateGroup[]>([]),[groupId,setGroupId]=useState("");
  const [templates,setTemplates]=useState<PageTemplate[]>([]),[templateId,setTemplateId]=useState("");
  const [models,setModels]=useState<ModelStatus[]>([]),[modelId,setModelId]=useState("pp-ocrv6-small");
  const [candidates,setCandidates]=useState<Array<{template_id:string;name:string;score:number}>>([]);
  const [error,setError]=useState(""),[busy,setBusy]=useState("");
  useEffect(()=>{void api.classes().then(setClasses).catch((e:Error)=>setError(e.message));void api.templateGroups().then(setGroups).catch((e:Error)=>setError(e.message));void api.models().then(setModels).catch((e:Error)=>setError(e.message));},[]);
  useEffect(()=>{if(classId)void api.assignments(classId).then(setAssignments).catch((e:Error)=>setError(e.message));else setAssignments([]);setAssignmentId("");},[classId]);
  useEffect(()=>{if(assignmentId)void api.submissions(assignmentId).then(setSubmissions).catch((e:Error)=>setError(e.message));else setSubmissions([]);setSubmissionId("");},[assignmentId]);
  useEffect(()=>{if(groupId)void api.templatePages(groupId).then(setTemplates).catch((e:Error)=>setError(e.message));else setTemplates([]);setTemplateId("");},[groupId]);
  useEffect(()=>{if(!pageId){setDetail(null);return;}const load=()=>{void api.pageDetail(pageId).then(setDetail).catch((e:Error)=>setError(e.message));};load();const timer=setInterval(load,2000);return()=>clearInterval(timer);},[pageId]);
  async function task(name:string,work:()=>Promise<unknown>){setBusy(name);setError("");try{await work();if(pageId)setDetail(await api.pageDetail(pageId));}catch(e){setError((e as Error).message);}finally{setBusy("");}}
  async function importFile(file?:File){if(!file)return;await task("导入",async()=>{const page=await api.labImport(file.name,await fileAsBase64(file));setPageId(page.id);});}
  async function exportJsonl(){if(!pageId)return;await task("导出",async()=>{const rows=await api.pagePredictions(pageId);
    const blob=new Blob([rows.map((row)=>JSON.stringify(row)).join("\n")+"\n"],{type:"application/x-ndjson"});
    const url=URL.createObjectURL(blob);const link=document.createElement("a");link.href=url;link.download=`predictions-${pageId}.jsonl`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});}
  const overlays=detail?.binding?.snapshot.questions??templates.find((t)=>t.id===templateId)?.questions??[];
  const visibleCrops=detail?.crops.filter((c)=>c.binding_id===detail.page.template_binding_id)??[];
  return <div className="page-stack">
    <section className="product-card"><h2>图片与模板</h2><p className="details-line">用于检查识别链路；结果保留历史记录。</p>
      {error&&<p role="alert" className="message error">{error}</p>}
      <label className="button secondary import-button">导入测试作业页<input type="file" accept="image/*" disabled={!!busy} onChange={(e)=>{void importFile(e.target.files?.[0]);e.target.value="";}}/></label>
      {busy&&<p role="status">正在{busy}…</p>}
      <div className="product-grid-two"><div><h3>已有 SubmissionPage</h3>
        <select aria-label="班级" value={classId} onChange={(e)=>setClassId(e.target.value)}><option value="">班级</option>{classes.map((item)=><option key={item.id} value={item.id}>{item.name}</option>)}</select>
        <select aria-label="作业" value={assignmentId} onChange={(e)=>setAssignmentId(e.target.value)}><option value="">作业</option>{assignments.map((item)=><option key={item.id} value={item.id}>{item.name}</option>)}</select>
        <select aria-label="提交" value={submissionId} onChange={(e)=>setSubmissionId(e.target.value)}><option value="">提交</option>{submissions.map((item)=><option key={item.id} value={item.id}>{item.student_id} · {item.page_count} 页</option>)}</select>
        <select aria-label="页面" value={pageId} onChange={(e)=>setPageId(e.target.value)}><option value="">页面</option>{submissions.find((s)=>s.id===submissionId)?.pages.map((page)=><option key={page.id} value={page.id}>第 {page.page_index} 页 · {page.processing_status??"PENDING"}</option>)}</select></div>
        <div><h3>PageTemplate</h3>
        <select aria-label="模板组" value={groupId} onChange={(e)=>setGroupId(e.target.value)}><option value="">模板组</option>{groups.map((item)=><option key={item.id} value={item.id}>{item.name}</option>)}</select>
        <select aria-label="页面模板" value={templateId} onChange={(e)=>setTemplateId(e.target.value)}><option value="">页面模板</option>{templates.map((item)=><option key={item.id} value={item.id}>{item.name} · v{item.version}</option>)}</select>
        <div className="inline-controls"><button className="button secondary" disabled={!pageId||!!busy} onClick={()=>void task("处理图片",()=>api.pageProcess(pageId))}>运行 ImagePipeline</button>
        <button className="button secondary" disabled={!pageId||!!busy} onClick={()=>void task("匹配模板",async()=>{setCandidates(await api.pageMatch(pageId));})}>推荐模板</button>
        <button className="button primary" disabled={!pageId||!templateId||!!busy} onClick={()=>void task("绑定模板",()=>api.pageBind(pageId,templateId))}>人工绑定</button></div>
        {candidates.map((item)=><p key={item.template_id}>{item.name} · {item.score.toFixed(2)} <button className="button secondary" onClick={()=>setTemplateId(item.template_id)}>选择</button></p>)}</div></div>
      {detail&&<><p>图像 {detail.page.processing_status} · {detail.page.processing_warning??"无质量提示"}{detail.page.processing_error&&` · ${detail.page.processing_error}`}</p>
        {detail.page.processed_image&&<div className="lab-image"><img src={imageUrl("processed",pageId)} alt="处理后的作业页"/>
          {overlays.flatMap((q)=>q.regions.map((r)=><div key={r.id} className="lab-overlay" style={{left:`${r.x*100}%`,top:`${r.y*100}%`,width:`${r.width*100}%`,height:`${r.height*100}%`}}>{q.question_no}.{r.region_index}</div>))}</div>}
        <p>绑定：{detail.binding?`${detail.binding.snapshot.name} · v${detail.binding.template_version}`:"未绑定"}</p>
        <button className="button primary" disabled={!detail.binding||!!busy} onClick={()=>void task("生成裁图",()=>api.pageCrops(pageId))}>生成答案裁图</button></>}
    </section>
    {visibleCrops.length>0&&<section className="product-card"><h2>答案裁图与 RecognitionRun</h2>
      <div className="inline-controls"><select aria-label="运行模型" value={modelId} onChange={(e)=>setModelId(e.target.value)}>{models.map((item)=><option key={item.model.id} value={item.model.id}>{item.model.display_name} · {item.state}</option>)}</select>
        <button className="button secondary" disabled={!!busy} onClick={()=>void exportJsonl()}>导出 P0 predictions JSONL</button></div>
      <div className="lab-crops">{visibleCrops.map((crop)=><article className="lab-crop product-card" key={crop.id}>
        <h3>第 {crop.question_no} 题 · 区域 {crop.region_index}</h3><img src={imageUrl("crop",crop.id)} alt={`第 ${crop.question_no} 题答案裁图`}/>
        <p className="details-line">坐标 {crop.normalized_bbox} · {crop.width} × {crop.height}px</p>
        <button className="button primary" disabled={!!busy} onClick={()=>void task("识别",()=>api.cropRun(crop.id,modelId))}>运行所选模型</button>
        {detail?.runs.filter((run)=>run.crop_id===crop.id).map((run)=><div key={run.id} className="lab-run"><strong>{run.provider} · {run.model}</strong>
          <p>状态 {run.status} · 原文 {run.text??"—"} · 标准化 {run.normalized_candidate??"—"}</p>
          <p>confidence {run.confidence??"—"} · {run.latency_ms} ms · revision {run.model_revision??"—"}</p>
          {run.error&&<p role="alert">{run.error_code}: {run.error}</p>}
          <details><summary>技术详情</summary><pre>{JSON.stringify(run.metadata,null,2)}</pre></details></div>)}</article>)}</div></section>}
  </div>;
}
