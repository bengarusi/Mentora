import { apiClient } from "./client";
import type {
  HomeworkProgress,
  Session,
  StudyMaterial,
  SupportedFormats,
  TurnResult,
} from "../types";

// Uploads run through extraction (and, for images, a vision call) before they
// return, so they need considerably more than the client's 30s default.
const UPLOAD_TIMEOUT = 120000;

export interface StudyMaterialUploadFields {
  subject?: string;
  topic?: string;
  subtopic?: string;
  title?: string;
}

export async function uploadStudyMaterial(
  file: File,
  fields: StudyMaterialUploadFields = {}
): Promise<StudyMaterial> {
  const form = new FormData();
  form.append("file", file);
  for (const [key, value] of Object.entries(fields)) {
    if (value) form.append(key, value);
  }
  const { data } = await apiClient.post<StudyMaterial>("/materials/", form, {
    timeout: UPLOAD_TIMEOUT,
  });
  return data;
}

export async function listStudyMaterials(params?: {
  subject?: string;
  topic?: string;
}): Promise<StudyMaterial[]> {
  const { data } = await apiClient.get<{ materials: StudyMaterial[] }>(
    "/materials/",
    { params }
  );
  return data.materials;
}

export async function updateMaterial(
  materialId: number,
  fields: StudyMaterialUploadFields
): Promise<StudyMaterial> {
  const { data } = await apiClient.patch<StudyMaterial>(
    `/materials/${materialId}`,
    fields
  );
  return data;
}

export async function reprocessMaterial(
  materialId: number
): Promise<StudyMaterial> {
  const { data } = await apiClient.post<StudyMaterial>(
    `/materials/${materialId}/reprocess`,
    undefined,
    { timeout: UPLOAD_TIMEOUT }
  );
  return data;
}

export async function deleteMaterial(materialId: number): Promise<void> {
  await apiClient.delete(`/materials/${materialId}`);
}

export async function getSupportedFormats(): Promise<SupportedFormats> {
  const { data } = await apiClient.get<SupportedFormats>(
    "/materials/supported-formats"
  );
  return data;
}

// ---- Homework Help ----

export async function createHomeworkSession(
  subject = "math"
): Promise<Session> {
  const { data } = await apiClient.post<Session>("/tutor/homework", { subject });
  return data;
}

/** Homework Help sessions, newest first. These are intentionally absent from
 * the lesson list, so this is how the Files page offers them for resuming. */
export async function listHomeworkSessions(): Promise<Session[]> {
  const { data } = await apiClient.get<Session[]>("/tutor/homework");
  return data;
}

export async function uploadHomework(
  sessionId: number,
  file: File
): Promise<StudyMaterial> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await apiClient.post<StudyMaterial>(
    `/materials/homework/${sessionId}`,
    form,
    { timeout: UPLOAD_TIMEOUT }
  );
  return data;
}

export async function listHomework(
  sessionId: number
): Promise<StudyMaterial[]> {
  const { data } = await apiClient.get<{ materials: StudyMaterial[] }>(
    `/materials/homework/${sessionId}`
  );
  return data.materials;
}

/** Rename a Homework Help session, replacing its default "My homework" title. */
export async function renameHomeworkSession(
  sessionId: number,
  title: string
): Promise<Session> {
  const { data } = await apiClient.patch<Session>(
    `/tutor/${sessionId}/homework/rename`,
    { title }
  );
  return data;
}

/** Delete a homework session with its conversation and its uploaded files. */
export async function deleteHomeworkSession(sessionId: number): Promise<void> {
  await apiClient.delete(`/tutor/${sessionId}/homework`);
}

/** Ask the tutor to read the uploaded homework and open the conversation. */
export async function analyzeHomework(sessionId: number): Promise<TurnResult> {
  const { data } = await apiClient.post<TurnResult>(
    `/tutor/${sessionId}/homework/analyze`,
    undefined,
    { timeout: 90000 } // reads the whole worksheet before replying
  );
  return data;
}

/** How many of the homework's exercises the student has solved so far. */
export async function getHomeworkProgress(
  sessionId: number
): Promise<HomeworkProgress> {
  const { data } = await apiClient.get<HomeworkProgress>(
    `/tutor/${sessionId}/homework/progress`,
    { timeout: 30000 } // may run a fresh summarization if new messages arrived
  );
  return data;
}

/** Open the student's original uploaded file (photo/PDF/Word) in a new tab.
 * Fetched as a blob (not a plain <a href>) because the download must carry
 * the auth token, which only apiClient's interceptor attaches. */
export async function openMaterialFile(materialId: number): Promise<void> {
  const { data, headers } = await apiClient.get(
    `/materials/${materialId}/file`,
    { responseType: "blob" }
  );
  const blob = new Blob([data], {
    type: String(headers["content-type"] ?? "application/octet-stream"),
  });
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener");
  // Give the new tab time to load the object URL before revoking it.
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
