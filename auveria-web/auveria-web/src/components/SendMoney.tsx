import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { ApiError, api, describeError } from "../api";
import { formatNaira, parseNairaToKobo } from "../money";
import type { Account, Me, TransferResult } from "../types";
import { Field, Notice } from "./ui";

type Step = "form" | "otp" | "done";
type Recipient = { name?: string; error?: string; loading?: boolean };

const newKey = (): string => crypto.randomUUID();

interface Props {
  account: Account;
  me: Me;
  onSent: () => void;
  onGoSecurity: () => void;
  hideBalance: boolean;
}

export default function SendMoney({ account, me, onSent, onGoSecurity, hideBalance }: Props) {
  const [to, setTo] = useState("");
  const [amount, setAmount] = useState("");
  const [pin, setPin] = useState("");
  const [otp, setOtp] = useState("");
  const [step, setStep] = useState<Step>("form");
  const [recipient, setRecipient] = useState<Recipient>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<{ result: TransferResult; toName: string } | null>(null);

  // One idempotency key per transfer. It only changes when the details change,
  // so retrying the same transfer after a dropped connection can never charge twice.
  const key = useRef(newKey());

  const kobo = parseNairaToKobo(amount);
  const needsOtp = kobo !== null && kobo >= me.otp_threshold_kobo;
  const locked = step === "otp";

  useEffect(() => {
    setRecipient({});
    if (!/^\d{10}$/.test(to)) return;
    if (to === account.account_number) {
      setRecipient({ error: "That's your own account." });
      return;
    }
    let stale = false;
    setRecipient({ loading: true });
    api
      .lookup(to)
      .then((r) => {
        if (!stale) setRecipient({ name: r.account_name });
      })
      .catch((e) => {
        if (stale) return;
        const notFound = e instanceof ApiError && e.status === 404;
        setRecipient({ error: notFound ? "No Auveria account has this number." : describeError(e) });
      });
    return () => {
      stale = true;
    };
  }, [to, account.account_number]);

  function formProblem(): string | null {
    if (!recipient.name) return "Enter the 10-digit account number of an Auveria account.";
    if (kobo === null) return "Enter an amount such as 25000 or 25,000.50.";
    if (kobo > account.balance_kobo) {
      return hideBalance
        ? "That's more than your available balance."
        : `You have ${formatNaira(account.balance_kobo)} available.`;
    }
    if (!/^\d{4}$/.test(pin)) return "Enter your 4-digit PIN.";
    return null;
  }

  async function requestCode() {
    const res = await api.requestOtp({
      purpose: "TRANSFER",
      from_account: account.account_number,
      to_account: to,
      amount_kobo: kobo as number,
    });
    const minutes = Math.max(1, Math.round(res.expires_in_seconds / 60));
    setInfo(`We texted a 6-digit code to ${res.sent_to}. It expires in ${minutes} minutes.`);
    setStep("otp");
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const problem = formProblem();
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (needsOtp && step === "form") {
        await requestCode();
        return;
      }
      const result = await api.transfer(
        {
          from_account: account.account_number,
          to_account: to,
          amount_kobo: kobo as number,
          pin,
          ...(step === "otp" ? { otp } : {}),
        },
        key.current,
      );
      setReceipt({ result, toName: recipient.name ?? "" });
      setStep("done");
      onSent();
    } catch (err) {
      if (err instanceof ApiError && err.otpRequired && step === "form") {
        try {
          await requestCode();
        } catch (e2) {
          setError(describeError(e2));
        }
      } else {
        setError(describeError(err));
      }
    } finally {
      setBusy(false);
    }
  }

  async function resendCode() {
    setBusy(true);
    setError(null);
    try {
      await requestCode();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  function changeDetails() {
    setStep("form");
    setOtp("");
    setInfo(null);
    setError(null);
  }

  function reset() {
    setTo("");
    setAmount("");
    setPin("");
    setOtp("");
    setStep("form");
    setReceipt(null);
    setInfo(null);
    setError(null);
    key.current = newKey();
  }

  if (!me.pin_set) {
    return (
      <section className="stack">
        <h1 className="page-title">Send money</h1>
        <div className="panel banner">
          <p>Set a transaction PIN before you send your first transfer.</p>
          <button className="btn btn-primary" onClick={onGoSecurity}>
            Set PIN
          </button>
        </div>
      </section>
    );
  }

  if (step === "done" && receipt) {
    return (
      <section className="stack">
        <h1 className="page-title">Sent</h1>
        <div className="panel receipt">
          <p className="receipt-line">
            {formatNaira(receipt.result.amount_kobo)} to {receipt.toName}
          </p>
          <dl className="limits">
            <div>
              <dt>Account</dt>
              <dd>{to}</dd>
            </div>
            <div>
              <dt>Reference</dt>
              <dd>{receipt.result.reference.slice(0, 12)}</dd>
            </div>
          </dl>
          <button className="btn btn-primary" onClick={reset}>
            Send another transfer
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="stack">
      <h1 className="page-title">Send money</h1>
      <p className="muted">
        From {account.account_number}, available {hideBalance ? "₦••••••" : formatNaira(account.balance_kobo)}. Transfers of{" "}
        {formatNaira(me.otp_threshold_kobo)} or more also need a code we text you.
      </p>

      <form className="form panel" onSubmit={submit}>
        <div>
          <Field
            label="Recipient account number"
            value={to}
            onChange={(e) => {
              setTo(e.target.value.replace(/\D/g, ""));
              key.current = newKey();
            }}
            inputMode="numeric"
            maxLength={10}
            autoComplete="off"
            readOnly={locked}
            required
          />
          {recipient.loading && <p className="recipient muted">Looking up account…</p>}
          {recipient.name && <p className="recipient ok">{recipient.name}</p>}
          {recipient.error && <p className="recipient bad">{recipient.error}</p>}
        </div>

        <Field
          label="Amount in naira"
          value={amount}
          onChange={(e) => {
            setAmount(e.target.value);
            key.current = newKey();
          }}
          inputMode="decimal"
          autoComplete="off"
          readOnly={locked}
          required
        />

        <Field
          label="Transaction PIN"
          type="password"
          value={pin}
          onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
          inputMode="numeric"
          maxLength={4}
          autoComplete="off"
          required
        />

        {locked && (
          <Field
            label="6-digit code"
            value={otp}
            onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
            inputMode="numeric"
            maxLength={6}
            autoComplete="one-time-code"
            required
          />
        )}

        {info && <Notice kind="info">{info}</Notice>}
        {error && <Notice kind="error">{error}</Notice>}

        <div className="actions">
          <button className="btn btn-primary" type="submit" disabled={busy || (locked && otp.length !== 6)}>
            {busy
              ? "Working…"
              : locked
                ? `Send ${kobo !== null ? formatNaira(kobo) : ""}`
                : needsOtp
                  ? "Text me a code"
                  : "Send money"}
          </button>
          {locked && (
            <>
              <button className="btn btn-quiet" type="button" onClick={resendCode} disabled={busy}>
                Send a new code
              </button>
              <button className="btn btn-quiet" type="button" onClick={changeDetails} disabled={busy}>
                Change details
              </button>
            </>
          )}
        </div>
      </form>
    </section>
  );
}
