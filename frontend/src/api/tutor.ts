import { apiClient } from "./client";
import type {
  GradedAnswer,
  PhaseResult,
  Question,
  SessionSummary,
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

export async function startAssessment(sessionId: number): Promise<Question[]> {
  const { data } = await apiClient.post<Question[]>(
    `/tutor/${sessionId}/assessment/start`
  );
  return data;
}

export async function submitAnswer(
  sessionId: number,
  questionId: number,
  answer: string
): Promise<GradedAnswer> {
  const { data } = await apiClient.post<GradedAnswer>(
    `/tutor/${sessionId}/assessment/answer`,
    { question_id: questionId, answer }
  );
  return data;
}

export async function getSummary(sessionId: number): Promise<SessionSummary> {
  const { data } = await apiClient.get<SessionSummary>(
    `/tutor/${sessionId}/summary`
  );
  return data;
}
