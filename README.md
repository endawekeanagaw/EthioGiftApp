# GiftBridge Ethiopia — End-to-end sandbox MVP v0.2

A responsive, **local-only simulated gift card platform** with merchant-specific and universal (multi-merchant) digital gifts, simulated checkout, merchant onboarding, gifting, cashier redemption and a settlement preview.

> **IMPORTANT:** This demo issues fictional cards with fictional money. It does **not** connect to M-PESA, telebirr, Dashen Bank, Queens Supermarket, any real bank or a real payment system. Any merchants named in seed data are illustrative examples, **not partners**. Do not deploy this build publicly or use it for real funds, real card identifiers, or customer personal data.

## Windows: start in minutes

1. Extract the ZIP. Open `giftbridge` (the folder containing `requirements.txt`) in VS Code.
2. Open **Terminal > New Terminal** and enter:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m backend.seed
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

3. Visit **http://127.0.0.1:8000**. API documentation: **http://127.0.0.1:8000/docs**.
4. Later, **double-click `run.bat`** (provided Python dependencies are installed), or start from the terminal with one command:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

If you already have the previous GiftBridge version installed, use the **same project folder** and copy the changed source files into it. The new tables are created automatically. Back up your existing `giftbridge.db` before changing code. You do **not** need to recreate `.venv`; rerun `python -m backend.seed` to add sample cashier/program accounts safely. If Git reports modified files, use `git status` and commit after reviewing changes.

**Unix/macOS:** activate `.venv/bin/activate`, then `python -m backend.seed && python -m uvicorn backend.main:app --reload`.

## Demo sign-ins

All passwords: `DemoPass123!`.

| Role | Phone | Use case |
|---|---|---|
| Administrator | `251900000001` | Create merchant, create program, assign staff, settlement |
| Customer | `251900000002` | Browse, buy, simulate payment, send gift |
| Recipient | `251900000003` | Receive gifts and view wallet |
| Queens demo cashier | `251900000004` | Redeem at the Queens demo merchant only |

Seed with `.venv\Scripts\python.exe -m backend.seed` if they are missing. Accounts created by users through the UI have the `customer` role by default.

## Complete demo walkthrough

**Scenario A — Admin creates a merchant and a card program**

1. Sign in as administrator.
2. Open **Management** → **Create merchant**, name it `Coffee House Demo`.
3. Under **Create gift program**, enter `Coffee House Gift`, choose **Merchant-specific** and check **Coffee House Demo** only → Publish.
4. For a universal gift, choose **Universal multi-merchant** and check two or more merchants.
5. Both appear immediately in the Gift Shop.

**Scenario B — Customer buys a gift and pays (simulation only)**

1. Sign in as demo customer.
2. Choose a gift, enter ETB `2000`, and set recipient phone `251900000003`.
3. Click **Proceed to demo checkout**.
4. Choose a simulated channel, e.g. `M-PESA (simulated)`.
5. Click **Simulate successful payment**. A success popup appears with the new `GB-...` code.
6. Sign in as recipient; find the gift in **My wallet**.

**Scenario C — Failed payment and retry**

1. Create another order. At checkout click **Simulate failed payment**.
2. No gift is issued, and the order appears as **FAILED** in **My orders**.
3. Click **Retry payment** and simulate success. Exactly one card is issued.

**Scenario D — Cashier redemption**

1. Get the gift card code from recipient's wallet.
2. Sign in as administrator or seeded cashier `251900000004`.
3. Select **Cashier POS**, paste the `GB-...` code, select an eligible merchant and redeem a partial amount.
4. Check the balance again under recipient's wallet. A merchant-specific card cannot be spent at an unrelated merchant.
5. Admin sees the simulated gross, fee and payable values under **Management**.

**Scenario E — Send an already-owned card**

1. Sign in as a card owner.
2. Open **My wallet**, click **Send gift**, enter a different registered phone.
3. The card leaves the sender's wallet and appears in the recipient's wallet. Redemptions and transfers are visible under **History**.

## Implemented functionality

- Customer sign-up and sign-in; HMAC-SHA256 signed, expiring access tokens; salted PBKDF2 passwords.
- Admin merchant onboarding and program publication.
- Single-merchant and universal acceptance networks.
- Merchant cashier assignment, with merchant-scoped redemption permissions.
- Gift order creation (`PENDING`), simulated payment confirmation (`PAID`) or failure (`FAILED`), retry support.
- Exactly-one simulated gift issuance per paid order, with replay-safe payment handling and order/card mapping.
- Card wallet, available balance, gifting to registered recipients, transaction history.
- Merchant redemption, insufficient-funds and merchant-acceptance checks, idempotency keys.
- Admin dashboard, illustrative merchant settlement preview and zero-sum event ledger checks.
- Responsive web UI, success modal, failed-payment message, loading states.
- FastAPI Swagger docs (`/docs`), automated end-to-end API tests, Docker Compose for local PostgreSQL demonstration.

## Main API endpoints

| Route | Purpose |
|---|---|
| `POST /api/auth/register` | Create a customer account |
| `POST /api/auth/login` | Obtain an access token |
| `GET /api/programs` | Gift shop programs and acceptance networks |
| `POST /api/orders` | Create pending gift purchase |
| `POST /api/orders/{id}/simulate-payment` | Simulate success or failure (NO money charged) |
| `POST /api/orders/{id}/retry` | Retry a failed checkout |
| `GET /api/orders` | List your orders and simulated attempts |
| `GET /api/wallet` | View currently owned cards |
| `POST /api/cards/{id}/send` | Gift card ownership transfer |
| `GET /api/cards/{id}/history` | Card redemption and transfer history |
| `POST /api/redemptions` | Authorized demo cashier redemption |
| `POST /api/admin/merchants` | Create merchant |
| `POST /api/admin/programs` | Create merchant or universal program |
| `POST /api/admin/staff` | Assign registered user to merchant |
| `GET /api/admin/overview` | Simulated metrics and ledger checks |
| `GET /api/admin/settlements` | Illustrative settlement totals |

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The tests create an independent temporary SQLite database, leaving your local demo data unchanged. Tests exercise multiple roles and full payment/order/gift/redemption flows.

## Project map

```text
giftbridge/
  backend/main.py          FastAPI routes + data models
  backend/seed.py          Sample users, merchants, programs
  frontend/index.html      Web interface
  frontend/app.js          Order, payment modal, wallet, admin flows
  frontend/style.css       Responsive interface
  tests/test_flows.py      Integration tests
  run.bat                  Windows one-click startup
  requirements.txt
  docker-compose.yml
  README.md
  .gitignore
```

## Financial, legal, and engineering limitations

**This is not a real payment application.** The sandbox `simulate-payment` endpoint deliberately generates fictional gift value without receiving money. Never expose this endpoint in a public production service. It has no provider signature verification, KYC, cash settlement, safeguarding, or live payment reconciliation.

SQLite does not provide row-level locks for concurrent redemption; production needs PostgreSQL transaction/concurrency design and comprehensive security reviews. The demo uses a simplified ledger and a fixed illustrative 3% fee. It has no production refunds, chargeback handling, formal accounting reconciliation, dynamic fee contracts, merchant-issued credential scanning, signed single-use redemption codes, physical-card conversion, or gift marketplace. A card code must **not** be used as an actual spendable credential.

Additional hardening needed before real use: issuer and bank agreements; Ethiopian regulatory/legal review; user privacy compliance; token/key storage and rotation; proper merchant KYC and staff lifecycle; MFA; email/SMS ownership verification; rate limits; device fraud controls; encryption; backups; observability; migrations; strict PostgreSQL serializability/locking; code-signed redemption tokens; anti-enumeration; penetration testing; and licensed partner-managed settlement.

## Docker option (local sandbox)

```bash
docker compose up --build
```

See `docker-compose.yml`. Do not use the sample credentials or hard-coded secrets on any publicly reachable server.
