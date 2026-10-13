# Auveria Bank

Portfolio core-banking backend (Django). Nigeria-first: NUBAN account numbers,
amounts in kobo, double-entry ledger. External rails (NIBSS/NIP, BVN/NIN) are
mocked/sandboxed.

## Setup (Windows PowerShell)

    python -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    python manage.py makemigrations kyc accounts ledger security api
    python manage.py migrate
    python manage.py test
    python manage.py createsuperuser
    python manage.py runserver   # then open http://127.0.0.1:8000/admin/

## Useful commands

    python manage.py reconcile   # verifies the ledger balances and cached balances match

## PostgreSQL + concurrency tests

SQLite is the default. For row locking and `apps/ledger/test_concurrency.py`,
point Django at PostgreSQL (PowerShell, same terminal session):

    $env:DB_NAME="auveria"
    $env:DB_USER="postgres"
    $env:DB_PASSWORD="your-password"
    python manage.py migrate
    python manage.py test

Without DB_NAME, the concurrency tests are skipped.

## API (v1)

Token auth: send `Authorization: Token <token>`. Money amounts are integer kobo.
Money-moving requests need an `Idempotency-Key` header.

| Method | Path | Who |
| --- | --- | --- |
| POST | `/api/v1/auth/register/` | anyone (BVN, NIN, phone, password) |
| POST | `/api/v1/auth/login/` | anyone (phone, password) |
| POST | `/api/v1/pin/` | customer (set PIN; changing it needs an OTP) |
| POST | `/api/v1/otp/request/` | customer (texts a one-time code) |
| GET | `/api/v1/me/` | customer (tier, limits, PIN status) |
| GET | `/api/v1/accounts/` | customer |
| GET | `/api/v1/accounts/lookup/<number>/` | customer (name enquiry) |
| GET | `/api/v1/accounts/<number>/transactions/` | customer (statement, paginated) |
| POST | `/api/v1/transfers/` | customer (PIN required) |
| POST | `/api/v1/staff/deposits/` and `/staff/withdrawals/` | staff only |

## One-time codes (OTP)

Transfers of N20,000 or more (`OTP_TRANSFER_THRESHOLD_KOBO`) and PIN changes need a
6-digit code. The code is texted to the customer, expires after 5 minutes, allows 5
guesses, and for transfers only works for the exact amount and recipient it was
requested for. In development the "SMS" is printed in the `runserver` terminal;
swap `SMS_PROVIDER` for a real gateway class later.
