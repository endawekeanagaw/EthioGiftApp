# Safely upgrade GiftBridge v0.5 to v0.6 on Windows

## 1. Back up and preserve data

1. Stop the local GiftBridge server (`Ctrl+C`).
2. Confirm you are in the **existing local Git repository root**, which contains `backend`, `frontend`, `.git` and `run.bat`.
3. Create a backup of your current `giftbridge.db` outside the project, e.g. `Documents\GiftBridge-backups\giftbridge-v05-before-upgrade.db`. Also back up any `.env` and custom modifications.
4. Extract v0.6 separately, then **copy only the updated project source files and folders** into your existing Git project. Replace source where prompted. **Never replace or delete `.git`, `.venv`, `.env`, or `giftbridge.db`.**

If you made your own modifications, compare/diff files before overwriting; this is a source-code release, not an automatic merge or a migration manager.

## 2. Install / run

In your existing GiftBridge project folder:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m backend.seed
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

Or double-click the updated `run.bat` once your virtual environment is set up.

`backend.main` creates the four **new additive tables** on startup: `payment_intents`, `payment_events`, `fraud_alerts`, and `login_guards`. It does not rename/drop the old tables or rewrite historical v0.5 transactions. **This is not an Alembic migration system**; always test the upgrade using a copy of the database first. If you use PostgreSQL instead of SQLite, also test schema creation and permissions in a nonproduction instance.

## 3. Acceptance checklist

- [ ] Your older gift cards and balances appear in My wallet.
- [ ] Existing orders and merchant dashboard records remain accessible.
- [ ] New checkout produces a simulated intent and success/failure result.
- [ ] Admin → Management → Risk & reconciliation center loads.
- [ ] Reconciliation reads **PASS** for unmodified, consistent demo records. If it shows FAIL, investigate; do not delete historical transactions to make it pass.
- [ ] Run `python -m pytest -q` using `.venv\Scripts\python.exe` and confirm all tests pass.
- [ ] Review `git status` before committing; local `.db`, `.env` and `.venv` must remain untracked.

## 4. Push the upgrade to GitHub

```powershell
git status
git add .
git diff --cached --name-only
git commit -m "Release v0.6: Payment intents, fraud monitoring and reconciliation"
git push
```

If any sensitive or local file appears in the staged list, unstage it before committing. To return to v0.5, stop the server, restore your backed-up database to its previous path, and revert to your previous Git commit or tag (after safeguarding newer changes). The new tables are harmless to old code but do not assume rollback compatibility across every custom version.
