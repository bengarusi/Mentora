import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { BoardResponse } from "../types";

const streamBoardNarration = vi.fn();
vi.mock("../api/board", () => ({
  streamBoardNarration: (...a: unknown[]) => streamBoardNarration(...a),
}));

import { useBoardPlayer } from "./useBoardPlayer";

function board(): BoardResponse {
  return {
    id: 1,
    kind: "lesson_intro",
    message_id: 5,
    question_id: null,
    created_at: null,
    spec: {
      title: "Kinds of angles",
      intro: "Let's look at angles.",
      final_answer: null,
      blocks: [
        {
          kind: "steps",
          id: "s1",
          caption: "A corner",
          narration: "Look at this corner.",
          items: [
            { math: "90^\\circ", operation: null, note: null, emphasis: "none", emphasis_tone: "neutral" },
          ],
        },
        {
          kind: "callout",
          id: "c1",
          caption: "A tip",
          narration: "An angle is the opening between two sides.",
          tone: "insight",
          text: "An angle is an opening.",
        },
      ],
    },
  };
}

beforeEach(() => {
  vi.useFakeTimers();
  streamBoardNarration.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useBoardPlayer avatar state", () => {
  it("never shows the tutor speaking before any sound exists", async () => {
    // A narration stream that connects but has not delivered audio yet — the
    // window in which the tutor used to mouth silently at the student.
    streamBoardNarration.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useBoardPlayer(1, board(), { voice: true }));

    act(() => result.current.play());

    expect(result.current.speaking).toBe(false);
    expect(result.current.avatarState).toBe("thinking");
  });

  it("never shows the tutor speaking when voice is off", () => {
    const { result } = renderHook(() => useBoardPlayer(1, board(), { voice: false }));

    act(() => result.current.play());

    // There is no audio at all on this path, so miming would be pure theatre.
    expect(result.current.avatarState).toBe("idle");
    expect(streamBoardNarration).not.toHaveBeenCalled();
  });

  it("still writes the board out when voice is off", () => {
    const { result } = renderHook(() => useBoardPlayer(1, board(), { voice: false }));

    act(() => result.current.play());
    expect(result.current.revealed).toBe(1);
    expect(result.current.caption).toBe("Look at this corner.");

    act(() => vi.advanceTimersByTime(5000));
    expect(result.current.revealed).toBe(2);
  });

  it("goes idle as soon as the board is closed", async () => {
    streamBoardNarration.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useBoardPlayer(1, board(), { voice: true }));
    act(() => result.current.play());

    act(() => result.current.stop());

    expect(result.current.avatarState).toBe("idle");
    expect(result.current.speaking).toBe(false);
  });

  it("shows the whole board when the student skips ahead", () => {
    streamBoardNarration.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useBoardPlayer(1, board(), { voice: true }));
    act(() => result.current.play());

    act(() => result.current.skipToEnd());

    expect(result.current.revealed).toBe(2);
    expect(result.current.avatarState).toBe("idle");
  });

  it("falls back to writing the board out when narration fails", async () => {
    streamBoardNarration.mockRejectedValue(new Error("no tts"));
    const { result } = renderHook(() => useBoardPlayer(1, board(), { voice: true }));

    act(() => result.current.play());
    // Flush the rejection rather than polling: waitFor runs on real time and
    // would fight the fake timers this test needs for the silent fallback.
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(result.current.revealed).toBe(1);
    // Failure means silence, so the tutor must not appear to be talking.
    expect(result.current.speaking).toBe(false);
    act(() => vi.advanceTimersByTime(5000));
    expect(result.current.revealed).toBe(2);
  });

  it("keeps speaking across block boundaries so the narration is not cut off", async () => {
    // Regression: flipping `speaking` off between blocks made useLipSyncVolume
    // tear down, and its source.disconnect() permanently unroutes the audio
    // element — every block after the first went silent.
    let handlers: {
      onChunkStart: (i: number) => void;
      onChunkBytes: (i: number, b: Uint8Array) => void;
      onChunkEnd: (i: number) => void;
      onDone?: () => void;
    };
    streamBoardNarration.mockImplementation((_s, _b, h) => {
      handlers = h;
      return new Promise(() => {});
    });
    globalThis.URL.createObjectURL = vi.fn(() => "blob:chunk");
    globalThis.URL.revokeObjectURL = vi.fn();

    const { result } = renderHook(() => useBoardPlayer(1, board(), { voice: true }));
    act(() => result.current.play());

    const deliver = (index: number) =>
      act(() => {
        handlers.onChunkStart(index);
        handlers.onChunkBytes(index, new Uint8Array([1]));
        handlers.onChunkEnd(index);
      });

    deliver(0);
    const audio = result.current.audioElRef.current!;
    act(() => audio.dispatchEvent(new Event("playing")));
    expect(result.current.speaking).toBe(true);

    // Block 0 finishes and block 1 begins: the tutor is mid-sentence, not done.
    deliver(1);
    act(() => audio.dispatchEvent(new Event("ended")));

    expect(result.current.speaking).toBe(true);
    expect(result.current.revealed).toBe(2);
  });

  it("goes quiet once the narration is genuinely finished", async () => {
    let handlers: {
      onChunkStart: (i: number) => void;
      onChunkBytes: (i: number, b: Uint8Array) => void;
      onChunkEnd: (i: number) => void;
      onDone?: () => void;
    };
    streamBoardNarration.mockImplementation((_s, _b, h) => {
      handlers = h;
      return new Promise(() => {});
    });
    globalThis.URL.createObjectURL = vi.fn(() => "blob:chunk");
    globalThis.URL.revokeObjectURL = vi.fn();

    const { result } = renderHook(() => useBoardPlayer(1, board(), { voice: true }));
    act(() => result.current.play());
    act(() => {
      handlers.onChunkStart(0);
      handlers.onChunkEnd(0);
      handlers.onDone?.();
    });
    const audio = result.current.audioElRef.current!;
    act(() => audio.dispatchEvent(new Event("playing")));

    act(() => audio.dispatchEvent(new Event("ended")));

    expect(result.current.speaking).toBe(false);
    expect(result.current.avatarState).toBe("idle");
  });
});
