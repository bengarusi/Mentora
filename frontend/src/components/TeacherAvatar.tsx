import { useRef, type RefObject } from "react";
import { useLipSyncVolume } from "../hooks/useLipSyncVolume";

export type AvatarState = "idle" | "thinking" | "speaking";

/**
 * Reserved for future backend-driven lip sync.
 *
 * TODO: When the backend returns { audioUrl, visemes?: VisemeCue[] },
 * update useLipSyncVolume to accept cues and drive mouthOpen from them.
 */
export type VisemeCue = {
  timeMs: number;
  viseme: string;
};

// DEV ONLY: flip to true to bypass Web Audio and test the CSS fallback animation.
// Never commit as true — it silences TTS playback through the analyser.
const FORCE_CSS_FALLBACK = false;

// Describes how the mouth ellipse should be scaled for a given volume level.
// TODO: Replace getMouthShape with a viseme lookup table once the backend
//       returns VisemeCue[]. Map viseme strings to shapes:
//         "rest"/"closed" → closed, "aa" → wide, "ee" → small,
//         "oh" → o-shape, "fv" → small, "l" → medium, etc.
type MouthShape = { scaleX: number; scaleY: number };

function getMouthShape(mouthOpen: number): MouthShape {
  if (mouthOpen < 0.15) return { scaleX: 0.82, scaleY: 0.11 }; // closed / rest
  if (mouthOpen < 0.35) return { scaleX: 0.88, scaleY: 0.38 }; // small open (ee-like)
  if (mouthOpen < 0.65) return { scaleX: 1.00, scaleY: 0.70 }; // medium open (aa-like)
  if (mouthOpen < 0.85) return { scaleX: 1.00, scaleY: 1.00 }; // wide open
  return                       { scaleX: 0.76, scaleY: 1.00 }; // rounded "oh"
}

interface TeacherAvatarProps {
  state: AvatarState;
  audioElementRef?: RefObject<HTMLAudioElement | null>;
  className?: string;
}

export function TeacherAvatar({
  state,
  audioElementRef,
  className = "",
}: TeacherAvatarProps) {
  const fallbackRef = useRef<HTMLAudioElement | null>(null);
  const resolvedRef = audioElementRef ?? fallbackRef;

  // Web Audio amplitude analysis; falls back to CSS animation when unavailable.
  // TODO: Swap for a VisemeCue-based driver when visemes are available.
  const [mouthOpen, webAudioActive] = useLipSyncVolume(
    resolvedRef,
    state === "speaking",
  );

  // FORCE_CSS_FALLBACK overrides the Web Audio path for development testing.
  const useWebAudio = webAudioActive && !FORCE_CSS_FALLBACK;

  // Derive mouth shape from amplitude.
  const mouth = getMouthShape(mouthOpen);

  // Inner dark mouth: smaller scale + fades in as mouth opens.
  const innerScaleX = mouth.scaleX * 0.72;
  const innerScaleY = Math.max(mouth.scaleY - 0.28, 0);
  const innerOpacity = Math.min(1, Math.max(0, (mouth.scaleY - 0.25) / 0.5));

  // Pupils look slightly upward in thinking state — classic "hmm" expression.
  const pupilDy = state === "thinking" ? -3 : 0;

  // Eyebrows: asymmetric raise in thinking (left higher → curious expression).
  const leftBrow =
    state === "thinking"
      ? "M 59 64 Q 72 56 85 62"
      : "M 59 71 Q 72 64 85 70";
  const rightBrow =
    state === "thinking"
      ? "M 115 68 Q 128 63 141 69"
      : "M 115 70 Q 128 64 141 71";

  return (
    <div
      className={`teacher-avatar teacher-avatar--${state} ${className}`}
      aria-label={`Teacher is ${state}`}
    >
      <svg
        viewBox="0 0 200 200"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
        focusable="false"
      >
        <defs>
          <radialGradient id="ta-glow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#e9ddff" stopOpacity="0.9" />
            <stop offset="100%" stopColor="#e9ddff" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* Soft background glow */}
        <circle cx="100" cy="100" r="96" fill="url(#ta-glow)" />

        {/* Hair — drawn first; face circle occludes its lower half */}
        <path
          d="M 30 100 Q 30 18 100 15 Q 170 18 170 100 Q 148 88 100 88 Q 52 88 30 100 Z"
          fill="#3d2314"
        />

        {/* Ears */}
        <ellipse cx="30"  cy="102" rx="11" ry="15" fill="#ffe8d6" />
        <ellipse cx="170" cy="102" rx="11" ry="15" fill="#ffe8d6" />

        {/* Head */}
        <circle cx="100" cy="102" r="70" fill="#ffe8d6" />

        {/* Left eye — pupilDy lifts pupils in thinking state */}
        <g className="ta-eye ta-eye--left">
          <ellipse cx="72" cy="90" rx="15" ry="17" fill="white" />
          <circle cx="72" cy={92 + pupilDy} r="10" fill="#6b38d4" />
          <circle cx="72" cy={92 + pupilDy} r="5"  fill="#2a1060" />
          <circle cx="76" cy={88 + pupilDy} r="4"  fill="white" />
        </g>

        {/* Right eye */}
        <g className="ta-eye ta-eye--right">
          <ellipse cx="128" cy="90" rx="15" ry="17" fill="white" />
          <circle cx="128" cy={92 + pupilDy} r="10" fill="#6b38d4" />
          <circle cx="128" cy={92 + pupilDy} r="5"  fill="#2a1060" />
          <circle cx="132" cy={88 + pupilDy} r="4"  fill="white" />
        </g>

        {/* Eyebrows — asymmetrically raised in thinking state */}
        <path
          d={leftBrow}
          stroke="#3d2314"
          strokeWidth="3.5"
          fill="none"
          strokeLinecap="round"
        />
        <path
          d={rightBrow}
          stroke="#3d2314"
          strokeWidth="3.5"
          fill="none"
          strokeLinecap="round"
        />

        {/* Rosy cheeks */}
        <circle cx="50"  cy="112" r="16" fill="#ff8899" opacity="0.3" />
        <circle cx="150" cy="112" r="16" fill="#ff8899" opacity="0.3" />

        {/* ── Mouth ──────────────────────────────────────────────────────────
            Speaking + Web Audio active : shape-driven with transitions
            Speaking + Web Audio silent : CSS cycle animation (fallback)
            Idle / thinking             : arc path (big smile vs. soft neutral)
            ──────────────────────────────────────────────────────────────── */}
        {state === "speaking" ? (
          useWebAudio ? (
            <>
              {/* Outer lips */}
              <ellipse
                cx="100"
                cy="127"
                rx="19"
                ry="14"
                fill="#c0607a"
                className="ta-mouth-shape"
                style={{
                  transform: `scaleX(${mouth.scaleX}) scaleY(${mouth.scaleY})`,
                }}
              />
              {/* Dark inner mouth — fades in as mouth opens */}
              <ellipse
                cx="100"
                cy="129"
                rx="13"
                ry="10"
                fill="#8b2042"
                className="ta-mouth-shape"
                style={{
                  transform: `scaleX(${innerScaleX}) scaleY(${innerScaleY})`,
                  opacity: innerOpacity,
                }}
              />
            </>
          ) : (
            /* CSS fallback: natural speech cycle when Web Audio isn't active */
            <ellipse
              cx="100"
              cy="127"
              rx="19"
              ry="14"
              fill="#c0607a"
              className="ta-mouth-speaking-css"
            />
          )
        ) : (
          <path
            d={
              state === "thinking"
                ? "M 84 128 Q 100 133 116 128"   // neutral / closed-ish
                : "M 82 124 Q 100 140 118 124"   // happy smile
            }
            stroke="#c0607a"
            strokeWidth="4"
            fill="none"
            strokeLinecap="round"
          />
        )}

        {/* Shirt collar */}
        <path
          d="M 55 165 L 72 200 L 128 200 L 145 165 Q 100 178 55 165 Z"
          fill="#6b38d4"
        />
        <ellipse cx="100" cy="200" rx="48" ry="16" fill="#6b38d4" />
      </svg>

      {/* Bouncing dots shown below avatar while AI is generating a response */}
      {state === "thinking" && (
        <div className="ta-thinking-dots" aria-label="Thinking">
          <span className="ta-dot" />
          <span className="ta-dot" />
          <span className="ta-dot" />
        </div>
      )}
    </div>
  );
}
