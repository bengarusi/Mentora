import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  fetchMe,
  login as loginRequest,
  register as registerRequest,
  type RegisterPayload,
} from "../api/auth";
import { clearToken, getToken, setToken } from "../api/client";
import type { Student } from "../types";

interface AuthContextValue {
  student: Student | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [student, setStudent] = useState<Student | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!getToken()) {
      setLoading(false);
      return;
    }
    fetchMe()
      .then(setStudent)
      .catch(() => clearToken())
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const result = await loginRequest(email, password);
    setToken(result.access_token);
    setStudent(result.student);
  }, []);

  const register = useCallback(async (payload: RegisterPayload) => {
    await registerRequest(payload);
    await login(payload.email, payload.password);
  }, [login]);

  const logout = useCallback(() => {
    clearToken();
    setStudent(null);
  }, []);

  return (
    <AuthContext.Provider value={{ student, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
