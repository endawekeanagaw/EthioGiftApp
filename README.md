# GiftBridge Ethiopia — runnable MVP demo

**Educational prototype, NOT a financial production system.** Includes merchant-specific and universal gift programs, simulated issuance, gift sending, wallet, POS redemption, double-entry demonstration ledger, admin program management and settlement reports. No live money moves. Queens/Dashen are not partners or integrated; all sample names are illustrative.

## Quick start (Python 3.11+)

```bash
cd giftbridge
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python -m backend.seed
uvicorn backend.main:app --reload
```

Open **http://localhost:8000**. API docs: **http://localhost:8000/docs**.

Demo accounts (all passwords `DemoPass123!`):
- Admin: `251900000001`
- Customer: `251900000002`
- Recipient: `251900000003`

Or run `docker compose up --build` for PostgreSQL-backed demo.

## Demo walkthrough
1. Log in as customer and issue a Queens or universal gift via simulated funding.
2. Open Wallet, copy the `GB-...` code, then open POS Demo.
3. Redeem Queens at Queens; attempting a different merchant is rejected. Universal accepts all seeded demo merchants.
4. Log in as admin to view outstanding liability, redeemed totals and illustrative merchant payables.
5. Register another customer or send a gift to the seeded recipient.

## Architecture
- FastAPI + SQLAlchemy (SQLite local / PostgreSQL Docker)
- Responsive HTML/CSS/vanilla JavaScript frontend (not Flutter/React yet)
- JWT login, PBKDF2 password hashes, role-gated admin endpoints
- Program acceptance network, gift ownership, redemption idempotency, balanced demo ledger entries

## IMPORTANT: Not production ready
- `/api/demo/issue` **mints demo gift value without a real payment**. Disable/remove for live use.
- `/api/redemptions` is a **demo cashier simulator** accessible to logged-in users. Replace with verified merchant/cashier roles and branch binding before any live deployment.
- SQLite ignores row locks; PostgreSQL is recommended for concurrency testing. Add robust retry/unique-key collision handling, database constraints and production migration tooling.
- No real payment gateway, escrow, cash settlement, reversal, refund, fraud case management, real QR credential, physical card issuer API, gift exchange, KYC/AML, customer fund safeguarding, or regulatory authorization.
- Fee calculation is an illustrative fixed 3% with integer rounding, not a contractual fee engine.
- No real-time transfer locks; physical card conversion and resale are intentionally excluded until issuer integration is available.
- Demo secrets and credentials MUST be changed; enforce HTTPS, CSRF/session protections as applicable, MFA, logging, rate limits, monitoring, proper key management and professional security review.
- Existing physical cards shown in user photos must not be entered into this demo: the platform cannot verify them.

## Proposed production milestones
1. Formal PRD, issuer/merchant contracts and legal classification for universal value.
2. Licensed payment partner integration with verified signed callbacks, refund flow, safeguarded funds reconciliation.
3. Cashier identities, authorization/capture/reversal, robust ledger and concurrent redemption tests.
4. Physical issuer adapters with ownership verification and plastic-to-digital spend lock.
5. Marketplace only with issuer-approved transfer, fraud holds, dispute handling and regulated settlement.

## API endpoints
Visit `/docs` for interactive OpenAPI specification. Admin endpoints require admin login. Amounts are ETB; internally balances use integer cents.
"# EthioGiftApp" 
"# EthioGiftApp" 
