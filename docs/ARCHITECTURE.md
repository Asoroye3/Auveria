# Architecture

## Components

```mermaid
flowchart LR
  subgraph Browser
    Web["auveria-web: React + TypeScript"]
  end
  subgraph Django["auveria-bank: Django + DRF"]
    API["api: auth, PIN, OTP gate, transfers, teller"]
    KYC["kyc: customers, tiers, identity checks"]
    ACC["accounts: NUBAN accounts"]
    LED["ledger: double-entry, cash, reconcile"]
    SEC["security: one-time codes"]
  end
  DB[("PostgreSQL")]
  IDP["Identity provider (mock BVN/NIN)"]
  SMS["SMS provider (console mock)"]
  Web -->|"JSON over /api/v1"| API
  API --> KYC
  API --> ACC
  API --> LED
  API --> SEC
  KYC --> IDP
  SEC --> SMS
  KYC --> DB
  ACC --> DB
  LED --> DB
  SEC --> DB
```

The browser only talks to the API. In development, Vite proxies `/api` to Django, so no CORS configuration is
needed. The identity and SMS providers sit behind small interfaces (`apps/kyc/providers.py`,
`apps/security/providers.py`) and are selected by settings.

## Data model

```mermaid
erDiagram
  TIER ||--o{ CUSTOMER : "sets limits for"
  CUSTOMER ||--o{ ACCOUNT : owns
  ACCOUNT ||--o{ LEDGER_ENTRY : has
  TRANSACTION ||--|{ LEDGER_ENTRY : contains
  CUSTOMER ||--o{ ONE_TIME_CODE : receives

  TIER {
    int code
    bigint daily_limit_kobo
    bigint max_balance_kobo
  }
  CUSTOMER {
    string full_name
    string bvn_last4
    string identity_hash
    string pin_hash
  }
  ACCOUNT {
    string account_number
    bigint balance_kobo
    string status
    bool is_system
  }
  TRANSACTION {
    string reference
    string idempotency_key
    string type
    string status
  }
  LEDGER_ENTRY {
    string direction
    bigint amount_kobo
  }
  ONE_TIME_CODE {
    string purpose
    string context_hash
    string code_hash
    int attempts
  }
```

`Account.balance_kobo` is a cache. The ledger is the source of truth, and `reconcile` checks the two agree.
The **cash vault** is a system account: deposits debit it and withdrawals credit it, so it runs negative by exactly
the net cash customers have handed in. Because every transaction balances, the sum of all account balances is
always zero.

## A large transfer, step by step

```mermaid
sequenceDiagram
  participant App as Web app
  participant API
  participant Codes as One-time codes
  participant SMS
  participant Ledger

  App->>API: POST /otp/request (from, to, amount)
  API->>Codes: issue code bound to this exact transfer
  Codes->>SMS: text the code to the customer
  App->>API: POST /transfers (PIN, code, Idempotency-Key)
  API->>API: replay check: same key already done?
  API->>API: verify PIN (lockout after 5 wrong tries)
  API->>Codes: verify and consume code
  API->>Ledger: transfer()
  Ledger->>Ledger: lock both accounts in id order
  Ledger->>Ledger: check status, tier limits, funds
  Ledger->>Ledger: write debit and credit entries, update balances
  Ledger-->>API: transaction
  API-->>App: 201 with reference
```

Transfers below the OTP threshold skip the code steps. A retry with the same `Idempotency-Key` returns the
original result without asking for a new PIN or code.

## Guarantees and how they're enforced

| Guarantee | Mechanism | Tested by |
| --- | --- | --- |
| Entries per transaction sum to zero | `transfer()` always writes one debit and one credit | `reconcile` plus ledger tests |
| Ledger entries can't be edited | `save()` and `delete()` raise on existing entries; read-only admin | `test_ledger_entries_are_immutable` |
| No overdraft under parallel requests | Row locks (`SELECT ... FOR UPDATE`) and a funds check under the lock | `ConcurrencyTests` (PostgreSQL) |
| No double charge on retries | Unique idempotency key, checked after locking | API and concurrency tests |
| No deadlocks between opposite transfers | Locks always taken in account-id order | opposite-direction concurrency test |
| Limits can't be raced | Daily total is read after the sender's row is locked | parallel daily-limit test |
| A code can't approve a different transfer | The code carries a hash of (from, to, amount) | OTP service and API tests |

## Project conventions

- Amounts are integer kobo in the database, the API (`amount_kobo`) and the frontend. `₦` formatting happens in
  `apps/accounts/money.py` and `auveria-web/src/money.ts` only.
- Staff and customers share one login endpoint. `GET /api/v1/whoami/` tells the app which interface to show.
- Settings hold everything environment-specific: bank name and code, KYC tiers, provider classes, OTP limits.
