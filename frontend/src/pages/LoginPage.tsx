import { useEffect, useState } from "react";
import { useAuthStore } from "../store/authStore";

export default function LoginPage() {
  const { setupRequired, checkSetup, setupAdmin, login } = useAuthStore();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    checkSetup();
  }, [checkSetup]);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      if (setupRequired) {
        await setupAdmin(username, password);
        await login(username, password);
      } else {
        await login(username, password);
      }
    } catch (e: any) {
      setError(e.message || "Что-то пошло не так");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ height: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg-void)" }}>
      <div style={{ width: 340, background: "var(--bg-base)", border: "1px solid var(--border-hair)", borderRadius: "var(--radius-lg)", padding: 28 }}>
        <h1 style={{ fontFamily: "var(--font-prose)", fontSize: 22, marginBottom: 4 }}>LocalRP</h1>
        <p style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 20 }}>
          {setupRequired ? "Создайте учётную запись администратора" : "Войдите в систему"}
        </p>
        <input
          placeholder="Логин"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          style={inputStyle}
        />
        <input
          placeholder="Пароль"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          style={{ ...inputStyle, marginTop: 10 }}
          onKeyDown={(e) => e.key === "Enter" && submit()}
        />
        {error && <p style={{ color: "var(--danger)", fontSize: 12, marginTop: 8 }}>{error}</p>}
        <button
          disabled={busy || !username || !password}
          onClick={submit}
          style={{
            marginTop: 16, width: "100%", padding: "10px 0", borderRadius: "var(--radius-sm)",
            border: "none", background: "var(--accent)", color: "white", fontWeight: 500,
          }}
        >
          {setupRequired ? "Создать и войти" : "Войти"}
        </button>
      </div>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "9px 12px",
  borderRadius: "var(--radius-sm)",
  border: "1px solid var(--border-hair)",
  background: "var(--bg-raised)",
  color: "var(--text-primary)",
  fontSize: 14,
};
