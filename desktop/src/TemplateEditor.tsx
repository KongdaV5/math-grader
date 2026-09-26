import {screenToNormalized} from "./coordinates";
import {useEffect, useRef, useState, type PointerEvent} from "react";
import {api,imageUrl,type AnswerRegion,type PageTemplate,type TemplateQuestion} from "./api";

const answerTypes = ["integer","decimal","choice","boolean","comparison_symbol","fraction","formula","short_text","sequence","multi_blank"] as const;
type Box = {x:number;y:number;width:number;height:number};
const initialForm = {question_no:"",answer_type:"integer",correct_answer:"",accepted_answers:"",score:"1",knowledge_tag:"",metadata:"{}"};

export function TemplateEditor({detail,reload}:{detail:PageTemplate;reload:()=>void}) {
  const [questionId,setQuestionId]=useState("");
  const [regionId,setRegionId]=useState("");
  const [form,setForm]=useState(initialForm);
  const [box,setBox]=useState<Box>({x:0,y:0,width:.2,height:.1});
  const [drawing,setDrawing]=useState<{x:number;y:number}|null>(null);
  const [draft,setDraft]=useState<Box|null>(null);
  const [redraw,setRedraw]=useState(false);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  const imageRef=useRef<HTMLImageElement>(null);
  const question=detail.questions.find((item)=>item.id===questionId);
  const region=question?.regions.find((item)=>item.id===regionId);
  useEffect(()=>{setQuestionId((id)=>detail.questions.some((q)=>q.id===id)?id:detail.questions[0]?.id??"");},[detail]);
  useEffect(()=>{if (!question) {setForm(initialForm);return;}setForm({question_no:question.question_no,answer_type:question.answer_type,
    correct_answer:question.correct_answer??"",accepted_answers:question.accepted_answers.join("、"),score:String(question.score),
    knowledge_tag:question.knowledge_tag??"",metadata:JSON.stringify(question.metadata??{})});},[questionId,detail]);
  useEffect(()=>{if(region)setBox({x:region.x,y:region.y,width:region.width,height:region.height});},[regionId,detail]);
  const point=(event:PointerEvent<HTMLDivElement>)=>{
    const rect=imageRef.current?.getBoundingClientRect();if(!rect)return null;
    return screenToNormalized({x:event.clientX,y:event.clientY},rect,
      {width:imageRef.current?.naturalWidth??0,height:imageRef.current?.naturalHeight??0});
  };
  async function action(work:()=>Promise<unknown>){setBusy(true);setError("");try{await work();reload();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  async function saveQuestion(){await action(async()=>{
    const payload={question_no:form.question_no,answer_type:form.answer_type,correct_answer:form.correct_answer||null,
      accepted_answers:form.accepted_answers.split(/[、,]/).map((x)=>x.trim()).filter(Boolean),
      score:Number(form.score),knowledge_tag:form.knowledge_tag||null,metadata:JSON.parse(form.metadata)};
    const saved:TemplateQuestion=question ? await api.updateTemplateQuestion(question.id,payload):await api.createTemplateQuestion(detail.id,payload);
    setQuestionId(saved.id);
  });}
  async function saveRegion(rectangle:Box,target=regionId){
    if (!question) {setError("先选择一道题目");return;}
    if (rectangle.width<=.002||rectangle.height<=.002) {setError("区域太小，请重新绘制");return;}
    await action(async()=>{
      const saved:AnswerRegion=target ? await api.updateAnswerRegion(target,rectangle):await api.createAnswerRegion(question.id,
        {...rectangle,region_index:Math.max(0,...question.regions.map((item)=>item.region_index))+1});
      setRegionId(saved.id);setRedraw(false);
    });
  }
  function finish(event:PointerEvent<HTMLDivElement>){
    if(!drawing)return;const p=point(event);setDrawing(null);setDraft(null);if(!p)return;
    const next={x:Math.min(drawing.x,p.x),y:Math.min(drawing.y,p.y),width:Math.abs(p.x-drawing.x),height:Math.abs(p.y-drawing.y)};
    void saveRegion(next,redraw?regionId:"");
  }
  return <div className="template-editor">
    {error&&<p className="message error" role="alert">{error}</p>}
    <div className="template-layout">
      <div><h3>参考页与答案区域</h3>{detail.reference_image?<div className="template-canvas"
        onPointerDown={(event)=>{if(!question||busy)return;const p=point(event);if(p){event.currentTarget.setPointerCapture(event.pointerId);setDrawing(p);setDraft({x:p.x,y:p.y,width:0,height:0});}}}
        onPointerMove={(event)=>{if(!drawing)return;const p=point(event);if(p)setDraft({x:Math.min(drawing.x,p.x),y:Math.min(drawing.y,p.y),width:Math.abs(p.x-drawing.x),height:Math.abs(p.y-drawing.y)});}}
        onPointerUp={finish} onPointerCancel={()=>{setDrawing(null);setDraft(null);}}>
        <img ref={imageRef} src={imageUrl("reference",detail.id)} alt={`第 ${detail.page_number} 页参考图`} draggable={false}/>
        {detail.questions.flatMap((q)=>q.regions.map((r)=><button type="button" key={r.id}
          className={`region-overlay ${r.id===regionId?"selected":""}`} style={{left:`${r.x*100}%`,top:`${r.y*100}%`,width:`${r.width*100}%`,height:`${r.height*100}%`}}
          aria-label={`第 ${q.question_no} 题区域 ${r.region_index}`} onPointerDown={(event)=>{event.stopPropagation();setQuestionId(q.id);setRegionId(r.id);setRedraw(false);}}>{q.question_no}.{r.region_index}</button>))}
        {draft&&<div className="region-draft" style={{left:`${draft.x*100}%`,top:`${draft.y*100}%`,width:`${draft.width*100}%`,height:`${draft.height*100}%`}}/>}
      </div>:<p>先导入参考页图片，图片将保存在应用管理目录。</p>}
      <p className="details-line">选择题目后在图片上拖出答案框。当前模板版本 {detail.version}；旧绑定保留独立快照。</p></div>
      <div className="template-controls"><h3>题目</h3>
        <label className="field-label" htmlFor="edit-question">当前题目</label><select id="edit-question" value={questionId} onChange={(e)=>{setQuestionId(e.target.value);setRegionId("");}}><option value="">新建题目</option>{detail.questions.map((q)=><option key={q.id} value={q.id}>第 {q.question_no} 题</option>)}</select>
        <div className="stack-form"><input aria-label="题号" placeholder="题号" value={form.question_no} onChange={(e)=>setForm({...form,question_no:e.target.value})}/>
        <select aria-label="答案类型" value={form.answer_type} onChange={(e)=>setForm({...form,answer_type:e.target.value})}>{answerTypes.map((type)=><option key={type} value={type}>{type}</option>)}</select>
        <input aria-label="正确答案" placeholder="正确答案" value={form.correct_answer} onChange={(e)=>setForm({...form,correct_answer:e.target.value})}/>
        <input aria-label="可接受答案" placeholder="可接受答案，用逗号分隔" value={form.accepted_answers} onChange={(e)=>setForm({...form,accepted_answers:e.target.value})}/>
        <input aria-label="分值" type="number" min="0" step="0.5" value={form.score} onChange={(e)=>setForm({...form,score:e.target.value})}/>
        <input aria-label="知识点" placeholder="知识点" value={form.knowledge_tag} onChange={(e)=>setForm({...form,knowledge_tag:e.target.value})}/>
        <input aria-label="元数据 JSON" placeholder="元数据 JSON" value={form.metadata} onChange={(e)=>setForm({...form,metadata:e.target.value})}/>
        <div className="inline-controls"><button className="button primary" disabled={busy||!form.question_no} onClick={()=>void saveQuestion()}>{question?"保存题目":"创建题目"}</button>
        {question&&<button className="button destructive" disabled={busy} onClick={()=>{if(window.confirm(`删除第 ${question.question_no} 题及其区域？`))void action(()=>api.deleteTemplateQuestion(question.id));}}>删除题目</button>}</div></div>
        <h3>答案区域</h3>{question?<><select aria-label="当前区域" value={regionId} onChange={(e)=>setRegionId(e.target.value)}><option value="">新建区域</option>{question.regions.map((r)=><option key={r.id} value={r.id}>区域 {r.region_index}</option>)}</select>
        <div className="bbox-inputs">{(["x","y","width","height"] as const).map((key)=><label key={key}>{key}<input type="number" min="0" max="1" step="0.001" value={box[key]} onChange={(e)=>setBox({...box,[key]:Number(e.target.value)})}/></label>)}</div>
        <div className="inline-controls"><button className="button secondary" disabled={busy} onClick={()=>void saveRegion(box)}>保存坐标</button>
          {region&&<><button className="button secondary" onClick={()=>setRedraw(true)}>重画区域</button><button className="button destructive" onClick={()=>void action(()=>api.deleteAnswerRegion(region.id))}>删除区域</button></>}</div>
        {redraw&&<p className="details-line">在图片上拖出新区域以替换当前框。</p>}</>:<p className="details-line">先创建题目。</p>}</div>
    </div>
  </div>;
}
