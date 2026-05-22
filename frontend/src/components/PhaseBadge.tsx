import type { LessonPhase } from "../types";

const LABELS: Record<LessonPhase, string> = {
  teaching: "Teaching",
  pre_practice_example: "Guided Example",
  practice: "Practice",
  practice_summary: "Practice Results",
  summary: "Summary",
  completed: "Completed",
};

export function PhaseBadge({ phase }: { phase: LessonPhase | null }) {
  if (!phase) return null;
  return <span className={`badge phase-${phase}`}>{LABELS[phase] ?? phase}</span>;
}
