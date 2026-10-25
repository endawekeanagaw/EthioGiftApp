# GiftBridge Ethiopia v0.3 — End-to-End Gifting Sandbox 🎁

GiftBridge is a **working local demonstration** of merchant-specific and universal digital gifts for Ethiopia. The new v0.3 release upgrades the v0.2 codebase with a refined gift marketplace, personalized gift designs, an unwrapping experience, an inbox, one-time redemption PINs, merchant branches, merchant reports, and a one-click Windows launcher.

> **DEMO ONLY. No real money, payment provider, financial service, verified gift value, Dashen Bank integration, or licensed settlement.** “M-PESA”, “telebirr”, and “Dashen Bank” labels inside checkout are simulated **choice labels**, not connected services. Example merchant brands are illustrative, not actual partners. The server refuses `APP_ENV=production` intentionally.

## Get running (Windows)

**Recommended: Double-click `run.bat` inside the `giftbridge` folder.**

The launcher will create `.venv` if necessary, install Python packages if missing, seed demo users and merchants, run Uvicorn, and open http://127.0.0.1:8000 when the server is ready. Requires **Python 3.11+** installed and available as `py -3` or `python`. Keep the terminal open while testing; Ctrl+C stops it.

If you prefer PowerShell:

```powershell
cd path\to\giftbridge
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m backend.seed
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

Then open **http://127.0.0.1:8000**. API docs: http://127.0.0.1:8000/docs.

### Demo sign-in accounts

All have demo password `DemoPass123!` — **never use these credentials on an internet-accessible system**.

| Role | Phone |
|---|---|
| Admin | `251900000001` |
| Buyer | `251900000002` |
| Gift recipient | `251900000003` |
| Queens demo cashier | `251900000004` |

## Walkthrough (10 steps)

1. Log in as **Buyer** (`251900000002`).
2. Under **Discover gifts**, filter or search for a merchant-specific or universal program.
3. Select a gift, enter an ETB amount, and send it to `251900000003`.
4. Select a birthday/wedding/other occasion, choose a card design, and type a message.
5. Click **Proceed to demo checkout** → choose a simulated channel → **Simulate successful payment**. A success dialog appears; no money moves.
6. Log out, then log in as **Recipient** (`251900000003`). Open **Inbox** and **My wallet**; select **Open gift ✨** to unwrap it.
7. In the wallet choose **Redeem PIN** to create a one-time eight-digit code (valid 5 minutes); note the gift card code and PIN. Generating another PIN invalidates the old one.
8. Log out and sign in as **Cashier** (`251900000004`). Choose **Cashier POS**, paste the gift code and PIN, select Queens demo merchant, enter an amount smaller than the balance, and redeem.
9. Confirm the simulated receipt and remaining balance. The recipient's Inbox receives a redemption notice.
10. Cashier opens **Merchant studio** to review transaction history or export CSV. Admin can create new merchants, gift programs, branches, and cashier assignments.

**Failure path:** Choose simulated FAILED checkout. The order remains unpaid, no gift is issued, and **My orders → Retry payment** restarts the simulated checkout.

## Features

| Feature | v0.3 scope |
|---|---|
| Digital gifts | Merchant-specific or multi-merchant universal demo gift programs |
| Gifting | Personal message, occasion, named sender, 5 selectable designs, reveal modal |
| Simulated payment | Paid/failed, failed retry, once-only issuance, attempt history |
| Wallet | Gift balances, transfers between registered users, histories, summary |
| Inbox | Received, issued, transferred, redeemed events with read state |
| Redemption | Authorized cashier, one-time owner-generated 8-digit PIN, 5-minute expiry, max 5 wrong attempts, single use, partial/full redemption |
| Merchant | Branch directory, authorized POS access, transaction reporting and local CSV export |
| Admin | Merchants, programs, acceptance network, cashier assignments, branches, demo ledger and settlement reports |
| Testing | Automated API integration tests and frontend end-to-end harness during development |

## Main technologies

- **Backend:** Python, FastAPI, SQLAlchemy, Pydantic
- **Database:** SQLite by default for local testing; PostgreSQL supported via `DATABASE_URL` for development
- **Frontend:** Single-page vanilla JavaScript + responsive HTML/CSS; no npm/build step required
- **Run locally:** Uvicorn, `run.bat` + `launcher.py`; Docker Compose optional
- **Auth:** Demo password hashing and signed bearer tokens, **not hardened for production**

### Directory layout

```text
giftbridge/
├── backend/
│   ├── main.py            # Models, security, endpoints, gift/order flows
│   └── seed.py            # Demo accounts and sample merchants
├── frontend/
│   ├── index.html          # Responsive customer, cashier, admin and merchant UI
│   ├── app.js              # Browser workflow and API client
│   └── style.css           # Product design system
├── tests/test_flows.py     # API integration test suite
├── docs/                   # Optional screenshots and upgrade guide
├── launcher.py             # Readiness check; opens browser
├── run.bat                 # One-click Windows runner
├── requirements.txt
└── docker-compose.yml
```

### Run tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Uses a fresh temporary test database. The test suite does **not** use your local `giftbridge.db` file.

### Database and upgrading from v0.2

The database stays **backward-compatible** for the local sandbox because v0.3 adds new supplemental tables rather than modifying old card/order columns. Existing v0.2 orders and gift balances remain in your local `giftbridge.db` if that file is preserved.

**Always back up `giftbridge.db` before upgrading.** The release ZIP deliberately does not include any database. See [docs/UPGRADE_FROM_V02.md](docs/UPGRADE_FROM_V02.md) for exact steps.

### Simulated card accounting and settlement

The demo issues a gift only after a successful simulated attempt. That event adds equal/opposite ledger entries representing simulated funds and gift liability. Redemptions reduce the gift liability and record simulated merchant payables plus a sample 3% fee. **No issuer/customer money is held, moved, collected, safeguarded or settled**. Do not interpret the accounting model as a regulator-approved design.

### Security limitations before any real deployment

**This is not a production fintech platform.** At a minimum, real use requires an authorized issuer/payment partner and legal review; real provider webhooks; reconciled safeguarded customer funds; escrow/settlement contracts; provider-approved merchant and customer identity verification; secrets management; token rotation/refresh and revocation; HTTPS; rate limiting and bot controls; recipient onboarding and consent; security review and penetration testing; robust backup and disaster recovery; PostgreSQL transaction and load testing; migration management; fraud review; and proper customer support and dispute processes. The browser stores the demo token in `sessionStorage`, and demo accounts are seeded with published passwords. Do not expose this service to the public internet.

Physical card verification, an exchange marketplace, scheduled SMS delivery, live notifications, production QR issuance, real receipts, cash-out, and real settlement are **not implemented**.

## GitHub update

Once you have extracted the release into your existing GiftBridge repository (keep its `.git` and `.venv` folders and `giftbridge.db`), run:

```powershell
git status
git add .
git commit -m "GiftBridge v0.3 - personalized gifting and merchant studio"
git push
```

Be sure `.env`, SQLite database files and your local `.venv` are not staged. We have supplied `.gitignore` for these.

---
**GiftBridge Ethiopia · Build a culture of meaningful gifting.**
