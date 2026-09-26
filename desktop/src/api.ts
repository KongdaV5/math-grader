export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8765";

export type ClassRecord = {
  id: string;
  name: string;
  active: boolean;
};

export type Student = {
  id: string;
  class_id: string;
  student_no: string;
  name: string;
  active: boolean;
};

export type Assignment = {
  id: string;
  class_id: string;
  name: string;
  date: string;
  status: string;
};

export type PageRecord = {
  id: string;
  page_index: number;
  source_ref: string;
  processed_image?: string | null;
  processing_status?: string;
};

export type RecognitionResult = {
  id: string;
  page_id: string;
  text: string | null;
  normalized_candidate: string | null;
  confidence: number | null;
  provider: string;
  model: string;
  latency_ms: number;
  metadata: Record<string, unknown>;
  error: string | null;
};

export type Submission = {
  id: string;
  assignment_id: string;
  student_id: string;
  status: "EMPTY" | "CAPTURING" | "READY" | "QUEUED" | "PROCESSING" | "REVIEW_REQUIRED" | "COMPLETED" | "FAILED";
  page_count: number;
  created_at: string;
  finished_capture_at: string | null;
  completed_at: string | null;
  error: string | null;
  pages: PageRecord[];
  results: RecognitionResult[];
};

export type CaptureAddress = { ip: string; interface: string };
export type CapturePage = {
  id: string;
  page_index: number;
  original_filename: string | null;
  mime_type: string | null;
  byte_size: number;
  uploaded_at: string | null;
};
export type CaptureCurrent = {
  submission_id: string;
  student_id: string;
  student_name: string;
  student_no: string;
  status: string;
  page_count: number;
  pages: CapturePage[];
};
export type CaptureDashboard = {
  session_id: string;
  status: string;
  created_at: string;
  expires_at: string;
  class_name: string;
  assignment_name: string;
  current: CaptureCurrent | null;
  complete: boolean;
  finished_count: number;
  total_students: number;
  last_finished: { name: string; status: string; finished_at: string } | null;
  processing: Array<{ student_name: string; status: string; page_count: number; job_status: string | null }>;
};
export type CaptureSessionSnapshot = {
  status: "ACTIVE" | "ENDED" | "EXPIRED" | "INACTIVE";
  session: { id: string; assignment_id: string; status: string; created_at: string; expires_at: string } | null;
  capture?: CaptureDashboard;
  addresses: CaptureAddress[];
  capture_url: string | null;
  host: string | null;
  port: number | null;
};

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(`${payload.code ? `${payload.code}: ` : ""}${payload.error ?? `Local service returned ${response.status}`}`);
  }
  return payload as T;
}

export const api = {
  health: () => request<{ status: string; service: string; runtime_version: string; python_supported: boolean }>("/health"),
  overview: () => request<Overview>("/api/overview"),
  system: () => request<SystemInfo>("/api/system"),
  openDirectory: (key: string) => request<{path: string}>(`/api/system/open/${key}`, {method: "POST", body: "{}"}),
  models: () => request<ModelStatus[]>("/api/models"),
  modelAction: (id: string, action: string, body: Record<string, unknown> = {}) =>
    request<ModelStatus | Record<string, unknown>>(`/api/models/${id}/${action}`, {method: "POST", body: JSON.stringify(body)}),
  modelHealth: (id: string) => request<ProviderHealth>(`/api/models/${id}/health`),
  templateGroups: () => request<TemplateGroup[]>("/api/templates/groups"),
  createTemplateGroup: (body: Record<string, unknown>) => request<TemplateGroup>("/api/templates/groups", {method: "POST", body: JSON.stringify(body)}),
  templatePages: (groupId: string) => request<PageTemplate[]>(`/api/templates/groups/${groupId}/pages`),
  createTemplatePage: (groupId: string, body: Record<string, unknown>) =>
    request<PageTemplate>(`/api/templates/groups/${groupId}/pages`, {method: "POST", body: JSON.stringify(body)}),
  templatePage: (pageId: string) => request<PageTemplate>(`/api/templates/pages/${pageId}`),
  importTemplateReference: (pageId: string, filename: string, image_base64: string) =>
    request<PageTemplate>(`/api/templates/pages/${pageId}/reference`, {method: "POST", body: JSON.stringify({filename, image_base64})}),
  createTemplateQuestion: (pageId: string, body: Record<string, unknown>) =>
    request<TemplateQuestion>(`/api/templates/pages/${pageId}/questions`, {method: "POST", body: JSON.stringify(body)}),
  createAnswerRegion: (questionId: string, body: Record<string, unknown>) =>
    request<AnswerRegion>(`/api/templates/questions/${questionId}/regions`, {method: "POST", body: JSON.stringify(body)}),
  updateTemplateQuestion: (id: string, body: Record<string, unknown>) => request<TemplateQuestion>(`/api/templates/questions/${id}`, {method:"PATCH",body:JSON.stringify(body)}),
  deleteTemplateQuestion: (id: string) => request<{deleted:string}>(`/api/templates/questions/${id}`, {method:"DELETE"}),
  updateAnswerRegion: (id: string, body: Record<string, unknown>) => request<AnswerRegion>(`/api/templates/regions/${id}`, {method:"PATCH",body:JSON.stringify(body)}),
  deleteAnswerRegion: (id: string) => request<{deleted:string}>(`/api/templates/regions/${id}`, {method:"DELETE"}),
  labImport: (filename:string,image_base64:string) => request<PageRecord>("/api/lab/import", {method:"POST",body:JSON.stringify({filename,image_base64})}),
  pageProcess: (id:string) => request<Record<string,unknown>>(`/api/pages/${id}/process`,{method:"POST",body:"{}"}),
  pageDetail: (id:string) => request<LabDetail>(`/api/pages/${id}/detail`),
  pageMatch: (id:string) => request<Array<{template_id:string;name:string;page_number:number;score:number}>>(`/api/pages/${id}/match`),
  pageBind: (id:string,template_id:string) => request<Record<string,unknown>>(`/api/pages/${id}/bind`,{method:"POST",body:JSON.stringify({template_id})}),
  pageCrops: (id:string) => request<AnswerCrop[]>(`/api/pages/${id}/crops`,{method:"POST",body:"{}"}),
  cropRun: (id:string,model_id?:string) => request<{id:string;status:string;model:string}>(`/api/crops/${id}/runs`,{method:"POST",body:JSON.stringify({model_id})}),
  pagePredictions: (id:string) => request<Array<Record<string,unknown>>>(`/api/pages/${id}/predictions`),
  classes: () => request<ClassRecord[]>("/api/classes"),
  createClass: (name: string) => request<ClassRecord>("/api/classes", { method: "POST", body: JSON.stringify({ name }) }),
  students: (classId: string) => request<Student[]>(`/api/classes/${classId}/students`),
  createStudent: (classId: string, student_no: string, name: string) =>
    request<Student>(`/api/classes/${classId}/students`, { method: "POST", body: JSON.stringify({ student_no, name }) }),
  assignments: (classId: string) => request<Assignment[]>(`/api/classes/${classId}/assignments`),
  submissions: (assignmentId: string) => request<Submission[]>(`/api/assignments/${assignmentId}/submissions`),
  createAssignment: (classId: string, name: string, date: string) =>
    request<Assignment>(`/api/classes/${classId}/assignments`, { method: "POST", body: JSON.stringify({ name, date }) }),
  createSubmission: (assignment_id: string, student_id: string) =>
    request<Submission>("/api/submissions", { method: "POST", body: JSON.stringify({ assignment_id, student_id }) }),
  startSubmission: (id: string) => request<Submission>(`/api/submissions/${id}/start`, { method: "POST", body: "{}" }),
  addPlaceholderPage: (id: string) =>
    request<{ page: PageRecord; submission: Submission }>(`/api/submissions/${id}/pages`, { method: "POST", body: JSON.stringify({ placeholder: true }) }),
  addImagePage: (id: string, filename: string, image_base64: string) =>
    request<{ page: PageRecord; submission: Submission }>(`/api/submissions/${id}/pages`, { method: "POST", body: JSON.stringify({ filename, image_base64 }) }),
  finishSubmission: (id: string) => request<Submission>(`/api/submissions/${id}/finish`, { method: "POST", body: "{}" }),
  submission: (id: string) => request<Submission>(`/api/submissions/${id}`),
  captureSession: () => request<CaptureSessionSnapshot>("/api/capture/session"),
  startCaptureSession: (assignment_id: string, host: string) =>
    request<CaptureSessionSnapshot>("/api/capture/session/start", { method: "POST", body: JSON.stringify({ assignment_id, host }) }),
  endCaptureSession: () =>
    request<CaptureSessionSnapshot>("/api/capture/session/end", { method: "POST", body: "{}" }),
};

export type Overview = {
  counts: { classes: number; students: number; queued: number; processing: number };
  recent_assignments: Array<Assignment & { created_at: string }>;
  recent_submissions: Submission[];
};
export type ModelEntry = {
  id: string; display_name: string; category: "ocr" | "formula" | "vision"; description: string;
  source: string; source_repo: string[]; upstream_repo: string | null; runtime: string;
  approximate_size_bytes: number; license: string; recommended: string; metadata: Record<string, string>;
};
export type ModelStatus = { model: ModelEntry; state: string; path: string | null;
  progress: {completed_files: number; total_files: number | null; current_file: string | null} | null;
  error: {code: string; message: string} | null; };
export type ProviderHealth = { model_id: string; state: string; lifecycle: string; runtime_available: boolean; error?: string };
export type SystemInfo = { paths: Record<string, string>; runtime_version: string; python_supported: boolean;
  dependencies: Record<string,boolean>;
  recognition_config: {schema_version: number; routes: string[]; model_routes: Record<string, unknown>} };
export type TemplateGroup = {id: string; name: string; grade: string; semester: string; book_name: string;
  publisher: string | null; version: number; created_at: string; updated_at: string};
export type AnswerRegion = {id: string; question_id: string; region_index: number; x: number; y: number;
  width: number; height: number; coordinate_space: "normalized"};
export type TemplateQuestion = {id: string; page_template_id: string; question_no: string; answer_type: string;
  correct_answer: string | null; accepted_answers: string[]; score: number; knowledge_tag: string | null;
  metadata: Record<string,unknown>; regions: AnswerRegion[]};
export type PageTemplate = {id: string; template_group_id: string; page_number: number; name: string;
  reference_image: string | null; fingerprint: string | null; version: number; active: boolean;
  questions: TemplateQuestion[]};

export function fileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(`无法读取图片：${file.name}`));
    reader.onload = () => {
      const dataUrl = String(reader.result ?? "");
      const comma = dataUrl.indexOf(",");
      if (comma < 0) {
        reject(new Error(`图片格式无效：${file.name}`));
        return;
      }
      resolve(dataUrl.slice(comma + 1));
    };
    reader.readAsDataURL(file);
  });
}

export type AnswerCrop = {binding_id:string;id:string;question_no:string;answer_type:string;region_index:number;crop_path:string;
  normalized_bbox:string;pixel_bbox:string;width:number;height:number;template_version:number};
export type LabRun = {id:string;crop_id:string;provider:string;model:string;model_revision:string|null;
  text:string|null;normalized_candidate:string|null;confidence:number|null;latency_ms:number;
  status:string;error_code:string|null;error:string|null;metadata:Record<string,unknown>};
export type LabDetail = {page:PageRecord & {processing_status:string;processing_warning:string|null;
  processing_error:string|null;template_binding_id:string|null};binding:{id:string;page_template_id:string;template_version:number;snapshot:PageTemplate}|null;
  crops:AnswerCrop[];runs:LabRun[]};
export const imageUrl = (kind:"reference"|"processed"|"crop",id:string) => `${API_BASE}/api/images/${kind}/${id}`;
