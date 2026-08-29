import { apiClient, getToken } from "./client";
import type {
  DifficultyLevel,
  LessonSummaryResponse,
  PhaseResult,
  PracticeAnswerItem,
  PracticeStartResult,
  PracticeSubmitResult,
  PracticeSummary,
  TurnResult,
  VoiceTurnResult,
  StreamEvent,
} from "../types";

export async function setLessonDifficulty(
  sessionId: number,
  level: DifficultyLevel
): Promise<TurnResult> {
  const { data } = await apiClient.post<TurnResult>(
    `/tutor/${sessionId}/difficulty`,
    { level }
  );
  return data;
}

export async function sendTurn(
  sessionId: number,
  content: string,
  turnId: string
): Promise<TurnResult> {
  const { data } = await apiClient.post<TurnResult>(
    `/tutor/${sessionId}/turn`,
    { content, turn_id: turnId }
  );
  return data;
}

// Stream the tutor reply token-by-token. Uses fetch (not axios) because axios
// can't expose a readable stream in the browser. onToken fires for each chunk.
export async function streamTurn(
  sessionId: number,
  content: string,
  turnId: string,
  onToken: (delta: string) => void,
  onToolEvent?: (event: Extract<StreamEvent, { type: "tool_start" | "tool_end" }>) => void
): Promise<void> {
  const token = getToken();
  const response = await fetch(`/api/tutor/${sessionId}/turn/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/x-ndjson",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ content, turn_id: turnId }),
  });
  if (!response.ok || !response.body) {
    throw new Error(`Stream failed: ${response.status}`);
  }
  await readEventStream(response, (event) => {
    if (event.type === "text_delta") onToken(event.data);
    if (event.type === "tool_start" || event.type === "tool_end") onToolEvent?.(event);
  });
}

// Handlers for the low-latency speech-stream turn (NDJSON: text + audio events).
export interface SpeechStreamHandlers {
  onTextDelta: (delta: string) => void;
  onAudioStart?: (chunkId: number) => void;
  onAudioChunk: (chunkId: number, bytes: Uint8Array) => void;
  onAudioEnd: (chunkId: number) => void;
  onDone?: () => void;
  onError?: (message: string) => void;
  onToolStart?: (toolName: string) => void;
  onToolEnd?: (toolName: string, status: string) => void;
}

function base64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

async function readEventStream(
  response: Response,
  onEvent: (event: StreamEvent) => void
): Promise<void> {
  if (!response.body) return;
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
      if (line) onEvent(JSON.parse(line) as StreamEvent);
    }
  }
}

// Stream tutor text + per-chunk TTS audio over a single NDJSON response. Uses
// fetch (not axios) so the response body can be read incrementally. Pass an
// AbortSignal to support barge-in (cancelling the in-flight turn).
export async function streamSpeechTurn(
  sessionId: number,
  content: string,
  turnId: string,
  handlers: SpeechStreamHandlers,
  signal?: AbortSignal
): Promise<void> {
  const token = getToken();
  const response = await fetch(`/api/tutor/${sessionId}/turn/speech-stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ content, turn_id: turnId }),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`Speech stream failed: ${response.status}`);
  }
  await readEventStream(response, (evt) => {
      switch (evt.type) {
        case "text_delta":
          handlers.onTextDelta(evt.data);
          break;
        case "audio_start":
          handlers.onAudioStart?.(evt.chunk_id);
          break;
        case "audio_delta":
          handlers.onAudioChunk(evt.chunk_id, base64ToBytes(evt.data));
          break;
        case "audio_end":
          handlers.onAudioEnd(evt.chunk_id);
          break;
        case "tool_start":
          handlers.onToolStart?.(evt.tool_name);
          break;
        case "tool_end":
          handlers.onToolEnd?.(evt.tool_name, evt.status ?? "complete");
          break;
        case "done":
          handlers.onDone?.();
          break;
        case "error":
          handlers.onError?.(evt.message);
          break;
      }
  });
}

export async function speakTutorMessage(
  sessionId: number,
  text: string
): Promise<string | null> {
  const { data } = await apiClient.post<{ audio_base64: string | null }>(
    `/tutor/${sessionId}/tts`,
    { text },
    { timeout: 30000 }
  );
  return data.audio_base64;
}

// Map a MediaRecorder MIME type ("audio/mp4;codecs=..." etc.) to a bare file
// extension OpenAI's transcription endpoint accepts. Falls back to webm.
function extensionForMime(mime: string): string {
  const base = (mime || "").split(";")[0].trim().toLowerCase();
  const map: Record<string, string> = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "mp4",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
  };
  return map[base] ?? "webm";
}

// Send recorded audio to the voice endpoint. The browser sets the multipart
// boundary automatically; apiClient's interceptor adds the auth token.
export async function sendVoiceTurn(
  sessionId: number,
  audioBlob: Blob,
  turnId: string
): Promise<VoiceTurnResult> {
  const form = new FormData();
  // OpenAI infers the audio codec from the filename extension, so the name
  // must match what the browser actually recorded (Safari records mp4, not webm).
  form.append("file", audioBlob, `recording.${extensionForMime(audioBlob.type)}`);
  form.append("turn_id", turnId);
  const { data } = await apiClient.post<VoiceTurnResult>(
    `/tutor/${sessionId}/voice-turn`,
    form,
    { timeout: 60000 } // STT + tutor reply + TTS chained — needs more than the 30s default
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
