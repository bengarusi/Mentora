import type { ToolActivity } from "../types";

const LABELS: Record<string, string> = {
  evaluateAnswer: "Checking your answer…",
  analyzeHomework: "Looking through your worksheet…",
  searchStudyMaterials: "Looking in your study materials…",
  recordLearningAnnotation: "Noting a useful learning detail…",
};

export function AgentActivity({ activity }: { activity: ToolActivity[] }) {
  if (activity.length === 0) return null;
  const current = activity[activity.length - 1];
  return (
    <div className={`agent-activity ${current.status}`} aria-live="polite">
      <span className="material-symbols-outlined">
        {current.status === "running" ? "progress_activity" : "check_circle"}
      </span>
      <span>{LABELS[current.toolName] ?? "Working with a tutor tool…"}</span>
    </div>
  );
}
