import type { BoardStepItem } from "../types";

/**
 * The marks a teacher makes at a board: an underline under the term being worked
 * on, a loop around things that belong together, a line through something being
 * cancelled.
 *
 * Drawn as SVG strokes rather than CSS text-decoration for two reasons: the
 * paths are deliberately slightly irregular so they read as hand-drawn, and a
 * stroke can be animated on with stroke-dashoffset so it appears to be drawn
 * rather than to blink into existence.
 *
 * The SVG stretches to whatever it is overlaying via preserveAspectRatio="none",
 * so a mark fits its term at any width.
 */

type Emphasis = BoardStepItem["emphasis"];
type Tone = BoardStepItem["emphasis_tone"];

const TONE_COLOR: Record<Tone, string> = {
  neutral: "var(--board-ink-accent)",
  good: "var(--board-ink-good)",
  bad: "var(--board-ink-bad)",
};

// Hand-drawn wobble is baked into the path data — a perfectly straight line
// reads as a UI underline, not as chalk.
const PATHS: Partial<Record<Emphasis, string>> = {
  underline: "M2,30 C25,26 48,33 72,28 C84,26 94,29 98,27",
  strike: "M3,31 C26,24 52,17 97,9",
  circle:
    "M50,4 C78,4 97,11 97,20 C97,29 78,36 50,36 C22,36 3,29 3,20 C3,11 22,4 50,4 C60,4 68,5 74,7",
};

export function BoardMark({
  emphasis,
  tone,
  visible,
}: {
  emphasis: Emphasis;
  tone: Tone;
  visible: boolean;
}) {
  const path = PATHS[emphasis];
  if (!path) return null;

  return (
    <svg
      className={`board-mark ${emphasis} ${visible ? "drawn" : ""}`}
      viewBox="0 0 100 40"
      preserveAspectRatio="none"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d={path}
        fill="none"
        stroke={TONE_COLOR[tone]}
        strokeWidth={emphasis === "circle" ? 1.6 : 2.2}
        strokeLinecap="round"
      />
    </svg>
  );
}
