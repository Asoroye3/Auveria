# Deploying Auveria on Vercel

Auveria deploys as **two Vercel projects from the same GitHub repo**: the Django API and the React app. Vercel
detects a Django project by finding `manage.py`, runs it as a Vercel Function, and needs an external PostgreSQL
database (its filesystem doesn't persist, so SQLite won't do).

> This is a public **demo** setup. It uses demo mode (see below), mock BVN/NIN checks, and fake data. Don't put real
> personal or financial information into it.

## 0. Before you start

- The repo is on GitHub and CI is green.
- You have a Vercel account connected to GitHub.
- You can run the backend locally (you'll use it to prepare the cloud database).

## 1. Create a PostgreSQL database

Create a free database with Neon (directly at neon.tech, or through Vercel's Marketplace). Copy the **pooled**
connection string, which looks like `postgresql://user:password@host/dbname?sslmode=require`. Each serverless
invocation opens its own connection, so the pooled address matters.

## 2. Create the backend project

In Vercel: **Add New > Project**, import the repo, and set:

| Setting | Value |
| --- | --- |
| Root Directory | `auveria-bank` |
| Framework Preset | Django (detected automatically) |

Environment variables:

| Name | Value |
| --- | --- |
| `DJANGO_SECRET_KEY` | A long random string. Keep a copy: you need the same value in step 4 |
| `DJANGO_DEBUG` | `0` |
| `DATABASE_URL` | The pooled Neon connection string |
| `AUVERIA_DEMO_MODE` | `1` (shows the one-time code on screen, because no real SMS is sent) |
| `CORS_ALLOWED_ORIGINS` | Added in step 5, once you know the frontend address |

Deploy. You'll get an address like `https://auveria-bank.vercel.app`.

A random secret key can be generated with:
```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

## 3. Create the frontend project

Add a second project from the same repo:

| Setting | Value |
| --- | --- |
| Root Directory | `auveria-web` |
| Framework Preset | Vite (detected automatically) |

Environment variable:

| Name | Value |
| --- | --- |
| `VITE_API_BASE` | The backend address from step 2, with no trailing slash |

Deploy. You'll get something like `https://auveria-web.vercel.app`.

## 4. Prepare the cloud database from your own machine

The tables and demo data are created once, from your computer, pointed at the cloud database. In PowerShell, from
`auveria-bank` with the venv active:

```powershell
$env:DATABASE_URL="postgresql://...your pooled Neon string..."
$env:DJANGO_SECRET_KEY="the same value you gave the backend project"
python manage.py migrate
python manage.py seed_demo
python manage.py createsuperuser
```

Use the **same** `DJANGO_SECRET_KEY` as Vercel. Identity checks store a keyed hash of each BVN and NIN, and a
different key would make the seeded customers invisible to duplicate detection. Don't set `DJANGO_DEBUG=0` for this
step, because `seed_demo` refuses to run when DEBUG is off.

Clear the variables afterwards (or close the terminal) so later local work doesn't touch the cloud database.

## 5. Allow the frontend to call the backend

In the backend project's environment variables, set:

```
CORS_ALLOWED_ORIGINS=https://auveria-web.vercel.app
```

Use the exact frontend origin: `https://`, no path, no trailing slash. Then **redeploy the backend**, since
environment changes only apply to new deployments.

## 6. Smoke test

1. Open the frontend address and sign in as `08030000001` (password `Demo-Passw0rd!`).
2. Send ₦25,000 to the other demo account. At the code step, the app shows the code on screen because of demo mode.
3. Open `https://<backend>/admin/` and sign in with the superuser from step 4. Check the ledger entries.
4. Sign in to the frontend with the superuser's username to see the teller desk.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Browser console shows a CORS error | `CORS_ALLOWED_ORIGINS` doesn't exactly match the frontend origin, or the backend wasn't redeployed |
| `DisallowedHost` / 400 on the backend | The host isn't covered by `ALLOWED_HOSTS` (`.vercel.app` is allowed by default; add custom domains in `DJANGO_ALLOWED_HOSTS`) |
| Admin login fails with a CSRF error | Add the backend's origin to `DJANGO_CSRF_TRUSTED_ORIGINS` |
| Backend crashes at startup with "Set DJANGO_SECRET_KEY" | The secret key variable is missing |
| Database timeouts or "too many connections" | Use the pooled connection string, not the direct one |
| First request after a quiet spell is slow | Cold start on serverless; it's normal |
| Build complains about the Python version | Set a supported Python version in the Vercel project settings |
| Frontend calls hit its own address and return 404 | `VITE_API_BASE` is unset; set it and redeploy the frontend (it's baked in at build time) |

## Known limits of this deployment

- Demo mode shows codes on screen. That's right for a public demo and wrong for anything real.
- Rate limiting uses Django's in-memory cache, which is per serverless instance, so limits are looser than on a single
  server. A shared cache (Redis) would fix that.
- Changing `DJANGO_SECRET_KEY` later breaks duplicate-identity detection for existing customers and invalidates
  pending codes.
- Anyone can register on a public demo. The mock identity rules keep the data fake, but expect junk accounts.
