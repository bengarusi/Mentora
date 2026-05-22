import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    password: "",
    age: 10,
    grade: "5",
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function update<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await register(form);
      navigate("/");
    } catch {
      setError("Could not register. The email may already be in use.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="centered">
      <form className="card form" onSubmit={handleSubmit}>
        <h1>Mentora</h1>
        <h2>Create account</h2>
        {error && <p className="error">{error}</p>}
        <label>
          Full name
          <input
            value={form.full_name}
            onChange={(e) => update("full_name", e.target.value)}
            required
          />
        </label>
        <label>
          Email
          <input
            type="email"
            value={form.email}
            onChange={(e) => update("email", e.target.value)}
            required
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={form.password}
            onChange={(e) => update("password", e.target.value)}
            required
          />
        </label>
        <div className="row">
          <label>
            Age
            <input
              type="number"
              value={form.age}
              onChange={(e) => update("age", Number(e.target.value))}
              required
            />
          </label>
          <label>
            Grade
            <input
              value={form.grade}
              onChange={(e) => update("grade", e.target.value)}
              required
            />
          </label>
        </div>
        <button type="submit" disabled={busy}>
          {busy ? "Creating…" : "Register"}
        </button>
        <p className="muted">
          Already have an account? <Link to="/login">Log in</Link>
        </p>
      </form>
    </div>
  );
}
