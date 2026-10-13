# Auveria Web

React + TypeScript customer app for Auveria Bank (dark, ledger-inspired).
Sign in or open an account, see your balance and limits, send money (name
enquiry, PIN, and an SMS code for larger amounts), read your ledger, and
manage your PIN.

## Run it

1. Start the Django backend (in the `auveria-bank` folder):

       python manage.py runserver

2. In this folder:

       npm install
       npm run dev

3. Open http://localhost:5173

The Vite dev server forwards `/api` to Django on port 8000, so no CORS setup is
needed. In development the "SMS" code is printed in the Django terminal.

## Two ways in

- **Customers** sign in with their phone number and see the customer app. The eye icon beside the balance hides it (remembered between visits).
- **Tellers** sign in with their staff username (for example your Django superuser) and get the cash desk: look up an account, review, then confirm a deposit or withdrawal, plus a journal of cash movements.

## Notes

- Amounts are integer kobo end to end; `src/money.ts` is the only place that formats or parses naira.
- Every transfer carries an `Idempotency-Key` that only changes when the details change, so a retry can't pay twice.
- The token is kept in `localStorage`, which is fine for a portfolio demo. A production app would prefer short-lived tokens in httpOnly cookies.
- `npm run build` type-checks the project and produces `dist/`.
