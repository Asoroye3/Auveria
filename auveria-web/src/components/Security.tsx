import { useState } from "react";
import type { FormEvent } from "react";
import { api, describeError } from "../api";
import type { Me } from "../types";
import { Field, Notice } from "./ui";

export default function Security({ me, onChanged }: { me: Me; onChanged: () => void }) {
  const [current, setCurrent] = useState("");
  const [pin, setPin] = useState("");
  const [confirm, setConfirm] = useState("");
  const [otp, setOtp] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  const digits = (setter: (v: string) => void) => (e: { target: { value: string } }) =>
    setter(e.target.value.replace(/\D/g, ""));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setOk(null);
    if (me.pin_set && !/^\d{4}$/.test(current)) {
      setError("Enter your current 4-digit PIN.");
      return;
    }
    if (!/^\d{4}$/.test(pin)) {
      setError("Your new PIN must be exactly 4 digits.");
      return;
    }
    if (pin !== confirm) {
      setError("The two PINs don't match.");
      return;
    }
    setBusy(true);
    try {
      if (me.pin_set && !sentTo) {
        const res = await api.requestOtp({ purpose: "PIN_CHANGE" });
        setSentTo(res.sent_to);
        return;
      }
      await api.setPin(me.pin_set ? { pin, current_pin: current, otp } : { pin });
      setOk(me.pin_set ? "Your PIN was changed." : "Your PIN is set. You can send money now.");
      setCurrent("");
      setPin("");
      setConfirm("");
      setOtp("");
      setSentTo(null);
      onChanged();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  const label = !me.pin_set ? "Set PIN" : !sentTo ? "Text me a code" : "Change PIN";

  return (
    <section className="stack">
      <h1 className="page-title">Security</h1>
      <p className="muted">
        Signed in as {me.full_name}, phone {me.phone}. Your PIN approves every transfer. Changing it needs a code we
        text you.
      </p>

      <form className="form panel" onSubmit={submit}>
        <h2 className="section-title">{me.pin_set ? "Change your PIN" : "Create your PIN"}</h2>
        {me.pin_set && (
          <Field
            label="Current PIN"
            type="password"
            value={current}
            onChange={digits(setCurrent)}
            inputMode="numeric"
            maxLength={4}
            autoComplete="off"
          />
        )}
        <Field
          label="New PIN"
          type="password"
          value={pin}
          onChange={digits(setPin)}
          inputMode="numeric"
          maxLength={4}
          autoComplete="off"
          hint="4 digits. Not all the same digit."
        />
        <Field
          label="Confirm new PIN"
          type="password"
          value={confirm}
          onChange={digits(setConfirm)}
          inputMode="numeric"
          maxLength={4}
          autoComplete="off"
        />
        {sentTo && (
          <>
            <Notice kind="info">We texted a 6-digit code to {sentTo}.</Notice>
            <Field
              label="6-digit code"
              value={otp}
              onChange={digits(setOtp)}
              inputMode="numeric"
              maxLength={6}
              autoComplete="one-time-code"
            />
          </>
        )}
        {error && <Notice kind="error">{error}</Notice>}
        {ok && <Notice kind="ok">{ok}</Notice>}
        <button className="btn btn-primary" type="submit" disabled={busy || (!!sentTo && otp.length !== 6)}>
          {busy ? "Working…" : label}
        </button>
      </form>
    </section>
  );
}
