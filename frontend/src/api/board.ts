import { apiClient, getToken } from "./client";
import type { BoardListResponse, BoardResponse } from "../types";

/** Every board in this session, plus whether the feature is available at all.
 * Answers 200 even when the flag is off, so the caller can tell "disabled" from
 * "broken". */
export async function listBoards(sessionId: number): Promise<BoardListResponse> {
  const { data } = await apiClient.get<BoardListResponse>(`/tutor/${sessionId}/boards`);
  return data;
}

/** Teach on the board. With no focus this is the lesson opening, generated once
 * and replayable after; with a focus it is a fresh board about whatever the
 * student is stuck on. */
export async function openLessonBoard(
  sessionId: number,
  focus?: string
): Promise<BoardResponse> {
  const { data } = await apiClient.post<BoardResponse>(
    `/tutor/${sessionId}/boards/lesson`,
    focus ? { focus } : {},
    { timeout: 90000 } // a structured generation needs more than the 30s default
  );
  return data;
}

/** Explain a practice question the student has already been graded on. 409s
 * while the question is unanswered. */
export async function reviewQuestionBoard(
  sessionId: number,
  questionId: number
): Promise<BoardResponse> {
  const { data } = await apiClient.post<BoardResponse>(
    `/tutor/${sessionId}/practice/questions/${questionId}/board`,
    undefined,
    { timeout: 90000 }
  );
  return data;
}

/** Fetch a board's full spec — how replaying works after a page refresh. */
export async function getBoard(
  sessionId: number,
  boardId: number
): Promise<BoardResponse> {
  const { data } = await apiClient.get<BoardResponse>(
    `/tutor/${sessionId}/boards/${boardId}`
  );
  return data;
}

export interface NarrationHandlers {
  onChunkStart: (blockIndex: number) => void;
  onChunkBytes: (blockIndex: number, bytes: Uint8Array) => void;
  onChunkEnd: (blockIndex: number) => void;
  onDone?: () => void;
}

function base64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

/**
 * Stream the board's narration as one audio chunk per block.
 *
 * Uses fetch rather than axios because the body has to be read incrementally,
 * matching streamSpeechTurn. chunk_id is the block index, so the player can
 * reveal block N exactly when its audio begins.
 */
export async function streamBoardNarration(
  sessionId: number,
  boardId: number,
  handlers: NarrationHandlers,
  signal?: AbortSignal
): Promise<void> {
  const token = getToken();
  const response = await fetch(`/api/tutor/${sessionId}/boards/${boardId}/narration`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`Narration stream failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl: number;
    while ((nl = buffer.indexOf("\n")) !== -1) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (!line) continue;
      const evt = JSON.parse(line);
      if (evt.type === "audio_start") handlers.onChunkStart(evt.chunk_id);
      else if (evt.type === "audio_delta")
        handlers.onChunkBytes(evt.chunk_id, base64ToBytes(evt.data));
      else if (evt.type === "audio_end") handlers.onChunkEnd(evt.chunk_id);
      else if (evt.type === "done") handlers.onDone?.();
    }
  }
}
