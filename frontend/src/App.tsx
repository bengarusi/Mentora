import { lazy, Suspense } from "react";
import { Link, NavLink, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";

// Lazy-loaded so the heavy markdown/KaTeX bundle (pulled in by the lesson and
// practice pages) is split out and only fetched when one of these routes opens,
// keeping the initial/login bundle light.
const NewLessonPage = lazy(() =>
  import("./pages/NewLessonPage").then((m) => ({ default: m.NewLessonPage }))
);
const SubTopicSelectionPage = lazy(() =>
  import("./pages/SubTopicSelectionPage").then((m) => ({
    default: m.SubTopicSelectionPage,
  }))
);
const LessonPage = lazy(() =>
  import("./pages/LessonPage").then((m) => ({ default: m.LessonPage }))
);
const PrePracticeExamplePage = lazy(() =>
  import("./pages/PrePracticeExamplePage").then((m) => ({
    default: m.PrePracticeExamplePage,
  }))
);
const PracticePage = lazy(() =>
  import("./pages/PracticePage").then((m) => ({ default: m.PracticePage }))
);
const PracticeSummaryPage = lazy(() =>
  import("./pages/PracticeSummaryPage").then((m) => ({
    default: m.PracticeSummaryPage,
  }))
);
const SummaryPage = lazy(() =>
  import("./pages/SummaryPage").then((m) => ({ default: m.SummaryPage }))
);
const ProgressPage = lazy(() =>
  import("./pages/ProgressPage").then((m) => ({ default: m.ProgressPage }))
);

function AppLayout() {
  const { student, logout } = useAuth();
  const initial = student?.full_name?.trim().charAt(0).toUpperCase() || "?";
  const navClass = ({ isActive }: { isActive: boolean }) =>
    isActive ? "active" : undefined;
  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">
          Mentora
        </Link>
        <nav>
          <NavLink to="/" end className={navClass}>
            Home
          </NavLink>
          <NavLink to="/progress" className={navClass}>
            My Lessons
          </NavLink>
        </nav>
        <div className="topbar-right">
          <Link to="/progress" className="topbar-tracker">
            <span className="material-symbols-outlined">analytics</span>
            Progress Tracker
          </Link>
          {student && (
            <span className="avatar-chip" title={student.full_name}>
              {initial}
            </span>
          )}
          <button className="link-button" onClick={logout}>
            Log out
          </button>
        </div>
      </header>
      <main>
        <Suspense fallback={<div className="page-shell">Loading…</div>}>
          <Outlet />
        </Suspense>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<NewLessonPage />} />
        <Route path="/new" element={<NewLessonPage />} />
        <Route path="/topic/:topicId" element={<SubTopicSelectionPage />} />
        <Route path="/progress" element={<ProgressPage />} />
        <Route path="/lesson/:sessionId" element={<LessonPage />} />
        <Route
          path="/lesson/:sessionId/pre-practice"
          element={<PrePracticeExamplePage />}
        />
        <Route path="/lesson/:sessionId/practice" element={<PracticePage />} />
        <Route
          path="/lesson/:sessionId/practice/summary"
          element={<PracticeSummaryPage />}
        />
        <Route path="/lesson/:sessionId/summary" element={<SummaryPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
