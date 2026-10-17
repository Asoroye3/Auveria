import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { ApiError, api, describeError } from "../api";
import { formatNaira, parseNairaToKobo } from "../money";
import type { CashJournal, LedgerRow, StaffAccount, TransferResult } from "../types";
import { Field, Notice } from "./ui";

type Kind = "deposits" | "withdrawals";
type TellerView = "desk" | "journal";

const newKey = (): string => crypto.randomUUID();
const KIND_NAME: Record<Kind, string> = { deposits: "Deposit", withdrawals: "Withdrawal" };
const TYPE_NAME: Record<string, string> = {
  TRANSFER: "Transfer",
  DEPOSIT: "Cash deposit",
  WITHDRAWAL: "Cash withdrawal",
};

function formatWhen(iso: string): string {
  return new Date(iso).toLocaleString("en-NG", {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function TellerDesk({ name, onLogout }: { name: string; onLogout: () => void }) {
  const [view, setView] = useState<TellerView>("desk");
  const [tick, setTick] = useState(0); // bump to refresh the journal after cash moves

  return (
    <div className="shell">
      <nav className="rail" aria-label="Main">
        <div className="rail-head">
          <p className="brand">Auveria</p>
          <p className="rail-note">Teller desk, signed in as {name}</p>
        </div>
        <div className="nav">
          <button aria-current={view === "desk" ? "page" : undefined} onClick={() => setView("desk")}>
            Cash desk
          </button>
          <button aria-current={view === "journal" ? "page" : undefined} onClick={() => setView("journal")}>
            Journal
          </button>
        </div>
        <div className="rail-foot">
          <button className="link-btn" onClick={onLogout}>
            Sign out
          </button>
        </div>
      </nav>

      <main className="content">
        {view === "desk" ? <CashDesk onDone={() => setTick((t) => t + 1)} /> : <Journal refreshToken={tick} />}
      </main>
    </div>
  );
}

function RecentTable({ rows }: { rows: LedgerRow[] }) {
  return (
    <table className="ledger">
      <thead>
        <tr>
          <th scope="col">Recent activity</th>
          <th scope="col" className="num">Out</th>
          <th scope="col" className="num">In</th>
        </tr>
      </thead>
      <tbody>
        {rows.slice(0, 5).map((r) => (
          <tr key={`${r.reference}-${r.direction}`}>
            <td>
              <span className="what">{TYPE_NAME[r.type] ?? r.type}</span>
              <span className="when">{formatWhen(r.created_at)}</span>
            </td>
            <td className="num out">{r.direction === "DEBIT" ? r.amount_display : ""}</td>
            <td className="num in">{r.direction === "CREDIT" ? r.amount_display : ""}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CashDesk({ onDone }: { onDone: () => void }) {
  const [number, setNumber] = useState("");
  const [account, setAccount] = useState<StaffAccount | null>(null);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const [kind, setKind] = useState<Kind>("deposits");
  const [amount, setAmount] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<{ result: TransferResult; kind: Kind } | null>(null);

  // One idempotency key per cash movement; it only changes when the details change.
  const key = useRef(newKey());

  useEffect(() => {
    setLookupError(null);
    if (!/^\d{10}$/.test(number)) {
      setAccount(null);
      return;
    }
    let stale = false;
    api
      .staffAccount(number)
      .then((a) => {
        if (!stale) setAccount(a);
      })
      .catch((e) => {
        if (stale) return;
        setAccount(null);
        const notFound = e instanceof ApiError && e.status === 404;
        setLookupError(notFound ? "No customer account has this number." : describeError(e));
      });
    return () => {
      stale = true;
    };
  }, [number, reload]);

  // Never act on a card that belongs to a previously typed number.
  const current = account !== null && account.account_number === number ? account : null;
  const kobo = parseNairaToKobo(amount);

  function detailsChanged() {
    key.current = newKey();
    setConfirming(false);
    setError(null);
    setReceipt(null);
  }

  function review(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!current) return setError("Look up a customer account first.");
    if (current.status !== "ACTIVE") return setError(`This account is ${current.status.toLowerCase()}.`);
    if (kobo === null) return setError("Enter an amount such as 5000 or 5,000.50.");
    if (kind === "withdrawals" && kobo > current.balance_kobo) {
      return setError(`The balance is ${formatNaira(current.balance_kobo)}, which is less than this withdrawal.`);
    }
    setConfirming(true);
  }

  async function confirm() {
    if (!current || kobo === null) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.staffCash(kind, { account_number: number, amount_kobo: kobo }, key.current);
      setReceipt({ result, kind });
      setConfirming(false);
      setAmount("");
      key.current = newKey();
      setReload((r) => r + 1);
      onDone();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="stack">
      <h1 className="page-title">Cash desk</h1>
      <p className="muted">Look up the customer’s account, then record the cash that changes hands.</p>

      <div className="panel form">
        <Field
          label="Customer account number"
          value={number}
          onChange={(e) => {
            setNumber(e.target.value.replace(/\D/g, ""));
            detailsChanged();
          }}
          inputMode="numeric"
          maxLength={10}
          autoComplete="off"
        />
        {lookupError && <p className="recipient bad">{lookupError}</p>}
      </div>

      {current && (
        <>
          <div className="panel stack">
            <h2 className="section-title">{current.owner_name}</h2>
            <dl className="limits">
              <div>
                <dt>Account number</dt>
                <dd>{current.account_number}</dd>
              </div>
              <div>
                <dt>Balance</dt>
                <dd>{formatNaira(current.balance_kobo)}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>{current.status.charAt(0) + current.status.slice(1).toLowerCase()}</dd>
              </div>
              <div>
                <dt>Verification</dt>
                <dd>{current.tier === null ? "None" : `Tier ${current.tier}`}</dd>
              </div>
            </dl>
            {current.recent.length > 0 && <RecentTable rows={current.recent} />}
          </div>

          <form className="panel form" onSubmit={review}>
            <div className="seg" role="group" aria-label="Operation">
              {(Object.keys(KIND_NAME) as Kind[]).map((k) => (
                <button
                  key={k}
                  type="button"
                  aria-pressed={kind === k}
                  disabled={confirming}
                  onClick={() => {
                    setKind(k);
                    detailsChanged();
                  }}
                >
                  {KIND_NAME[k]}
                </button>
              ))}
            </div>

            <Field
              label="Amount in naira"
              value={amount}
              onChange={(e) => {
                setAmount(e.target.value);
                detailsChanged();
              }}
              inputMode="decimal"
              autoComplete="off"
              readOnly={confirming}
            />

            {confirming && kobo !== null && (
              <Notice kind="info">
                {KIND_NAME[kind]} of {formatNaira(kobo)} {kind === "deposits" ? "into" : "from"}{" "}
                {current.owner_name}’s account ({current.account_number}). Check the cash before you confirm.
              </Notice>
            )}
            {error && <Notice kind="error">{error}</Notice>}
            {receipt && (
              <Notice kind="ok">
                {KIND_NAME[receipt.kind]} of {formatNaira(receipt.result.amount_kobo)} recorded. Reference{" "}
                {receipt.result.reference.slice(0, 8)}.
              </Notice>
            )}

            <div className="actions">
              {!confirming ? (
                <button className="btn btn-primary" type="submit">
                  Review {KIND_NAME[kind].toLowerCase()}
                </button>
              ) : (
                <>
                  <button className="btn btn-primary" type="button" onClick={() => void confirm()} disabled={busy}>
                    {busy ? "Working…" : `Confirm ${KIND_NAME[kind].toLowerCase()}`}
                  </button>
                  <button className="btn btn-quiet" type="button" onClick={() => setConfirming(false)} disabled={busy}>
                    Back
                  </button>
                </>
              )}
            </div>
          </form>
        </>
      )}
    </section>
  );
}

function Journal({ refreshToken }: { refreshToken: number }) {
  const [data, setData] = useState<CashJournal | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let stale = false;
    setError(null);
    api
      .cashJournal()
      .then((d) => {
        if (!stale) setData(d);
      })
      .catch((e) => {
        if (!stale) setError(describeError(e));
      });
    return () => {
      stale = true;
    };
  }, [refreshToken]);

  return (
    <section className="stack">
      <h1 className="page-title">Journal</h1>
      {error && <Notice kind="error">{error}</Notice>}
      {!data && !error && <p className="muted">Loading the journal…</p>}
      {data && (
        <>
          <div className="panel">
            <p className="muted">Net cash taken in</p>
            <p className="receipt-line">{data.net_cash_display}</p>
          </div>
          <div className="panel">
            {data.entries.length === 0 ? (
              <p className="muted">No cash has moved yet. Deposits and withdrawals will be listed here.</p>
            ) : (
              <table className="ledger">
                <thead>
                  <tr>
                    <th scope="col">Activity</th>
                    <th scope="col">Customer</th>
                    <th scope="col" className="num">Cash in</th>
                    <th scope="col" className="num">Cash out</th>
                  </tr>
                </thead>
                <tbody>
                  {data.entries.map((e) => (
                    <tr key={e.reference}>
                      <td>
                        <span className="what">{TYPE_NAME[e.type] ?? e.type}</span>
                        <span className="when">
                          {formatWhen(e.created_at)}, ref {e.reference.slice(0, 8)}
                        </span>
                      </td>
                      <td>
                        <span className="what">{e.account_name}</span>
                        <span className="when">{e.account_number}</span>
                      </td>
                      <td className="num in">{e.type === "DEPOSIT" ? e.amount_display : ""}</td>
                      <td className="num out">{e.type === "WITHDRAWAL" ? e.amount_display : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </section>
  );
}
