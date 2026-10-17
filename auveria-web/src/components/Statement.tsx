import { useEffect, useState } from "react";
import { api, describeError } from "../api";
import type { LedgerRow, Page } from "../types";
import { Notice } from "./ui";

const LABELS: Record<string, string> = {
  TRANSFER: "Transfer",
  DEPOSIT: "Cash deposit",
  WITHDRAWAL: "Cash withdrawal",
};
const PAGE_SIZE = 20;
const COMPACT_ROWS = 5;

function formatWhen(iso: string): string {
  return new Date(iso).toLocaleString("en-NG", {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

interface Props {
  accountNumber: string;
  compact?: boolean;
  refreshToken?: number;
}

export default function Statement({ accountNumber, compact = false, refreshToken = 0 }: Props) {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Page<LedgerRow> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let stale = false;
    setError(null);
    api
      .statement(accountNumber, page)
      .then((d) => {
        if (!stale) setData(d);
      })
      .catch((e) => {
        if (!stale) setError(describeError(e));
      });
    return () => {
      stale = true;
    };
  }, [accountNumber, page, refreshToken]);

  if (error) return <Notice kind="error">{error}</Notice>;
  if (!data) return <p className="muted">Loading activity…</p>;

  const rows = compact ? data.results.slice(0, COMPACT_ROWS) : data.results;
  if (rows.length === 0) {
    return <p className="muted">No activity yet. Deposits and transfers will be listed here as they happen.</p>;
  }

  const totalPages = Math.max(1, Math.ceil(data.count / PAGE_SIZE));

  return (
    <div>
      <table className="ledger">
        <thead>
          <tr>
            <th scope="col">Activity</th>
            <th scope="col" className="num">Out</th>
            <th scope="col" className="num">In</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.reference}-${r.direction}`}>
              <td>
                <span className="what">{LABELS[r.type] ?? r.type}</span>
                <span className="when">
                  {formatWhen(r.created_at)}, ref {r.reference.slice(0, 8)}
                </span>
              </td>
              <td className="num out">{r.direction === "DEBIT" ? r.amount_display : ""}</td>
              <td className="num in">{r.direction === "CREDIT" ? r.amount_display : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {!compact && totalPages > 1 && (
        <div className="pager">
          <button className="btn btn-quiet" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            Newer
          </button>
          <span className="muted">
            Page {page} of {totalPages}
          </span>
          <button className="btn btn-quiet" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
            Older
          </button>
        </div>
      )}
    </div>
  );
}
