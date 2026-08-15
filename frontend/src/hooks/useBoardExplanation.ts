import { useCallback, useEffect, useRef, useState } from "react";
import { getBoard, listBoards, openLessonBoard, reviewQuestionBoard } from "../api/board";
import type { BoardResponse, BoardSummary } from "../types";
import type { BoardPhase } from "../components/BoardModal";

interface OpenBoard {
  /** What the request was for, so a late result can be matched against it. */
  anchor: string;
  phase: BoardPhase;
  board: BoardResponse | null;
}

/**
 * Owns which boards exist and which one is on screen.
 *
 * Never generates on its own — every path here runs from an explicit student
 * action. Staleness uses the generation-token idiom useTutorChat uses for
 * barge-in: each request captures a token, and a resolved request that no longer
 * matches is dropped, so a slow board can never open over something else.
 */
export function useBoardExplanation(sessionId: number) {
  const [enabled, setEnabled] = useState(false);
  const [summaries, setSummaries] = useState<BoardSummary[]>([]);
  const [open, setOpen] = useState<OpenBoard | null>(null);
  const genRef = useRef(0);
  // Boards fetched this page-session, so replaying costs no request at all.
  const cacheRef = useRef<Map<number, BoardResponse>>(new Map());
  const lastRequestRef = useRef<(() => Promise<void>) | null>(null);

  const refresh = useCallback(async () => {
    try {
      const result = await listBoards(sessionId);
      setEnabled(result.enabled);
      setSummaries(result.boards);
    } catch {
      // A failed listing only means no board action is offered; the lesson is
      // unaffected, so there is nothing to show the student.
      setEnabled(false);
    }
  }, [sessionId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  /** The board already drawn for a chat message, if any. */
  const boardForMessage = useCallback(
    (messageId: number) => summaries.find((s) => s.message_id === messageId) ?? null,
    [summaries]
  );

  /** The review board already drawn for a graded question, if any. */
  const boardForQuestion = useCallback(
    (questionId: number) => summaries.find((s) => s.question_id === questionId) ?? null,
    [summaries]
  );

  const close = useCallback(() => {
    // Invalidate any in-flight request so its result cannot pop the board back
    // open. The request itself is left to finish: the board gets persisted, so
    // replaying it later is instant and free.
    genRef.current += 1;
    setOpen(null);
  }, []);

  const run = useCallback(
    async (anchor: string, fetcher: () => Promise<BoardResponse>) => {
      const gen = ++genRef.current;
      setOpen({ anchor, phase: "generating", board: null });
      try {
        const board = await fetcher();
        if (gen !== genRef.current) return;
        cacheRef.current.set(board.id, board);
        setOpen({ anchor, phase: "ready", board });
        refresh();
      } catch {
        if (gen !== genRef.current) return;
        setOpen({ anchor, phase: "error", board: null });
      }
    },
    [refresh]
  );

  const openExisting = useCallback(
    (anchor: string, boardId: number) => {
      const cached = cacheRef.current.get(boardId);
      if (cached) {
        setOpen({ anchor, phase: "ready", board: cached });
        genRef.current += 1;
        return Promise.resolve();
      }
      return run(anchor, () => getBoard(sessionId, boardId));
    },
    [sessionId, run]
  );

  /** Open the lesson on the board. Without a focus this is the lesson opening,
   * generated once; with one it is a fresh board about what was asked. */
  const teachOnBoard = useCallback(
    (focus?: string) => {
      const anchor = focus ? `chat:${focus}` : "lesson_intro";
      const request = () => run(anchor, () => openLessonBoard(sessionId, focus));
      lastRequestRef.current = request;
      return request();
    },
    [sessionId, run]
  );

  /** Replay a board already in the transcript. */
  const replayBoard = useCallback(
    (boardId: number) => {
      const request = () => openExisting(`board:${boardId}`, boardId);
      lastRequestRef.current = request;
      return request();
    },
    [openExisting]
  );

  /** Explain a graded practice question. */
  const reviewQuestion = useCallback(
    (questionId: number) => {
      const existing = boardForQuestion(questionId);
      const request = existing
        ? () => openExisting(`question:${questionId}`, existing.id)
        : () => run(`question:${questionId}`, () => reviewQuestionBoard(sessionId, questionId));
      lastRequestRef.current = request;
      return request();
    },
    [sessionId, run, openExisting, boardForQuestion]
  );

  const retry = useCallback(() => lastRequestRef.current?.(), []);

  return {
    enabled,
    open,
    summaries,
    boardForMessage,
    boardForQuestion,
    teachOnBoard,
    replayBoard,
    reviewQuestion,
    retry,
    close,
    refresh,
  };
}
