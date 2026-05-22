import { apiClient } from "./client";
import type {
  LessonSummaryResponse,
  PhaseResult,
  PracticeAnswerItem,
  PracticeStartResult,
  PracticeSubmitResult,
  PracticeSummary,
  TurnResult,
} from "../types";

export async function sendTurn(
  sessionId: number,
  content: string
): Promise<TurnResult> {
  const { data } = await apiClient.post<TurnResult>(
    `/tutor/${sessionId}/turn`,
    { content }
  );
  return data;
}

export async function advancePhase(sessionId: number): Promise<PhaseResult> {
  const { data } = await apiClient.post<PhaseResult>(
    `/tutor/${sessionId}/advance`
  );
  return data;
}

// ---- Practice flow ----

export async function startPractice(
  sessionId: number
): Promise<PracticeStartResult> {
  const { data } = await apiClient.post<PracticeStartResult>(
    `/tutor/${sessionId}/practice/start`
  );
  return data;
}

export async function submitPracticeSet(
  sessionId: number,
  answers: PracticeAnswerItem[]
): Promise<PracticeSubmitResult> {
  const { data } = await apiClient.post<PracticeSubmitResult>(
    `/tutor/${sessionId}/practice/submit`,
    { answers }
  );
  return data;
}

export async function nextPracticeSet(
  sessionId: number
): Promise<PracticeStartResult> {
  const { data } = await apiClient.post<PracticeStartResult>(
    `/tutor/${sessionId}/practice/next`
  );
  return data;
}

export async function finishPractice(sessionId: number): Promise<PhaseResult> {
  const { data } = await apiClient.post<PhaseResult>(
    `/tutor/${sessionId}/practice/finish`
  );
  return data;
}

export async function getPracticeSummary(
  sessionId: number
): Promise<PracticeSummary> {
  const { data } = await apiClient.get<PracticeSummary>(
    `/tutor/${sessionId}/practice/summary`
  );
  return data;
}

export async function getLessonSummary(
  sessionId: number
): Promise<LessonSummaryResponse> {
  const { data } = await apiClient.get<LessonSummaryResponse>(
    `/tutor/${sessionId}/lesson-summary`
  );
  return data;
}
