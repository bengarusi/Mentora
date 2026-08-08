import { useEffect, useRef } from "react";

interface ChatComposerProps {
  draft: string;
  onDraftChange: (value: string) => void;
  onSend: (text: string) => void;
  busy: boolean;
  recording: boolean;
  onToggleRecording: () => void;
  voicePlayback: boolean;
  onVoicePlaybackChange: (enabled: boolean) => void;
  voiceError: string | null;
  placeholder?: string;
}

/**
 * The tutor-voice toggle plus the message input bar.
 *
 * Shared by every page that talks to the tutor, so the mic, mute, and send
 * affordances behave identically in a lesson and in Homework Help.
 */
export function ChatComposer({
  draft,
  onDraftChange,
  onSend,
  busy,
  recording,
  onToggleRecording,
  voicePlayback,
  onVoicePlaybackChange,
  voiceError,
  placeholder = "Type your message here…",
}: ChatComposerProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const wasBusyRef = useRef(busy);

  useEffect(() => {
    if (wasBusyRef.current && !busy) {
      inputRef.current?.focus();
    }
    wasBusyRef.current = busy;
  }, [busy]);

  return (
    <>
      <div className="voice-bar">
        <label className="voice-toggle">
          <input
            type="checkbox"
            checked={voicePlayback}
            onChange={(e) => onVoicePlaybackChange(e.target.checked)}
          />
          <span className="material-symbols-outlined">
            {voicePlayback ? "volume_up" : "volume_off"}
          </span>
          Tutor voice
        </label>
        {recording && (
          <span className="voice-status recording">
            <span className="rec-dot" />
            Recording… click the mic to stop
          </span>
        )}
        {voiceError && <span className="voice-status error">{voiceError}</span>}
      </div>

      <form
        className="chat-input-bar"
        onSubmit={(e) => {
          e.preventDefault();
          onSend(draft);
        }}
      >
        <span className="material-symbols-outlined chat-add">add_circle</span>
        <input
          ref={inputRef}
          value={draft}
          onChange={(e) => onDraftChange(e.target.value)}
          placeholder={placeholder}
          disabled={busy || recording}
        />
        <button
          type="button"
          className={`mic-button pressable-button${recording ? " recording" : ""}`}
          onClick={onToggleRecording}
          disabled={busy}
          aria-label={recording ? "Stop recording" : "Start voice message"}
          title={recording ? "Stop recording" : "Start voice message"}
        >
          <span className="material-symbols-outlined">
            {recording ? "stop" : "mic"}
          </span>
        </button>
        <button
          type="submit"
          className="primary-button pressable-button chat-send"
          disabled={busy || recording || !draft.trim()}
        >
          Send
          <span className="material-symbols-outlined">send</span>
        </button>
      </form>
    </>
  );
}
