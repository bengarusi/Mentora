import type { LessonPhase } from "../types";

const LABELS: Record<LessonPhase, string> = {
  explanation: "Explanation",
  example: "Example",
  assessment: "Assessment",
  correction: "Correction",
  level_adjustment: "Level adjustment",
  completed: "Completed",
};

export function PhaseBadge({ phase }: { phase: LessonPhase | null }) {
  if (!phase) return null;
  return <span className={`badge phase-${phase}`}>{LABELS[phase]}</span>;
}
