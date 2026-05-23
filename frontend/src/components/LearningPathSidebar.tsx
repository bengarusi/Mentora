import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

type SidebarKey = "lessons" | "practice" | "journey" | "achievements";

const ITEMS: { key: SidebarKey; label: string; icon: string; to?: string }[] = [
  { key: "lessons", label: "My Lessons", icon: "school", to: "/progress" },
  { key: "practice", label: "Practice Room", icon: "edit_note" },
  { key: "journey", label: "Learning Journey", icon: "map", to: "/progress" },
  { key: "achievements", label: "Achievements", icon: "emoji_events" },
];

export function LearningPathSidebar({
  active,
  action,
}: {
  active?: SidebarKey;
  action?: ReactNode;
}) {
  const { student } = useAuth();
  const grade = student?.grade?.trim();
  const subtitle = grade ? `Grade ${grade} Math` : "Math Learning Path";

  return (
    <nav className="app-sidebar">
      <div className="app-sidebar-title">Learning Path</div>
      <div className="app-sidebar-sub">{subtitle}</div>

      <div className="app-sidebar-nav">
        {ITEMS.map((item) => {
          const className = `app-sidebar-link${item.key === active ? " active" : ""}`;
          if (item.to) {
            return (
              <Link key={item.key} to={item.to} className={className}>
                <span className="material-symbols-outlined">{item.icon}</span>
                {item.label}
              </Link>
            );
          }
          return (
            <button key={item.key} type="button" className={className} disabled>
              <span className="material-symbols-outlined">{item.icon}</span>
              {item.label}
            </button>
          );
        })}
      </div>

      {action && <div className="app-sidebar-action">{action}</div>}

      <div className="app-sidebar-spacer" />

      <Link to="/" className="primary-button pressable-button app-sidebar-mentor">
        <span className="material-symbols-outlined">auto_awesome</span>
        New Lesson
      </Link>
    </nav>
  );
}
