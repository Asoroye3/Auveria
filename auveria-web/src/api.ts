import type { Account, CashJournal, LedgerRow, Me, Page, StaffAccount, TransferResult, Whoami } from "./types";

const TOKEN_KEY = "auveria.token";

// Empty in development (Vite proxies /api to Django). On Vercel, set VITE_API_BASE
// to the backend's address, for example https://auveria-bank.vercel.app
const API_BASE: string = ((import.meta.env.VITE_API_BASE as string | undefined) ?? "").replace(/\/$/, "");

export const tokenStore = {
  get: (): string | null => localStorage.getItem(TOKEN_KEY),
  set: (token: string): void => localStorage.setItem(TOKEN_KEY, token),
  clear: (): void => localStorage.removeItem(TOKEN_KEY),
};

export class ApiError extends Error {
  status: number;
  data: Record<string, unknown>;

  constructor(status: number, message: string, data: Record<string, unknown>) {
    super(message);
    this.status = status;
    this.data = data;
  }

  get otpRequired(): boolean {
    return this.data.otp_required === true;
  }

  get attemptsRemaining(): number | undefined {
    const left = this.data.attempts_remaining;
    return typeof left === "number" ? left : undefined;
  }
}

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(handler: () => void): void {
  onUnauthorized = handler;
}

function messageFrom(status: number, data: Record<string, unknown>): string {
  if (typeof data.error === "string") return data.error;
  if (typeof data.detail === "string") return data.detail;
  const parts: string[] = [];
  for (const [field, value] of Object.entries(data)) {
    if (Array.isArray(value)) parts.push(`${field}: ${value.join(" ")}`);
  }
  return parts.length > 0 ? parts.join("; ") : `Request failed (${status})`;
}

export function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    const left = err.attemptsRemaining;
    if (left !== undefined) return `${err.message}. ${left} ${left === 1 ? "attempt" : "attempts"} left.`;
    return err.message;
  }
  return err instanceof Error ? err.message : "Something went wrong";
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  auth?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...(options.headers ?? {}) };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const token = tokenStore.get();
  if (options.auth !== false && token) headers.Authorization = `Token ${token}`;

  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/v1${path}`, {
      method: options.method ?? "GET",
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check that the Django server is running.", {});
  }

  let data: Record<string, unknown> = {};
  try {
    data = await res.json();
  } catch {
    // empty or non-JSON body
  }

  if (!res.ok) {
    if (res.status === 401 && options.auth !== false && onUnauthorized) onUnauthorized();
    throw new ApiError(res.status, messageFrom(res.status, data), data);
  }
  return data as unknown as T;
}

export interface TransferBody {
  from_account: string;
  to_account: string;
  amount_kobo: number;
  pin: string;
  otp?: string;
}

export type OtpRequestBody =
  | { purpose: "TRANSFER"; from_account: string; to_account: string; amount_kobo: number }
  | { purpose: "PIN_CHANGE" };

export const api = {
  register: (body: { bvn: string; nin: string; phone: string; password: string }) =>
    request<{ token: string; account_number: string }>("/auth/register/", { method: "POST", body, auth: false }),

  login: (phone: string, password: string) =>
    request<{ token: string }>("/auth/login/", { method: "POST", body: { phone, password }, auth: false }),

  whoami: () => request<Whoami>("/whoami/"),

  me: () => request<Me>("/me/"),

  accounts: () => request<Account[]>("/accounts/"),

  lookup: (accountNumber: string) =>
    request<{ account_number: string; account_name: string }>(`/accounts/lookup/${accountNumber}/`),

  statement: (accountNumber: string, page: number) =>
    request<Page<LedgerRow>>(`/accounts/${accountNumber}/transactions/?page=${page}`),

  setPin: (body: { pin: string; current_pin?: string; otp?: string }) =>
    request<{ detail: string }>("/pin/", { method: "POST", body }),

  requestOtp: (body: OtpRequestBody) =>
    request<{ detail: string; sent_to: string; expires_in_seconds: number; demo_code?: string }>("/otp/request/", {
      method: "POST",
      body,
    }),

  staffAccount: (accountNumber: string) => request<StaffAccount>(`/staff/accounts/${accountNumber}/`),

  cashJournal: () => request<CashJournal>("/staff/cash-journal/"),

  staffCash: (
    kind: "deposits" | "withdrawals",
    body: { account_number: string; amount_kobo: number },
    idempotencyKey: string,
  ) =>
    request<TransferResult>(`/staff/${kind}/`, {
      method: "POST",
      body,
      headers: { "Idempotency-Key": idempotencyKey },
    }),

  transfer: (body: TransferBody, idempotencyKey: string) =>
    request<TransferResult>("/transfers/", {
      method: "POST",
      body,
      headers: { "Idempotency-Key": idempotencyKey },
    }),
};
