import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { BoardResponse } from "../types";

// The page pulls in the whole practice API surface; stub it at the module edge
// so these tests are about board behaviour, not about the lesson flow.
const listBoards = vi.fn();
const reviewQuestionBoard = vi.fn();
const getBoard = vi.fn();
const openLessonBoard = vi.fn();
const streamBoardNarration = vi.fn();

vi.mock("../api/board", () => ({
  listBoards: (...a: unknown[]) => listBoards(...a),
  reviewQuestionBoard: (...a: unknown[]) => reviewQuestionBoard(...a),
  getBoard: (...a: unknown[]) => getBoard(...a),
  openLessonBoard: (...a: unknown[]) => openLessonBoard(...a),
  streamBoardNarration: (...a: unknown[]) => streamBoardNarration(...a),
}));

const QUESTIONS = [
  { id: 101, difficulty: 1, question_text: "Compare 4 and 7", set_number: 1 },
  { id: 102, difficulty: 2, question_text: "Compare 8 and 8", set_number: 1 },
];

const GRADES = QUESTIONS.map((q, i) => ({
  question_id: q.id,
  question_text: q.question_text,
  difficulty: q.difficulty,
  set_number: 1,
  student_answer: "<",
  is_correct: i === 0,
  feedback: "Nice work.",
  correct_answer: "<",
  solution_steps: null,
  explanation: null,
}));

const submitPracticeSet = vi.fn(async () => ({ set_number: 1, grades: GRADES }));

vi.mock("../api/tutor", () => ({
  startPractice: vi.fn(async () => ({ set_number: 1, questions: QUESTIONS })),
  submitPracticeSet: () => submitPracticeSet(),
  nextPracticeSet: vi.fn(),
  finishPractice: vi.fn(),
}));

vi.mock("../api/sessions", () => ({
  getSession: vi.fn(async () => ({ topic: "Numbers", subtopic: "Comparing numbers" })),
}));

// Needs auth context and has nothing to do with boards.
vi.mock("../components/LearningPathSidebar", () => ({
  LearningPathSidebar: () => null,
}));

import { PracticePage } from "./PracticePage";

function board(id: number, questionId: number): BoardResponse {
  return {
    id,
    kind: "practice_review",
    message_id: null,
    question_id: questionId,
    created_at: null,
    spec: {
      title: "Comparing two numbers",
      intro: "Let's look at this together.",
      final_answer: null,
      blocks: [
        {
          kind: "steps",
          id: "s1",
          caption: "Working through it",
          narration: "First we line up the two numbers.",
          items: [
            {
              math: "4 < 7",
              operation: null,
              note: null,
              emphasis: "underline",
              emphasis_tone: "good",
            },
          ],
        },
      ],
    },
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <PracticePage />
    </MemoryRouter>
  );
}

async function submitTheSet(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByText(/Compare 4 and 7/);
  await user.type(screen.getByPlaceholderText("Type your answer"), "<");
  await user.click(screen.getByRole("button", { name: /Next/ }));
  await user.type(screen.getByPlaceholderText("Type your answer"), "=");
  await user.click(screen.getByRole("button", { name: /Submit Answers/ }));
  await screen.findByText(/questions correct this round/);
}

beforeEach(() => {
  listBoards.mockResolvedValue({ enabled: true, boards: [] });
  reviewQuestionBoard.mockReset();
  getBoard.mockReset();
  // The narration stream never resolves in these tests; the player falls back
  // to timed reveal, which is what we want for assertions about content.
  streamBoardNarration.mockRejectedValue(new Error("no audio in tests"));
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("board explanations in practice", () => {
  it("offers no board while the student is still answering", async () => {
    renderPage();
    await screen.findByText(/Compare 4 and 7/);

    // The whole point of moving the board out of the answering flow: this is
    // the student's to work through alone.
    expect(screen.queryByRole("button", { name: /board/i })).not.toBeInTheDocument();
    expect(reviewQuestionBoard).not.toHaveBeenCalled();
  });

  it("never generates or opens a board on its own once graded", async () => {
    const user = userEvent.setup();
    renderPage();
    await submitTheSet(user);

    expect(await screen.findAllByRole("button", { name: /Explain on board/ })).toHaveLength(2);
    expect(reviewQuestionBoard).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("offers no board action at all when the feature is disabled", async () => {
    listBoards.mockResolvedValue({ enabled: false, boards: [] });
    const user = userEvent.setup();
    renderPage();
    await submitTheSet(user);

    await waitFor(() => expect(listBoards).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /board/i })).not.toBeInTheDocument();
  });

  it("reviews the question the student asked about", async () => {
    reviewQuestionBoard.mockResolvedValue(board(1, 102));
    const user = userEvent.setup();
    renderPage();
    await submitTheSet(user);

    const buttons = await screen.findAllByRole("button", { name: /Explain on board/ });
    await user.click(buttons[1]);

    expect(reviewQuestionBoard).toHaveBeenCalledWith(expect.anything(), 102);
    expect(await screen.findByRole("dialog")).toHaveAccessibleName("Comparing two numbers");
  });

  it("writes the board out block by block", async () => {
    reviewQuestionBoard.mockResolvedValue(board(1, 101));
    const user = userEvent.setup();
    renderPage();
    await submitTheSet(user);
    await user.click((await screen.findAllByRole("button", { name: /Explain on board/ }))[0]);

    await screen.findByRole("dialog");

    // The first block is written immediately and its narration is captioned, so
    // a student who cannot hear still follows along.
    expect(await screen.findByText("First we line up the two numbers.")).toBeInTheDocument();
  });

  it("keeps practice usable when generation fails, and can retry", async () => {
    reviewQuestionBoard.mockRejectedValueOnce(new Error("502"));
    const user = userEvent.setup();
    renderPage();
    await submitTheSet(user);
    await user.click((await screen.findAllByRole("button", { name: /Explain on board/ }))[0]);

    expect(await screen.findByText(/couldn't get to the board/i)).toBeInTheDocument();

    reviewQuestionBoard.mockResolvedValueOnce(board(1, 101));
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("dialog")).toHaveAccessibleName("Comparing two numbers");
  });

  it("replays an existing board without generating it again", async () => {
    listBoards.mockResolvedValue({
      enabled: true,
      boards: [
        {
          id: 7,
          kind: "practice_review",
          message_id: null,
          question_id: 101,
          title: "Comparing",
          created_at: null,
        },
      ],
    });
    getBoard.mockResolvedValue(board(7, 101));
    const user = userEvent.setup();
    renderPage();
    await submitTheSet(user);

    await user.click((await screen.findAllByRole("button", { name: /Open board explanation/ }))[0]);

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(getBoard).toHaveBeenCalledWith(expect.anything(), 7);
    expect(reviewQuestionBoard).not.toHaveBeenCalled();
  });

  it("discards a board that arrives after the student closed it", async () => {
    let resolve!: (value: BoardResponse) => void;
    reviewQuestionBoard.mockReturnValue(new Promise<BoardResponse>((r) => (resolve = r)));
    const user = userEvent.setup();
    renderPage();
    await submitTheSet(user);
    await user.click((await screen.findAllByRole("button", { name: /Explain on board/ }))[0]);

    await user.keyboard("{Escape}");
    resolve(board(1, 101));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("stops the board from talking once it is closed", async () => {
    reviewQuestionBoard.mockResolvedValue(board(1, 101));
    const user = userEvent.setup();
    renderPage();
    await submitTheSet(user);
    await user.click((await screen.findAllByRole("button", { name: /Explain on board/ }))[0]);
    await screen.findByRole("dialog");

    await user.click(screen.getByRole("button", { name: "Close board" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByText("First we line up the two numbers.")).not.toBeInTheDocument();
  });
});
