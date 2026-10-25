# GiftBridge Ethiopia v0.5 — Digital Gifts + Merchant Ecosystem

> **LOCAL DEVELOPMENT SANDBOX ONLY.** No real gift value, funds, M-PESA, telebirr, Dashen Bank, SMS, bank settlement, customer identity verification, merchant KYC or business partnerships. Names of existing businesses in demo seed data are **illustrative, not endorsements or integrations**. Never put this demo on the public internet or enter real personal/financial information. `APP_ENV=production` deliberately refuses to start.

GiftBridge is a FastAPI + PostgreSQL/SQLite + responsive HTML/CSS/JavaScript gifting prototype for Ethiopian merchant-specific and multi-merchant universal gift cards. It runs locally on Windows and demonstrates payments (simulated only), personalized gifts, wallets, partial redemption and merchant workflows.

## New in v0.5

- **Merchant application portal**: registered customers submit business name, category, location, contact and description. An admin approves/rejects, with a visible application timeline and inbox notification. No actual document review/KYC is implemented.
- **Merchant ownership**: approved applicant becomes the demo merchant **OWNER**, with an automatically created main branch.
- **Team management**: merchant owners can assign MANAGER or branch-specific CASHIER permissions to *registered accounts*. Managers can assign cashiers; they cannot grant manager/owner access. Owners can deactivate team members. Old v0.4 cashier assignments remain supported.
- **Merchant gift publishing**: owner/manager can publish merchant-specific campaigns. Universal programs remain restricted to platform admin.
- **Branch administration**: owner/manager creates branches and ties cashiers to specific branches.
- **QR-assisted POS**: gift owner can show QR containing the card identifier and separately a five-minute, one-time redemption PIN. Camera scanning with `BarcodeDetector` where supported; fallback to manual card-code entry. Authorized branch is enforced for new cashiers.
- **Merchant analytics**: last 7/30/90/365 days, merchant-specific gift sales, redeemed value, simulated fees/payables, daily trend and branch breakdown. CSV redemption export from v0.4 remains available.
- **Audit and compatibility**: new tables for applications, scoped staff and redemption locations without altering old gift/ledger columns. Automated permission, payment, redemption and data-preservation tests.

## Screenshots

See `docs/preview-v05-merchant-application.png`, `docs/preview-v05-admin-review.png`, `docs/preview-v05-merchant-studio.png`.

## Installation — Windows 11

Requires Python 3.11+ with `python` or `py` in your PATH and an internet connection **on first installation** to download Python packages.

1. Extract the ZIP and open its `giftbridge` folder.
2. Double-click `run.bat` for first-time setup. It creates `.venv`, installs dependencies, seeds demo users and opens the local server.
3. Open http://127.0.0.1:8000 and leave the terminal window open while using GiftBridge.
4. Stop with Ctrl+C. The next run is again one click using `run.bat`.

Manual PowerShell commands from the GiftBridge project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m backend.seed
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

For an **existing v0.4 project**, read **[UPGRADE_FROM_V04.md](docs/UPGRADE_FROM_V04.md)**. Keep your `.git`, `.venv`, `.env` and `giftbridge.db` untouched and back up the DB before copying the updated code.

## Demo accounts

All seeded local example accounts use password `DemoPass123!`:

| Role | Phone |
|---|---|
| Platform administrator | `251900000001` |
| Customer | `251900000002` |
| Gift recipient | `251900000003` |
| Legacy Queens demo cashier | `251900000004` |

For self-service onboarding, register a new customer account, apply as a merchant, switch to the demo admin account to approve it, and sign in as the applicant again.

## Full demo workflow

1. Merchant owner applies through **Become a merchant**.
2. Admin approves through **Management**; the merchant gets a primary branch.
3. Merchant owner publishes a gift and assigns registered cashiers to specific branches.
4. Customer selects a gift, occasion, design, recipient, amount and personal message.
5. Checkout simulates **SUCCESS** or **FAILED**. Only SUCCESS issues a card; repeated success does not duplicate value.
6. Recipient receives an in-app inbox notification and opens the gift in **My wallet**.
7. Recipient requests **Redeem PIN**. The modal displays an 8-digit, 5-minute PIN and QR card identifier. PIN is never encoded in the QR.
8. Cashier selects their branch, scans/enters card code and PIN, and redeems part or all of the demo balance.
9. Merchant owner checks historical redemptions, branch breakdown, trends, and simulated payable amounts.

## Automated testing

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The tests use a disposable SQLite database outside your project. They cover merchant application approval/rejection, authorization, owner/manager/cashier powers, branch scoping, QR generation, duplicate transaction protection, ledger balancing, existing v0.4 functionality, and private receipts. A separate browser harness has been used to walk through application → approval → merchant studio.

## Repository layout

```text
giftbridge/
  backend/main.py           # FastAPI endpoints, permissions, DB models
  backend/seed.py           # Demo accounts and programs
  frontend/index.html       # Customer, merchant, admin and POS pages
  frontend/app.js           # Core customer/checkout/redemption JS
  frontend/merchant-v05.js  # Merchant v0.5 forms, reports, QR camera
  frontend/style.css        # Responsive styling
  tests/                    # Automated API tests
  docs/UPGRADE_FROM_V04.md  # Preservation and upgrade instructions
  launcher.py               # Browser/server launcher
  run.bat                   # Windows one-click development server
```

## Real-world limitations and security caveats

This is a demonstrator, **not production-ready fintech**. There is no phone verification, legally adequate business verification/KYC, bank/card/payment gateway, cash custody, tax invoicing, real merchant settlement, physical-card digitization, gift resale/exchange, or verified electronic delivery to unregistered people. Auth uses a development-only JWT secret and browser session storage; default demo accounts are known. Customer balance and simulated ledger use SQLite in the default local setup. Bank-grade concurrency, signed payment webhooks, fraud prevention, secrets and key management, legal review, data protection controls, accessibility audit and external security testing are still required. Do not use with real customers or real money.

Merchant staff permissions in this version are for the **demo merchant ecosystem**. Older v0.4 admins can still create a merchant manually without assigning an owner. Older demo cashier grants remain valid for backward compatibility and don't have historical branch details.

**GiftBridge Ethiopia — Send moments, not just money.**
