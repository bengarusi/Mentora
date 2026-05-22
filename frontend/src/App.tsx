import { Link, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { NewLessonPage } from "./pages/NewLessonPage";
import { LessonPage } from "./pages/LessonPage";
import { AssessmentPage } from "./pages/AssessmentPage";
import { SummaryPage } from "./pages/SummaryPage";
import { ProgressPage } from "./pages/ProgressPage";

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
        <Outlet />
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
        <Route path="/lesson/:sessionId/assessment" element={<AssessmentPage />} />
        <Route path="/lesson/:sessionId/summary" element={<SummaryPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
