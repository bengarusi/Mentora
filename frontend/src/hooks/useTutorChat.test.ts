import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const getSession = vi.fn();
const getMessages = vi.fn();
const sendVoiceTurn = vi.fn();
const speakTutorMessage = vi.fn();
const streamSpeechTurn = vi.fn();
const streamTurn = vi.fn();

vi.mock("../api/sessions", () => ({
  getSession: (...args: unknown[]) => getSession(...args),
  getMessages: (...args: unknown[]) => getMessages(...args),
}));

vi.mock("../api/tutor", () => ({
  sendVoiceTurn: (...args: unknown[]) => sendVoiceTurn(...args),
  speakTutorMessage: (...args: unknown[]) => speakTutorMessage(...args),
  streamSpeechTurn: (...args: unknown[]) => streamSpeechTurn(...args),
  streamTurn: (...args: unknown[]) => streamTurn(...args),
}));

import { useTutorChat } from "./useTutorChat";

beforeEach(() => {
  getSession.mockReset();
  getMessages.mockReset();
  sendVoiceTurn.mockReset();
  speakTutorMessage.mockReset();
  streamSpeechTurn.mockReset();
  streamTurn.mockReset();
  getSession.mockResolvedValue({ id: 17 });
  getMessages.mockResolvedValue([]);
  globalThis.URL.createObjectURL = vi.fn(() => "blob:tutor-audio");
  globalThis.URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useTutorChat Tutor Voice delivery", () => {
  it("speaks a fresh tutor reply returned by a non-chat action", async () => {
    speakTutorMessage.mockResolvedValue("ZmFrZS1tcDM=");
    const play = vi.spyOn(HTMLMediaElement.prototype, "play");
    const { result } = renderHook(() => useTutorChat(17));
    await waitFor(() => expect(result.current.session).not.toBeNull());

    let started = false;
    await act(async () => {
      started = await result.current.speakTutorReply("Welcome to the lesson.");
    });

    expect(started).toBe(true);
    expect(speakTutorMessage).toHaveBeenCalledWith(17, "Welcome to the lesson.");
    expect(play).toHaveBeenCalledOnce();
  });

  it("does not speak a non-chat tutor reply while Tutor Voice is off", async () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play");
    const { result } = renderHook(() => useTutorChat(17));
    await waitFor(() => expect(result.current.session).not.toBeNull());
    act(() => result.current.handleVoicePlaybackToggle(false));

    await act(async () => {
      expect(await result.current.speakTutorReply("Written only.")).toBe(false);
    });

    expect(speakTutorMessage).not.toHaveBeenCalled();
    expect(play).not.toHaveBeenCalled();
  });

  it("speaks an eligible completed reply when the speech stream produced no audio", async () => {
    streamSpeechTurn.mockImplementation(
      async (
        _sessionId: number,
        _content: string,
        _turnId: string,
        handlers: {
          onTextDelta: (delta: string) => void;
          onDone?: () => void;
        }
      ) => {
        handlers.onTextDelta("Let's take the first step together.");
        handlers.onDone?.();
      }
    );
    speakTutorMessage.mockResolvedValue("ZmFrZS1tcDM=");
    const play = vi.spyOn(HTMLMediaElement.prototype, "play");
    const { result } = renderHook(() => useTutorChat(17));
    await waitFor(() => expect(result.current.session).not.toBeNull());

    await act(async () => {
      await result.current.sendMessage("help me");
    });

    expect(speakTutorMessage).toHaveBeenCalledOnce();
    expect(speakTutorMessage).toHaveBeenCalledWith(
      17,
      "Let's take the first step together."
    );
    expect(play).toHaveBeenCalledOnce();
  });

  it("does not replay a reply whose streamed audio was already delivered", async () => {
    streamSpeechTurn.mockImplementation(
      async (
        _sessionId: number,
        _content: string,
        _turnId: string,
        handlers: {
          onTextDelta: (delta: string) => void;
          onAudioChunk: (chunkId: number, bytes: Uint8Array) => void;
          onAudioEnd: (chunkId: number) => void;
          onDone?: () => void;
        }
      ) => {
        handlers.onTextDelta("Use multiplication.");
        handlers.onAudioChunk(1, new Uint8Array([1, 2, 3]));
        handlers.onAudioEnd(1);
        handlers.onDone?.();
      }
    );
    const play = vi.spyOn(HTMLMediaElement.prototype, "play");
    const { result } = renderHook(() => useTutorChat(17));
    await waitFor(() => expect(result.current.session).not.toBeNull());

    await act(async () => {
      await result.current.sendMessage("I don't know");
    });

    expect(play).toHaveBeenCalledOnce();
    expect(speakTutorMessage).not.toHaveBeenCalled();
  });

  it("uses the text-only stream and never requests TTS while Tutor Voice is off", async () => {
    streamTurn.mockImplementation(
      async (
        _sessionId: number,
        _content: string,
        _turnId: string,
        onTextDelta: (delta: string) => void
      ) => onTextDelta("Here is a written hint.")
    );
    const play = vi.spyOn(HTMLMediaElement.prototype, "play");
    const { result } = renderHook(() => useTutorChat(17));
    await waitFor(() => expect(result.current.session).not.toBeNull());
    act(() => result.current.handleVoicePlaybackToggle(false));

    await act(async () => {
      await result.current.sendMessage("help");
    });

    expect(streamTurn).toHaveBeenCalledOnce();
    expect(streamSpeechTurn).not.toHaveBeenCalled();
    expect(speakTutorMessage).not.toHaveBeenCalled();
    expect(play).not.toHaveBeenCalled();
  });
});
