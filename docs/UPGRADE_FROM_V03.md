# Upgrade GiftBridge v0.3 → v0.4 on Windows

This guide preserves the source repository, virtual environment and local demo transaction history. **Backup first; never delete the existing project to replace it.**

## 1. Back up your working project

1. Press **Ctrl+C** in the running GiftBridge terminal (or close the `run.bat` terminal).
2. Locate the `giftbridge` folder in your existing GitHub checkout, not the newly downloaded ZIP.
3. Make a copy of `giftbridge.db` (for example `giftbridge-backup-v03.db`) **outside** the project folder, ideally next to the project, so it cannot be accidentally staged into Git.
4. Run `git status` to see whether you have uncommitted changes. Commit or back them up before copying the update.

## 2. Copy v0.4 source over v0.3

1. Extract `GiftBridge-Ethiopia-v0.4-Customer-Experience.zip`.
2. Open the inner `giftbridge` directory from the extracted ZIP.
3. Copy its `backend/`, `frontend/`, `tests/`, `docs/`, `README.md`, `CHANGELOG.md`, `requirements.txt`, `launcher.py` and `run.bat` into the existing project folder, replacing matching **source files**.
4. **Keep your existing `.git/`, `.venv/`, `.env` and `giftbridge.db` exactly as they are.** The ZIP contains no `.git`, `.venv` or user database.
5. No dropping or clearing tables is necessary. New v0.4 tables (`program_appearances`, `program_favorites`) are added automatically by the local prototype.

## 3. Start the application

Double-click `run.bat`; or from the existing project folder run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m backend.seed
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

If the browser continues to show the old layout, perform a hard refresh (**Ctrl+Shift+R**). Visit `/api/health` in your browser to confirm `"version":"0.4.0"`.

## 4. Smoke test the upgrade

- Log in as buyer `251900000002`.
- Confirm earlier purchases still appear in **My orders**, and gift balances remain the same.
- Save a favorite gift program, then refresh to confirm the heart remains selected.
- Make a fresh demo purchase and download its HTML receipt.
- Log in as recipient `251900000003`; check the inbox, wallet balance and redemption PIN.
- Log in as cashier `251900000004`; simulate a partial redemption.
- Confirm no new critical exceptions appear in the terminal.

## 5. Push your update to GitHub

Run these from your **existing GitHub project folder**:

```powershell
git status
git add .
git diff --cached --name-only
git commit -m "Release v0.4: Refine gifting experience, favorites and demo receipts"
git push
```

Ensure `.venv`, `giftbridge.db`, `.env`, real secrets, backups and raw customer data are **not** staged. The provided `.gitignore` excludes common local files.

## 6. Rollback

If the upgrade fails, stop the server, restore the earlier v0.3 source from Git and restore the copied v0.3 database backup. Keep your backup until you have completed the smoke test. **Do not** run destructive SQL migrations on your local database to attempt recovery.

## Compatibility details

v0.4 extends the v0.3 schema with additional tables only. The same `cards`, `gift_orders`, `redemptions`, `gift_presentations` and existing other v0.3 data remain. This approach is appropriate for the demonstration but is not a replacement for versioned database migrations in production.
