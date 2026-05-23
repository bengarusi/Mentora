import { useEffect, useRef, useState } from "react";

/**
 * Drives mouth-open (0–1) by analysing the amplitude of an HTMLAudioElement
 * via the Web Audio API AnalyserNode.
 *
 * Returns [mouthOpen, webAudioActive]:
 *   - mouthOpen    : normalised amplitude 0–1 (updated ~30 fps while active)
 *   - webAudioActive : true once the AnalyserNode starts producing non-zero data
 *
 * Falls back gracefully when the Web Audio API is unavailable or the
 * AudioContext cannot start — mouthOpen stays 0 and webAudioActive stays false,
 * so the calling component can use a CSS animation as a fallback.
 *
 * TODO: Replace this hook with a viseme-cue driver once the backend returns
 *       VisemeCue[] alongside the audio URL:
 *       { text, audioUrl, visemes?: VisemeCue[] }
 *       The new hook would interpolate between cues instead of reading amplitude.
 */
export function useLipSyncVolume(
  audioRef: React.RefObject<HTMLAudioElement | null>,
  active: boolean,
): [number, boolean] {
  const [mouthOpen, setMouthOpen] = useState(0);
  const [webAudioActive, setWebAudioActive] = useState(false);

  const rafRef = useRef<number | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  // Track the last update time so we throttle state updates to ~30 fps.
  const lastUpdateRef = useRef(0);

  useEffect(() => {
    if (!active || !audioRef.current) {
      setMouthOpen(0);
      setWebAudioActive(false);
      return;
    }

    const audio = audioRef.current;
    let source: MediaElementAudioSourceNode;
    let analyser: AnalyserNode;

    try {
      // Reuse the AudioContext across TTS turns to stay within browser limits.
      if (!ctxRef.current || ctxRef.current.state === "closed") {
        ctxRef.current = new AudioContext();
      }
      const ctx = ctxRef.current;
      // Resume in case the context was suspended (browser autoplay policy).
      if (ctx.state === "suspended") ctx.resume().catch(() => {});

      // Each audio element may only be connected to one source node.
      // A new Audio() is created per TTS turn, so this is always safe.
      source = ctx.createMediaElementSource(audio);
      analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      // Route through to speakers so audio remains audible.
      analyser.connect(ctx.destination);
    } catch {
      // Web Audio unavailable — CSS fallback animation runs in the component.
      return;
    }

    const data = new Uint8Array(analyser.frequencyBinCount);

    const tick = (timestamp: number) => {
      // Throttle React state updates to ~30 fps to limit re-renders.
      if (timestamp - lastUpdateRef.current >= 33) {
        analyser.getByteFrequencyData(data);
        const avg = data.reduce((s, v) => s + v, 0) / data.length;
        const val = Math.min(avg / 80, 1);
        setMouthOpen(val);
        if (val > 0.02) setWebAudioActive(true);
        lastUpdateRef.current = timestamp;
      }
      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);

    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      try {
        source.disconnect();
      } catch {
        // ignore — source may already be disconnected
      }
      setMouthOpen(0);
      setWebAudioActive(false);
    };
  }, [active, audioRef]);

  return [mouthOpen, webAudioActive];
}
