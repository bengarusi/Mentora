import { useCallback, useEffect, useRef, useState } from "react";
import { streamBoardNarration } from "../api/board";
import type { BoardResponse } from "../types";

/** Roughly how long a spoken word takes, used only when there is no audio to
 * pace against. Slow enough for a child to read the caption. */
const MS_PER_WORD = 380;
const MIN_BLOCK_MS = 2200;

function silentDurationFor(narration: string): number {
  return Math.max(MIN_BLOCK_MS, narration.split(/\s+/).length * MS_PER_WORD);
}

/**
 * Plays a board the way a teacher works through one: blocks appear one at a
 * time, each as the tutor starts talking about it.
 *
 * With voice on, pacing comes from the audio itself — block N is revealed when
 * chunk N begins playing, so the writing lands with the words. With voice off
 * the same sequence runs on a timer derived from the narration length, so the
 * experience is the same shape either way.
 *
 * Audio is reassembled per block and released strictly in order, the same
 * approach useTutorChat uses for chunked speech: a block that arrives early is
 * buffered, never played ahead of its turn.
 */
export function useBoardPlayer(
  sessionId: number,
  board: BoardResponse | null,
  { voice }: { voice: boolean }
) {
  const blocks = board?.spec.blocks ?? [];
  const total = blocks.length;

  const [revealed, setRevealed] = useState(0);
  const [caption, setCaption] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  // Whether the tutor is audibly talking. Turned on by the first real audio and
  // then held for the whole narration.
  //
  // It must NOT flap between blocks. useLipSyncVolume tears down on its `active`
  // dependency, and its cleanup calls source.disconnect() — but
  // createMediaElementSource permanently reroutes the element through the audio
  // graph, and calling it twice on the same element throws. So a false/true
  // round trip mid-narration disconnects the audio and never reconnects it,
  // silencing every block after the first.
  const [speaking, setSpeaking] = useState(false);

  const audioElRef = useRef<HTMLAudioElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const genRef = useRef(0);
  const timersRef = useRef<number[]>([]);
  // Per-block audio, assembled from deltas then released in order.
  const bytesRef = useRef<Map<number, Uint8Array[]>>(new Map());
  const readyRef = useRef<Map<number, string>>(new Map());
  const queueRef = useRef<{ index: number; url: string }[]>([]);
  const nextRef = useRef(0);
  const isPlayingRef = useRef(false);
  const streamDoneRef = useRef(false);
  const playNextRef = useRef<() => void>(() => {});
  const narrationsRef = useRef<string[]>([]);
  narrationsRef.current = blocks.map((block) => block.narration);

  const clearTimers = useCallback(() => {
    timersRef.current.forEach((id) => window.clearTimeout(id));
    timersRef.current = [];
  }, []);

  const releaseAudio = useCallback(() => {
    queueRef.current.forEach((item) => URL.revokeObjectURL(item.url));
    queueRef.current = [];
    readyRef.current.forEach((url) => URL.revokeObjectURL(url));
    readyRef.current.clear();
    bytesRef.current.clear();
    nextRef.current = 0;
    isPlayingRef.current = false;
  }, []);

  const stop = useCallback(() => {
    // Bump the generation first so every in-flight callback no-ops.
    genRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    clearTimers();
    if (audioElRef.current) {
      audioElRef.current.onended = null;
      audioElRef.current.onplaying = null;
      audioElRef.current.pause();
    }
    releaseAudio();
    setPlaying(false);
    setSpeaking(false);
  }, [clearTimers, releaseAudio]);

  // Tear everything down when the board changes or the player unmounts, so a
  // previous board's audio can never talk over a new one.
  useEffect(() => stop, [stop, board?.id]);

  const revealBlock = useCallback((index: number) => {
    setRevealed((current) => Math.max(current, index + 1));
    setCaption(narrationsRef.current[index] ?? null);
  }, []);

  const playNext = useCallback(() => {
    const audio = audioElRef.current;
    const item = queueRef.current.shift();
    if (!audio || !item) {
      isPlayingRef.current = false;
      // Out of queued audio. If more is still being synthesised the tutor is
      // only pausing for breath, so stay "speaking"; only a genuinely finished
      // narration goes quiet.
      if (streamDoneRef.current && readyRef.current.size === 0) {
        setPlaying(false);
        setSpeaking(false);
      }
      return;
    }
    const gen = genRef.current;
    isPlayingRef.current = true;
    audio.src = item.url;
    // Reveal as the audio for this block begins — this is the sync point that
    // makes the writing feel like it is being narrated.
    revealBlock(item.index);
    // The element itself is the authority on whether sound is coming out; a
    // resolved play() promise is not the same as audible output. Deliberately no
    // onpause handler: swapping src between blocks fires pause, which would flap
    // `speaking` and break the audio route.
    audio.onplaying = () => {
      if (gen === genRef.current) setSpeaking(true);
    };
    audio.onended = () => {
      if (gen !== genRef.current) return;
      URL.revokeObjectURL(item.url);
      playNextRef.current();
    };
    audio.play().catch(() => {
      if (gen !== genRef.current) return;
      // Autoplay blocked or playback failed. The board must still play out, so
      // fall back to timed reveal from wherever we got to.
      setSpeaking(false);
      releaseAudio();
      runSilentFrom(item.index + 1, gen);
    });
  }, [revealBlock, releaseAudio]);
  playNextRef.current = playNext;

  /** Reveal the remaining blocks on a timer. Used when voice is off, and as the
   * fallback whenever audio cannot play. */
  const runSilentFrom = useCallback(
    (startIndex: number, gen: number) => {
      let delay = 0;
      for (let index = startIndex; index < narrationsRef.current.length; index++) {
        const at = index;
        delay += silentDurationFor(narrationsRef.current[at]);
        timersRef.current.push(
          window.setTimeout(() => {
            if (gen !== genRef.current) return;
            revealBlock(at);
            if (at === narrationsRef.current.length - 1) setPlaying(false);
          }, delay - silentDurationFor(narrationsRef.current[at]))
        );
      }
      if (startIndex >= narrationsRef.current.length) setPlaying(false);
    },
    [revealBlock]
  );

  const play = useCallback(() => {
    if (!board || total === 0) return;
    stop();
    const gen = ++genRef.current;
    setRevealed(0);
    setCaption(null);
    setPlaying(true);
    streamDoneRef.current = false;

    if (!voice) {
      revealBlock(0);
      runSilentFrom(1, gen);
      return;
    }

    // One audio element for the whole board so the lip-sync analyser stays
    // attached, matching how a chat turn handles its chunks.
    const audio = new Audio();
    audioElRef.current = audio;
    const controller = new AbortController();
    abortRef.current = controller;

    streamBoardNarration(
      sessionId,
      board.id,
      {
        onChunkStart: (index) => {
          if (gen !== genRef.current) return;
          bytesRef.current.set(index, []);
        },
        onChunkBytes: (index, bytes) => {
          if (gen !== genRef.current) return;
          bytesRef.current.get(index)?.push(bytes);
        },
        onChunkEnd: (index) => {
          if (gen !== genRef.current) return;
          const parts = bytesRef.current.get(index) ?? [];
          bytesRef.current.delete(index);
          readyRef.current.set(
            index,
            URL.createObjectURL(new Blob(parts as BlobPart[], { type: "audio/mpeg" }))
          );
          // Release only contiguous blocks: block 2 must never be heard before
          // block 1, even if its audio finished first.
          while (readyRef.current.has(nextRef.current)) {
            const url = readyRef.current.get(nextRef.current)!;
            readyRef.current.delete(nextRef.current);
            queueRef.current.push({ index: nextRef.current, url });
            nextRef.current += 1;
          }
          if (!isPlayingRef.current) playNextRef.current();
        },
        onDone: () => {
          if (gen !== genRef.current) return;
          streamDoneRef.current = true;
        },
      },
      controller.signal
    ).catch(() => {
      if (gen !== genRef.current) return;
      // No narration available — the board is still worth watching.
      releaseAudio();
      revealBlock(0);
      runSilentFrom(1, gen);
    });
  }, [board, total, voice, sessionId, stop, revealBlock, runSilentFrom, releaseAudio]);

  /** Show the whole board at once, for a student who does not want to wait. */
  const skipToEnd = useCallback(() => {
    stop();
    setRevealed(total);
    setCaption(null);
  }, [stop, total]);

  /** What the tutor should look like. Deliberately never "speaking" unless
   * sound is actually coming out: with voice off there is no audio at all, so
   * the avatar stays idle rather than miming. */
  const avatarState: "idle" | "thinking" | "speaking" = speaking
    ? "speaking"
    : playing && voice
      ? "thinking"
      : "idle";

  return { revealed, caption, playing, speaking, avatarState, play, stop, skipToEnd, audioElRef };
}
