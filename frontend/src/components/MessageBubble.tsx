import { memo } from "react";
import { RichText } from "./RichText";
import type { Message } from "../types";

export const MessageBubble = memo(function MessageBubble({
  message,
}: {
  message: Message;
}) {
  const isTutor = message.role === "tutor";
  return (
    <div className={`chat-row ${isTutor ? "tutor" : "student"}`}>
      <div className={`msg-avatar ${isTutor ? "tutor" : "student"}`}>
        <span className="material-symbols-outlined">
          {isTutor ? "smart_toy" : "person"}
        </span>
      </div>
      <div className={isTutor ? "tutor-message" : "student-message"}>
        {message.content === "" ? (
          <span className="typing-cursor">▍</span>
        ) : (
          <RichText content={message.content} />
        )}
      </div>
    </div>
  );
});
