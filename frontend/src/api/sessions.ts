import { apiClient } from "./client";
import type { Message, Session, Subject } from "../types";

export interface CreateSessionPayload {
  subject: Subject;
  topic: string;
  subtopic: string;
  goal_text: string;
}

export async function createSession(
  payload: CreateSessionPayload
): Promise<Session> {
  const { data } = await apiClient.post<Session>("/sessions/", payload);
  return data;
}

export async function listSessions(): Promise<Session[]> {
  const { data } = await apiClient.get<Session[]>("/sessions/");
  return data;
}

export async function getSession(sessionId: number): Promise<Session> {
  const { data } = await apiClient.get<Session>(`/sessions/${sessionId}`);
  return data;
}

export async function endSession(sessionId: number): Promise<Session> {
  const { data } = await apiClient.post<Session>(`/sessions/${sessionId}/end`);
  return data;
}

export async function getMessages(sessionId: number): Promise<Message[]> {
  const { data } = await apiClient.get<Message[]>(
    `/sessions/${sessionId}/messages`
  );
  return data;
}
