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
    throw new Error(payload.error ?? `Local service returned ${response.status}`);
  }
  return payload as T;
}

export const api = {
  health: () => request<{ status: string; service: string }>("/health"),
  classes: () => request<ClassRecord[]>("/api/classes"),
  createClass: (name: string) => request<ClassRecord>("/api/classes", { method: "POST", body: JSON.stringify({ name }) }),
  students: (classId: string) => request<Student[]>(`/api/classes/${classId}/students`),
  createStudent: (classId: string, student_no: string, name: string) =>
    request<Student>(`/api/classes/${classId}/students`, { method: "POST", body: JSON.stringify({ student_no, name }) }),
  assignments: (classId: string) => request<Assignment[]>(`/api/classes/${classId}/assignments`),
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
