import { Navigate } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "./AuthContext";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { student, loading } = useAuth();

  if (loading) {
    return <div className="centered">Loading…</div>;
  }
  if (!student) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}
