import type { Message } from "../types";

export function MessageBubble({ message }: { message: Message }) {
  const isTutor = message.role === "tutor";
  return (
    <div className={`bubble ${isTutor ? "bubble-tutor" : "bubble-student"}`}>
      <span className="bubble-role">{isTutor ? "Tutor" : "You"}</span>
      <p>{message.content}</p>
    </div>
  );
}
