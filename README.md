# Pharmacy Inventory Management System

A server-rendered Django application for pharmacy inventory, point of sale, purchasing, prescriptions, reporting, and demand forecasting. The interface uses Tailwind CSS with a shadcn/ui-inspired neutral theme and Bootstrap Icons.

## Features

- **Inventory** — medicines, categories, suppliers, batches, FEFO stock deduction, stock ledger, adjustments, write-offs, and expiry management.
- **Point of sale** — server-side pricing, barcode entry, customer lookup, FEFO batch allocation, senior citizen/PWD VAT-exempt discounts, loyalty points, receipts, returns, and voids.
- **Purchasing** — draft/ordered purchase orders, receive-once stock posting, supplier lead times, and cancellation.
- **Customers and prescriptions** — customer profiles, purchase history, loyalty balances, and prescription records.
- **Reports and exports** — inventory, low stock, near expiry, sales, and purchases reports with filtered Excel downloads.
- **Forecasting** — weekly demand series, exponential smoothing with holdout error, safety stock, lead-time reorder points, and stock cover.
- **Operations and security** — role-based capabilities, audit log, optional TOTP two-factor authentication, password reset, expiry write-off command, and alert email digest.

## Setup

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py createsuperuser
.\venv\Scripts\python.exe manage.py runserver
```

Open <http://127.0.0.1:8000/accounts/login/> and sign in. Superusers can reach every page; other staff are limited by the roles below.

> Use `.\venv\Scripts\python.exe` for every command (or activate the venv first). If you run `python manage.py ...` and see `ModuleNotFoundError: No module named 'pyotp'`, that command is using a different Python installation. Re-run it with the venv interpreter or install the dependencies into that interpreter with `python -m pip install -r requirements.txt`.

## Roles

| Role | Access |
| --- | --- |
| Administrator | All pages, users, audit log, voids, reports, settings |
| Pharmacist | Inventory, purchasing, POS, returns, prescriptions, reports, forecasting |
| Cashier | POS, sales, customers |
| Inventory clerk | Inventory, batches, purchase receipts, stock adjustments |

Capabilities are defined in `core/permissions.py`. Views use `@capability_required(...)`; superusers bypass capability checks.

## Two-factor authentication

Every user can enable TOTP 2FA from **Security** in the sidebar. Add the displayed setup key to an authenticator app, then confirm a current 6-digit code. When enabled, sign-in asks for the code after the password. Disabling 2FA requires both the account password and a valid code.

## Scheduled operations

Run these from Task Scheduler/cron in production (they are safe to run daily):

```powershell
# Write off expired batches and record the loss in the stock ledger
.\venv\Scripts\python.exe manage.py expire_batches

# Preview expired stock without changing anything
.\venv\Scripts\python.exe manage.py expire_batches --dry-run

# Email low-stock and near-expiry digest to ALERT_EMAILS
.\venv\Scripts\python.exe manage.py send_alerts

# Print the digest instead of sending email
.\venv\Scripts\python.exe manage.py send_alerts --dry-run
```

Set `EMAIL_BACKEND`, `EMAIL_HOST`, and related values in `.env` to deliver alert and password-reset email. `ALERT_EMAILS` is a comma-separated recipient list.

The email backend is selected automatically: once `EMAIL_HOST_PASSWORD` is set, Django uses SMTP; otherwise it uses the **console backend**, which prints password-reset links in the terminal running `runserver` instead of delivering them. Configure SMTP in `.env` and restart the server to send real email.

## AI assistant

The assistant answers common inventory questions directly from the database: low stock, expiry windows, expired batches, medicine stock, total medicines, and sales. This keeps those facts exact even when no LLM is configured. Free-form questions use the LLM. Set `GROQ_API_KEY` (and optionally `LLM_MODEL`, `LLM_PROVIDER`, `LLM_BASE_URL`) to enable natural-language answers; without a key, LLM-backed questions return a configuration message. Non-admin users only receive sales context they are allowed to see.

## Development checks

```powershell
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py test
```

The test suite covers FEFO allocation, stock ledger integrity, purchase receiving, VAT-exempt discounts, returns/voids, role permissions, 2FA, password reset, forecasting, and the assistant's deterministic inventory answers.

## Production notes

- Set `DJANGO_DEBUG=False`, a unique `DJANGO_SECRET_KEY`, and real `DJANGO_ALLOWED_HOSTS`.
- Serve static files with `manage.py collectstatic` (WhiteNoise is configured).
- Enable HTTPS and set `DJANGO_SECURE_SSL_REDIRECT=True`, `DJANGO_SECURE_COOKIES=True`, and a non-zero `DJANGO_HSTS_SECONDS`.
- Back up the database and `media/` regularly.
- Treat the stock ledger (`StockMovement`) as append-only: it is the audit trail for every batch balance.
