# GiftBridge Ethiopia v0.6 — Payment Readiness & Fraud Controls

> **LOCAL DEVELOPMENT SANDBOX ONLY — NOT FOR REAL PAYMENTS, REAL GIFT VALUE, PUBLIC DEPLOYMENT OR LIVE CUSTOMERS.** The platform has NO bank, M-PESA, telebirr or card-network connections. All gift balances, payment references and settlement reports are simulated. Names of merchants and payment channels are illustrative; no business partnerships or endorsements exist. This build intentionally **refuses to start** if `APP_ENV=production`.

**What's in GiftBridge:** A responsive customer and merchant web application, built with FastAPI + SQLAlchemy + SQLite (default) or PostgreSQL (configurable), supporting merchant applications, approval, gift issuance, gifting, universal and merchant-only programs, POS redemption with one-time PIN, and **v0.6 sandbox payment-intent processing, fraud alerts and ledger reconciliation**.

## Quick start: Windows

1. Extract this archive and open the `giftbridge` folder.
2. **First time:** Double-click `run.bat` to set up `.venv`, install requirements and seed demo accounts.
3. Open `http://127.0.0.1:8000` if the browser doesn't open automatically.
4. Stop with `Ctrl+C`. Later runs are just `run.bat` again.

Manual commands from the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m backend.seed
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

**Upgrading your own v0.5 GitHub project?** Read [`docs/UPGRADE_FROM_V05.md`](docs/UPGRADE_FROM_V05.md). **Back up `giftbridge.db` before replacing code.** Keep `.git`, `.venv`, local `.env` and database files; the new release adds four tables without deleting old v0.5 tables. Validate on a copy before trusting your existing data.

## Demo logins

| Role | Phone | Password |
|---|---|---|
| Administrator | `251900000001` | `DemoPass123!` |
| Customer | `251900000002` | `DemoPass123!` |
| Recipient | `251900000003` | `DemoPass123!` |
| Legacy sample cashier | `251900000004` | `DemoPass123!` |

> These credentials are public and only suitable for a local demo. Register new demo users to test merchant applications, assignment and approval.

## What's new in v0.6

### Payment-intent engine

- **Step 1:** Creates a **PENDING** intent with an idempotency key (`POST /api/payments/intents`).
- **Step 2:** Simulates a provider result (`POST /api/payments/intents/{id}/simulate`) with `SUCCESS` or `FAILED`.
- **Step 3:** Atomically transitions order status, records a separate payment event, and **issues exactly one gift only after success**.
- Retries start from FAILED → PENDING; successful payments and replayed events do not issue duplicate cards.
- The prior v0.5 `/api/orders/{id}/simulate-payment` endpoint is retained for compatibility, but rejects orders with pending v0.6 intents.
- A **signed sandbox webhook example** is supplied for integration exercises. It is disabled by default. **Do not interpret it as a ready-to-use M-PESA, telebirr or bank integration.**

### Fraud & reconciliation operations

Admin → **Management** → **Risk & reconciliation center**:

- Reconcile paid order value, issued cards, remaining gift liabilities, redemption totals, balanced ledger entries, simulated merchant payables and platform fees.
- Review payment activity (new v0.6 intents), incident alerts and mark alerts INVESTIGATING / RESOLVED / FALSE_POSITIVE with a reason.
- `GBF001` high-value simulated gift (>= ETB 10,000), `GBF002` three payment failures in one hour, `GBF003` three incorrect redemption PIN attempts. Thresholds are **demonstration rules, not calibrated fraud controls**.
- Login safeguards: five invalid passwords within 15 minutes lock the phone account for 15 minutes (demo only).
- Basic security headers and `Cache-Control: no-store` on API responses.

### Existing v0.5 functionality preserved

Merchant applications and approvals, owner/manager/cashier permissions, branch-scoped POS, QR+PIN redemption, merchant reports, favorites, personalized gift cards, wallet transfers, receipts, and demo settlement preview.

## Demo walkthrough

1. Sign in as customer `251900000002` and choose **Queens Gift (Demo)**.
2. Fill recipient `251900000003`, a message and any amount (e.g., **ETB 10,500**, to demonstrate the high-value alert).
3. Check out; select **M-PESA (simulated)** or another **simulated** method; click **Simulate successful payment**.
4. A payment intent and provider event are recorded, **no real money moves**, and the recipient gets the gift.
5. Sign in as recipient to check **My wallet**; use the QR and one-time PIN for a redemption with an authorized cashier.
6. Sign in as admin `251900000001`, open **Management**, and scroll to **Risk & reconciliation center**. Verify the reconciliation status and review `GBF001`.
7. In demo-only scenarios, test failed payments and click **Retry payment** under My orders.

## Running tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The tests use an isolated temporary SQLite database, not your `giftbridge.db`. They exercise payment-intent idempotency, failed-payment retry, signed simulated webhook integrity and replay protection, account lockout, admin authorization, fraud alerts, ledger reconciliation, merchant and customer flows, branch permissions, and existing voucher redemption behavior.

Additional docs: [`docs/PAYMENTS_RISK_AND_LIMITATIONS.md`](docs/PAYMENTS_RISK_AND_LIMITATIONS.md), [`docs/UPGRADE_FROM_V05.md`](docs/UPGRADE_FROM_V05.md) and [`CHANGELOG.md`](CHANGELOG.md).

## Configuration

Read `.env.example` for available variables. This project does not auto-load `.env`; export variables in your shell or through your local environment. The **sandbox webhook** is disabled unless `ENABLE_SANDBOX_WEBHOOK=true` and a sufficiently long `SANDBOX_WEBHOOK_SECRET` is set. Keep secrets out of Git.

## Limitations that remain before any real launch

- No real licensed issuer, wallet or payment gateway integration. The signed sandbox webhook is **not** a real provider callback.
- No merchant KYC, phone-number verification, OTP, AML screening, sanctions screening, data privacy review, operational settlement or banking reconciliation.
- Known seeded credentials, default development JWT secret, JWT in browser `sessionStorage`, and basic heuristics are **not production-grade**.
- SQLite demo concurrency is not a substitute for a hardened PostgreSQL transaction engine under load; dedicated migrations, financial ledgers, audit/observability, full penetration testing, secrets management and disaster recovery are required.
- **Universal gift card issuance and marketplace exchange require business and regulatory review, issuer agreements and authorized settlement arrangements before live operation.**

**GiftBridge Ethiopia — Send moments, not just money.**
