# Upgrading GiftBridge Ethiopia from v0.4 to v0.5 (Windows)

GiftBridge v0.5 preserves the customer marketplace and wallet and adds a merchant onboarding and management system. **This is a local demo that cannot be used for real payments or real merchant verification.**

## Before updating

1. **Stop** the GiftBridge server (Ctrl+C or close the window opened by `run.bat`).
2. Open the existing GiftBridge project folder in File Explorer / VS Code.
3. Back up `giftbridge.db` if it exists, for example to `giftbridge-backup-v04.db` **outside your Git project**.
4. Commit your current GitHub project state first if it contains local changes. Check `git status`.
5. Extract the **new ZIP**. It contains a top-level `giftbridge` folder. Copy its source files into **your existing** project folder, accepting replacement of matching source files.
6. **Do not delete or replace** `.git`, `.venv`, `.env`, `giftbridge.db`, or local configuration. Do not upload these files to GitHub.

## First run after upgrade

Double-click `run.bat`. It checks for the `qrcode` dependency added in v0.5 and installs packages from `requirements.txt` if it is missing. If you prefer PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m backend.seed
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000. Refresh the browser with **Ctrl+Shift+R**. If you are already signed in, sign out and sign back in after a merchant account is approved to refresh the navigation and merchant permissions.

## What changes in the database

On import the application adds only three tables to the v0.4 database:

- `merchant_applications`: demo merchant intake, reviews, status and notes
- `merchant_memberships`: owner/manager/cashier roles with cashier branch scope
- `redemption_locations`: branch and acting cashier for **new** redemptions

It does not require changing columns of existing `cards`, `gift_orders`, `redemptions`, `ledger_entries`, or `users` tables. Older redemptions have no location record and show as **Unspecified** in new reports. Existing platform-created merchants do **not automatically have owners**; an admin can still manage them using older Management screens. No real KYC documents are collected.

## Test the new experience

1. Sign in as a customer and open **Become a merchant**. Submit a **demo** business application.
2. Sign out and sign in as admin: `251900000001`, `DemoPass123!`. Open **Management → Merchant applications**, approve the request.
3. Return to the applicant account and **sign in again**. **Merchant studio** should now be available.
4. Publish a merchant-specific gift. Add a branch. Assign a registered account as cashier to that branch.
5. Buy the gift as a customer and **simulate payment success** (no real funds move).
6. As the gift owner, go to **My wallet → Redeem PIN**. The app displays a QR for the gift's identifier, plus a separate 8-digit one-time PIN valid for 5 minutes.
7. As the cashier, open **Cashier POS**. Scan the QR with a supported browser/camera, or type the gift code. Select the authorized branch and enter the one-time PIN and an amount.
8. As owner, view branch activity, simulated payable amounts and redemption trend in **Merchant studio**.

**QR security:** QR contains the card *identifier only*, which is not a redemption credential. PIN verification, staff assignment and available-balance checks are enforced server-side. Camera scanning depends on browser support for `BarcodeDetector` and permission; manual entry is a supported fallback.

## Run tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

These tests use a temporary SQLite database, **not** `giftbridge.db`.

## Push the update

```powershell
git status
git add .
git diff --cached --name-only
git commit -m "Release v0.5: Merchant onboarding, roles, branch POS and analytics"
git push
```

Ensure `.venv`, `giftbridge.db`, `.env` and any real information aren't staged. This demo intentionally blocks startup if `APP_ENV=production`.
