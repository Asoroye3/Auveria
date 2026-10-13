# What a real deployment would still need

Auveria is a portfolio project. This list is deliberate: it separates what the code demonstrates from what
a licensed institution would have to add. Regulatory points are things to **check against current rules**, not
statements of what the rules are.

## Regulation and licensing

- A license and the regulator's approval to operate. Nothing here is, or implies, a licensed bank.
- Confirm current KYC tier definitions and limits. Tier 1 figures came from industry write-ups, and Tier 2 and
  Tier 3 values are placeholders.
- Anti-money-laundering controls: sanctions and watch-list screening, transaction monitoring, and the
  suspicious and currency transaction reporting that applies to the institution.
- Data protection compliance, including consent, retention, and breach procedures under Nigerian data
  protection law.
- A real bank code. `777` is a placeholder and must not clash with an assigned code.

## Integrations that are mocked

- **Identity:** BVN and NIN lookups need access through an authorized channel (a licensed institution or an
  approved aggregator). The mock is deterministic and for demos only.
- **Interbank transfers:** no NIBSS Instant Payment integration. `transfer()` is internal-only, and an abstract
  payment-rail interface is the natural next seam.
- **SMS:** the console provider prints codes. A real gateway, delivery receipts, and fallback channels are needed,
  and SMS-based OTP has known weaknesses (SIM swap), so an app-based second factor would be better.

## Security hardening

- The development `SECRET_KEY` and `DEBUG=1` default must be replaced by environment-driven settings, with
  `ALLOWED_HOSTS`, HTTPS, secure cookies and HSTS.
- Tokens live in `localStorage`. Production should use short-lived tokens or httpOnly cookies with CSRF protection.
- Staff accounts need two-factor authentication, least-privilege roles (teller, supervisor, compliance) instead of a
  single `is_staff` flag, and a maker-checker rule for large cash movements.
- Rate limiting at the edge, bot protection on registration and login, and account lockout policy.
- Secrets management, encrypted backups, database role separation, and dependency and container scanning.
- An append-only **audit log** of who did what and when, covering staff actions and failed attempts.

## Ledger and product depth

- Reversals and refunds as first-class operations, plus dispute handling.
- Fees, interest, standing orders, statements as PDFs, and end-of-day processing.
- A general-ledger chart of accounts beyond a single cash vault. The vault is a hot row that serializes all cash
  movements, and real systems split it by branch or till.
- Scheduled `reconcile` runs with alerting, and outbox-style delivery for notifications so an SMS failure can't
  leave a half-finished operation.

## Operations

- Monitoring, structured logging, tracing, and alerts on reconcile failures, lock timeouts and error rates.
- Backups with tested restores, a disaster-recovery plan, and zero-downtime migrations.
- Load testing well beyond the current concurrency tests, and a CI pipeline that runs the full suite against
  PostgreSQL on every change.
