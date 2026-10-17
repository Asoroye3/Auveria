import { useCallback, useEffect, useState } from "react";
import { api, describeError, setUnauthorizedHandler, tokenStore } from "./api";
import AuthScreen from "./components/AuthScreen";
import Dashboard from "./components/Dashboard";
import TellerDesk from "./components/TellerDesk";
import type { Whoami } from "./types";

export default function App() {
  const [token, setToken] = useState<string | null>(tokenStore.get());
  const [who, setWho] = useState<Whoami | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  const logout = useCallback(() => {
    tokenStore.clear();
    setToken(null);
    setWho(null);
    setError(null);
  }, []);

  // If the server ever says our token is no longer valid, drop back to sign-in.
  useEffect(() => {
    setUnauthorizedHandler(logout);
  }, [logout]);

  // Ask the server who we are, so staff get the teller desk and customers get the app.
  useEffect(() => {
    if (!token) return;
    let stale = false;
    setError(null);
    api
      .whoami()
      .then((w) => {
        if (!stale) setWho(w);
      })
      .catch((e) => {
        if (!stale) setError(describeError(e));
      });
    return () => {
      stale = true;
    };
  }, [token, attempt]);

  if (!token) {
    return (
      <AuthScreen
        onAuthed={(t) => {
          tokenStore.set(t);
          setWho(null);
          setToken(t);
        }}
      />
    );
  }

  if (error) {
    return (
      <div className="center">
        <div className="panel stack">
          <p>{error}</p>
          <div className="actions">
            <button className="btn btn-quiet" onClick={() => setAttempt((a) => a + 1)}>
              Try again
            </button>
            <button className="btn btn-quiet" onClick={logout}>
              Sign out
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!who) {
    return (
      <div className="center">
        <p className="muted">Signing you in…</p>
      </div>
    );
  }

  if (who.role === "staff") return <TellerDesk name={who.name} onLogout={logout} />;
  if (who.role === "customer") return <Dashboard onLogout={logout} />;

  return (
    <div className="center">
      <div className="panel stack">
        <p>This login isn’t linked to a customer profile or a staff role.</p>
        <button className="btn btn-quiet" onClick={logout}>
          Sign out
        </button>
      </div>
    </div>
  );
}
