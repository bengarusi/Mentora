const LABELS: Record<string, string> = {
  achieved: "Achieved",
  partially: "Partially achieved",
  not_achieved: "Not achieved",
};

export function ScoreBadge({ level }: { level: string | null }) {
  if (!level) return null;
  return <span className={`badge success-${level}`}>{LABELS[level] ?? level}</span>;
}
