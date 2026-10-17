export interface Account {
  account_number: string;
  owner_name: string;
  status: string;
  balance_kobo: number;
  balance_display: string;
}

export interface Me {
  full_name: string;
  phone: string;
  tier: number;
  tier_name: string;
  daily_limit_kobo: number | null;
  max_balance_kobo: number | null;
  pin_set: boolean;
  otp_threshold_kobo: number;
}

export interface LedgerRow {
  reference: string;
  type: string;
  direction: "DEBIT" | "CREDIT";
  amount_kobo: number;
  amount_display: string;
  created_at: string;
}

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface TransferResult {
  reference: string;
  type: string;
  status: string;
  amount_kobo: number;
}

export interface Whoami {
  role: "staff" | "customer" | "none";
  name: string;
}

export interface StaffAccount extends Account {
  tier: number | null;
  recent: LedgerRow[];
}

export interface JournalEntry {
  reference: string;
  type: string;
  account_number: string;
  account_name: string;
  amount_kobo: number;
  amount_display: string;
  created_at: string;
}

export interface CashJournal {
  net_cash_kobo: number;
  net_cash_display: string;
  entries: JournalEntry[];
}
