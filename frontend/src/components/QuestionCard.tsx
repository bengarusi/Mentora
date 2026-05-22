import { useState } from "react";
import type { Question } from "../types";

interface Props {
  question: Question;
  index: number;
  answered: boolean;
  feedback: string | null;
  isCorrect: boolean | null;
  onSubmit: (answer: string) => void;
  disabled: boolean;
}

export function QuestionCard({
  question,
  index,
  answered,
  feedback,
  isCorrect,
  onSubmit,
  disabled,
}: Props) {
  const [answer, setAnswer] = useState("");

  return (
    <div className="card question-card">
      <div className="question-header">
        <strong>Question {index + 1}</strong>
        <span className="muted">difficulty {question.difficulty}</span>
      </div>
      <p>{question.question_text}</p>

      {answered ? (
        <p className={isCorrect ? "feedback-correct" : "feedback-wrong"}>
          {isCorrect ? "Correct! " : "Not quite. "}
          {feedback}
        </p>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (answer.trim()) onSubmit(answer.trim());
          }}
        >
          <input
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            placeholder="Your answer"
            disabled={disabled}
          />
          <button type="submit" disabled={disabled || !answer.trim()}>
            Submit
          </button>
        </form>
      )}
    </div>
  );
}
