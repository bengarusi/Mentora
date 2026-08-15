import { useEffect, useRef, type ReactNode } from "react";
import type { Message } from "../types";
import { MessageBubble } from "./MessageBubble";

export function ChatWindow({
  messages,
  footerFor,
}: {
  messages: Message[];
  /** Optional slot rendered inside a tutor bubble, below its text. Used for the
   * board replay card so a board stays where it happened in the conversation. */
  footerFor?: (message: Message) => ReactNode;
}) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="chat-scroll-area">
      {messages.length === 0 && (
        <p className="chat-empty">Your tutor is getting ready…</p>
      )}
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} footer={footerFor?.(m)} />
      ))}
      <div ref={endRef} />
    </div>
  );
}
