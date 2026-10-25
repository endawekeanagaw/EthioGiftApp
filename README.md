# GiftBridge Ethiopia v0.4 — Digital gifting experience (local sandbox)

> **DEVELOPMENT DEMO ONLY — NOT A LIVE FINTECH PRODUCT.** Every checkout and card value is simulated. There are **no real M-PESA, telebirr, Dashen Bank, SMS, physical gift card, custody, settlement, or exchange connections**. The merchant and issuer names in the app are illustrative demonstrations, not partnerships. Do not host this demo on the public internet or use it with real customer information.

GiftBridge is a Windows-friendly FastAPI + vanilla JavaScript application demonstrating merchant-specific and universal gift programs, simulated purchasing, recipient delivery, a wallet, merchant redemption, and merchant administration. v0.4 **extends v0.3**, preserving the core v0.3 tables and gift flows.

## What's new in v0.4

- Refreshed responsive storefront with categories, saved favorites, search and merchant descriptions.
- Persistent favorites for authenticated demo customers.
- Quick gift denomination buttons, occasion selection, card-theme previews and a live personal-note preview.
- Premium customer wallet with overall demo balance, search, remaining-value indicators and available/used filters.
- Share a gift *announcement* using the browser share sheet or clipboard. **A share message does not contain the gift code, PIN or access link.** Recipients still must have a registered GiftBridge demo account; gifts are delivered through their in-app wallet and inbox.
- Download branded **sandbox purchase and redemption receipts as HTML** (open and Print → Save as PDF). Receipts are permission-checked and watermarked as having no real value.
- English / Amharic toggle for **primary marketing and navigation labels**. The rest of the interface is currently English: this is *partial localization*, not a fully translated product.
- Admin can enter program category, short description and gift symbol when publishing a demo gift program.
- Added automated tests for favorites, program presentation, receipt permissions, ownership and ledger preservation.
- Updated one-click `run.bat` launcher to recognize version 0.4.0.

### Screenshots

See `docs/preview-v04-marketplace.png`, `docs/preview-v04-wallet.png` and `docs/preview-v04-mobile.png`. These screenshots are from an instrumented local browser test, not an externally hosted production environment.

## First-time setup: Windows

Requirements: Python 3.11+ installed; modern Windows browser. For GitHub use, Git is optional.

1. Extract the archive; open the **inner `giftbridge` directory** containing `run.bat`.
2. Double-click `run.bat`. It will create `.venv` if needed, install dependencies when missing, seed demo data, run the server on `127.0.0.1:8000`, and open your browser.
3. Keep the command window open while using the demo. Press **Ctrl+C** to stop it.
4. Open `http://127.0.0.1:8000` or `http://127.0.0.1:8000/docs` for API docs.

PowerShell equivalent from the project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m backend.seed
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

If port 8000 is already in use, close the other GiftBridge instance. The launcher intentionally refuses to open a different or older application responding on that port.

### Sample demo accounts

**Only use locally.** All example accounts share the password `DemoPass123!`:

| Role | Phone |
| --- | --- |
| Admin | `251900000001` |
| Buyer | `251900000002` |
| Gift recipient | `251900000003` |
| Queens demo cashier | `251900000004` |

## End-to-end demo walkthrough

1. Sign in as Buyer. Browse the gift programs and click the heart to save one.
2. Filter to **Saved gifts**, then back to **All gifts**; choose a program.
3. Select ETB 500/1,000/2,000/5,000 or a custom amount, choose a design and occasion, add a personal message, and enter recipient `251900000003`.
4. Click **Proceed to demo checkout**. Select a *simulated* channel and click **Simulate successful payment**.
5. The gift is created once, and you can download a **sandbox HTML receipt**, or share an announcement without revealing redeem credentials.
6. Sign out; sign in as Recipient. The gift is visible in **Inbox** and **My wallet**. Open the gift, view its message, and generate a single-use eight-digit redemption PIN.
7. Sign out; sign in as Cashier. Use the gift code and freshly generated PIN to partially redeem the gift at a participating demo merchant.
8. Download the redemption receipt; inspect the merchant dashboard and remaining gift balance.
9. Repeat checkout with **Simulate failed payment**, and retry using **My orders**. Failed payments create no gift.

### What is actually enforced

- Buyer permission on purchase receipts; recipient/assigned cashier/admin permission on redemption receipts.
- Favorites are unique per account and only authenticated users can change them.
- Demo payments are processed once; unsuccessful attempts cannot create gift cards.
- Authorized merchants and a short-lived owner-issued PIN are required for redemption.
- Atomic balance debit prevents overspending under competing requests in supported transaction conditions.
- Balanced **simulated** ledger entries for issuance and redemption; merchant fee is for illustration only.

### What is not implemented

Actual monetary or financial settlement, issuing bank integrations, physical card scanning and issuer verification, SMS sending, secure gift claim links to unregistered recipients, OTP phone verification, real merchant onboarding/KYC, exchanges/resale, group funding, scheduled delivery, production user security, fully translated Amharic UI, native mobile apps or hosted production deployment.

## Existing v0.3 users: IMPORTANT

Read [`docs/UPGRADE_FROM_V03.md`](docs/UPGRADE_FROM_V03.md). Do **not** remove or replace your `.git`, `.venv`, `.env` or `giftbridge.db` file. Make a database backup before copying source files. The code adds optional supporting tables, and does not alter existing v0.3 `cards`, `gift_orders` or `redemptions` columns.

## Automated tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests use a separate temporary database (not `giftbridge.db`). Developer validation also includes a browser-harness walkthrough. The screenshots are examples, not substitutes for testing in your environment.

## Project structure

```text
giftbridge/
  backend/main.py           # SQLAlchemy schema and FastAPI endpoints
  backend/seed.py           # Idempotent demo data
  frontend/index.html       # Customer, merchant, admin UI
  frontend/style.css        # Responsive product design
  frontend/app.js           # UI flows, receipts, localization
  tests/test_flows.py       # API integration suite
  docs/UPGRADE_FROM_V03.md  # Windows / GitHub update instructions
  launcher.py               # Browser and server readiness
  run.bat                   # Windows one-click startup
  requirements.txt
  docker-compose.yml        # Optional local Docker demo
```

### Local-only security statement

FastAPI tokens use a development-only secret by default. Example accounts use published passwords; phone registration does not verify phone ownership; browser tokens are kept in session storage. Do not put real customer, bank or gift-card secrets into this prototype. The backend intentionally raises an error when `APP_ENV=production`.

Before a real rollout you would need verified user identity, hardened authentication and session management, TLS, secret rotation, audits, rate limits, monitoring, a payment partner's signed callback flows, payment and gift reconciliation, security testing, operational controls, legal review, and necessary licensing or regulated partners.

---
**GiftBridge Ethiopia — Make gifting feel personal.**
