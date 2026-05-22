import { lazy, Suspense } from "react";
import { Link, Navigate, Outlet, Route, Routes } from "react-router-dom";
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
  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">
          Mentora
        </Link>
        <nav>
          <Link to="/new">New lesson</Link>
          <Link to="/progress">Progress</Link>
        </nav>
        <div className="topbar-right">
          {student && <span className="muted">{student.full_name}</span>}
          <button className="link-button" onClick={logout}>
            Log out
          </button>
        </div>
      </header>
      <main>
        <Suspense fallback={<div className="container">Loading…</div>}>
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
