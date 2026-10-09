import { FormEvent, useState } from "react";
import { api } from "../../services/api";
import { clearAdminCredentials, setAdminCredentials } from "./adminAuth";
import "./admin.css";

type Props = {
  onSuccess: () => void;
};

export default function AdminLogin({ onSuccess }: Props) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      setAdminCredentials(username.trim(), password);
      await api.adminMe();
      onSuccess();
    } catch (err) {
      clearAdminCredentials();
      setError(err instanceof Error ? err.message : "Неверный логин или пароль");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="admin admin-login">
      <header className="admin-header">
        <h1>AI Technical Interview</h1>
        <p>Вход в админ-панель</p>
      </header>
      {error && <div className="admin-error">{error}</div>}
      <form className="card admin-section" onSubmit={(e) => void onSubmit(e)}>
        <div className="form-grid">
          <div>
            <label htmlFor="admin-login">Логин</label>
            <input
              id="admin-login"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </div>
          <div>
            <label htmlFor="admin-password">Пароль</label>
            <input
              id="admin-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
        </div>
        <div className="actions">
          <button className="btn-primary" type="submit" disabled={loading}>
            {loading ? "Входим…" : "Войти"}
          </button>
        </div>
      </form>
    </div>
  );
}
