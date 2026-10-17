import { useCallback, useEffect, useState } from "react";
import { api, describeError } from "../api";
import { formatNaira, splitNaira } from "../money";
import type { Account, Me } from "../types";
import Security from "./Security";
import SendMoney from "./SendMoney";
import Statement from "./Statement";
import { EyeIcon, EyeOffIcon } from "./icons";
import { Notice } from "./ui";

type View = "home" | "send" | "ledger" | "security";

const HIDE_KEY = "auveria.hideBalance";

const NAV: { id: View; label: string }[] = [
  { id: "home", label: "Home" },
  { id: "send", label: "Send money" },
  { id: "ledger", label: "Ledger" },
  { id: "security", label: "Security" },
];

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export default function Dashboard({ onLogout }: { onLogout: () => void }) {
  const [view, setView] = useState<View>("home");
  const [me, setMe] = useState<Me | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0); // bump to make the ledger refetch
  const [hidden, setHidden] = useState<boolean>(() => localStorage.getItem(HIDE_KEY) === "1");

  const toggleHidden = () =>
    setHidden((h) => {
      const next = !h;
      localStorage.setItem(HIDE_KEY, next ? "1" : "0");
      return next;
    });

  const load = useCallback(async () => {
    try {
      const [m, a] = await Promise.all([api.me(), api.accounts()]);
      setMe(m);
      setAccounts(a);
      setSelected((cur) => cur ?? a[0]?.account_number ?? null);
      setError(null);
    } catch (err) {
      setError(describeError(err));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (!me) {
    return (
      <div className="center">
        {error ? (
          <div className="panel stack">
            <Notice kind="error">{error}</Notice>
            <button className="btn btn-quiet" onClick={() => void load()}>
              Try again
            </button>
          </div>
        ) : (
          <p className="muted">Loading your accounts…</p>
        )}
      </div>
    );
  }

  const account = accounts.find((a) => a.account_number === selected) ?? null;
  const firstName = me.full_name.split(" ")[0];

  async function afterTransfer() {
    await load();
    setTick((t) => t + 1);
  }

  return (
    <div className="shell">
      <nav className="rail" aria-label="Main">
        <p className="brand">Auveria</p>
        <div className="nav">
          {NAV.map((item) => (
            <button
              key={item.id}
              aria-current={view === item.id ? "page" : undefined}
              onClick={() => setView(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="rail-foot">
          <button className="link-btn" onClick={onLogout}>
            Sign out
          </button>
        </div>
      </nav>

      <main className="content">
        {!account ? (
          <Notice kind="info">No account was found for this profile.</Notice>
        ) : (
          <>
            {accounts.length > 1 && (
              <div className="field picker">
                <label htmlFor="acct">Account</label>
                <select id="acct" value={account.account_number} onChange={(e) => setSelected(e.target.value)}>
                  {accounts.map((a) => (
                    <option key={a.account_number} value={a.account_number}>
                      {a.account_number}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {view === "home" && (
              <Home
                me={me}
                account={account}
                firstName={firstName}
                tick={tick}
                setView={setView}
                hidden={hidden}
                onToggle={toggleHidden}
              />
            )}
            {view === "send" && (
              <SendMoney
                key={account.account_number}
                account={account}
                me={me}
                hideBalance={hidden}
                onSent={() => void afterTransfer()}
                onGoSecurity={() => setView("security")}
              />
            )}
            {view === "ledger" && (
              <section className="stack">
                <h1 className="page-title">Ledger</h1>
                <p className="muted">Every entry on account {account.account_number}, newest first.</p>
                <div className="panel">
                  <Statement accountNumber={account.account_number} refreshToken={tick} />
                </div>
              </section>
            )}
            {view === "security" && <Security me={me} onChanged={() => void load()} />}
          </>
        )}
      </main>
    </div>
  );
}

interface HomeProps {
  me: Me;
  account: Account;
  firstName: string;
  tick: number;
  setView: (v: View) => void;
  hidden: boolean;
  onToggle: () => void;
}

function Home({ me, account, firstName, tick, setView, hidden, onToggle }: HomeProps) {
  const { whole, frac } = splitNaira(account.balance_kobo);
  return (
    <section className="stack">
      <h1 className="page-title">
        {greeting()}, {firstName}
      </h1>

      <div className="panel hero settle">
        <p className="muted">Savings account {account.account_number}</p>
        <div className="balance-row">
          {hidden ? (
            <p className="figure masked" aria-label="Balance hidden">
              <span className="cur">₦</span>••••••
            </p>
          ) : (
            <p className="figure" aria-label={`Balance ${formatNaira(account.balance_kobo)}`}>
              <span className="cur">₦</span>
              {whole}
              <span className="frac">.{frac}</span>
            </p>
          )}
          <button
            className="eye"
            type="button"
            onClick={onToggle}
            aria-pressed={hidden}
            aria-label={hidden ? "Show balance" : "Hide balance"}
            title={hidden ? "Show balance" : "Hide balance"}
          >
            {hidden ? <EyeOffIcon /> : <EyeIcon />}
          </button>
        </div>
        <dl className="limits">
          <div>
            <dt>Daily sending limit</dt>
            <dd>{formatNaira(me.daily_limit_kobo)}</dd>
          </div>
          <div>
            <dt>Highest balance allowed</dt>
            <dd>{formatNaira(me.max_balance_kobo)}</dd>
          </div>
          <div>
            <dt>Verification</dt>
            <dd>
              Tier {me.tier}, {me.tier_name}
            </dd>
          </div>
        </dl>
      </div>

      {account.status !== "ACTIVE" && (
        <Notice kind="error">This account is {account.status.toLowerCase()}, so transfers are paused.</Notice>
      )}

      {!me.pin_set && (
        <div className="panel banner">
          <p>Set a transaction PIN to start sending money.</p>
          <button className="btn btn-primary" onClick={() => setView("security")}>
            Set PIN
          </button>
        </div>
      )}

      <div className="panel">
        <div className="banner">
          <h2 className="section-title">Recent activity</h2>
          <button className="link-btn" onClick={() => setView("ledger")}>
            See the full ledger
          </button>
        </div>
        <Statement accountNumber={account.account_number} compact refreshToken={tick} />
      </div>
    </section>
  );
}
