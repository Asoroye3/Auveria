import { useState } from "react";
import type { FormEvent } from "react";
import { api, describeError } from "../api";
import { Field, Notice } from "./ui";

export default function AuthScreen({ onAuthed }: { onAuthed: (token: string) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [bvn, setBvn] = useState("");
  const [nin, setNin] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res =
        mode === "login"
          ? await api.login(phone.trim(), password)
          : await api.register({ bvn: bvn.trim(), nin: nin.trim(), phone: phone.trim(), password });
      onAuthed(res.token);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  function switchTo(next: "login" | "register") {
    setMode(next);
    setError(null);
  }

  return (
    <div className="auth">
      <section className="auth-story">
        <p className="brand">Auveria</p>
        <h1>Every kobo is written twice.</h1>
        <p>
          Auveria records each transfer as a debit on one account and a credit on another, then checks that the books
          balance. What you see in your ledger is exactly what the bank recorded.
        </p>
        <table className="ledger sample" aria-hidden="true">
          <thead>
            <tr>
              <th scope="col">Sample entry</th>
              <th scope="col" className="num">Out</th>
              <th scope="col" className="num">In</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Your account</td>
              <td className="num out">₦25,000.00</td>
              <td className="num"></td>
            </tr>
            <tr>
              <td>Recipient’s account</td>
              <td className="num"></td>
              <td className="num in">₦25,000.00</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section className="auth-form-wrap">
        <div className="auth-card">
          <div className="tabs" role="group" aria-label="Sign in or open an account">
            <button type="button" aria-pressed={mode === "login"} onClick={() => switchTo("login")}>
              Sign in
            </button>
            <button type="button" aria-pressed={mode === "register"} onClick={() => switchTo("register")}>
              Open an account
            </button>
          </div>

          <form className="form" onSubmit={submit}>
            {mode === "register" && (
              <>
                <Field
                  label="BVN"
                  value={bvn}
                  onChange={(e) => setBvn(e.target.value)}
                  inputMode="numeric"
                  maxLength={11}
                  autoComplete="off"
                  required
                />
                <Field
                  label="NIN"
                  value={nin}
                  onChange={(e) => setNin(e.target.value)}
                  inputMode="numeric"
                  maxLength={11}
                  autoComplete="off"
                  required
                />
              </>
            )}
            <Field
              label={mode === "login" ? "Phone number or staff username" : "Phone number"}
              type={mode === "login" ? "text" : "tel"}
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              autoComplete={mode === "login" ? "username" : "tel"}
              required
            />
            <Field
              label="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              hint={mode === "register" ? "At least 8 characters, and not a common password." : undefined}
              required
            />
            {error && <Notice kind="error">{error}</Notice>}
            <button className="btn btn-primary" type="submit" disabled={busy}>
              {busy ? "Working…" : mode === "login" ? "Sign in" : "Open account"}
            </button>
          </form>

          {mode === "register" && (
            <details className="demo">
              <summary>Using demo data?</summary>
              <p>
                Identity checks run against a mock provider. A BVN and NIN that start with the same four digits belong
                to the same person, for example 22211111111 and 22219999999. Numbers ending in 0000 aren’t found.
              </p>
            </details>
          )}
        </div>
      </section>
    </div>
  );
}
