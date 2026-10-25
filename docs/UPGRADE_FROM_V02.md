# Upgrading GiftBridge from v0.2 to v0.3 (Windows)

Your v0.2 GitHub repo, environment, and demo purchases can be preserved. **Do not delete your existing project folder.**

1. Stop the local Uvicorn server (`Ctrl+C`) and close any `run.bat` window.
2. In Windows Explorer, locate the existing `giftbridge` directory (it contains `backend`, `frontend`, `.git`, and usually `.venv`).
3. **Back up the SQLite file**: copy `giftbridge.db` to a location outside the project, e.g. `Documents\giftbridge-backups\giftbridge-before-v03.db`. The file is ignored by Git.
4. Download and extract the v0.3 ZIP. Open its inner `giftbridge` directory. Copy its source files and directories into the existing `giftbridge` directory, accepting replacement for `backend`, `frontend`, `run.bat`, docs, README, tests and dependency files. **Do not delete or overwrite `.git`, `.venv`, your `.env`, or `giftbridge.db`.**
5. Double-click the updated `run.bat`. It reuses the existing `.venv`, prepares any missing demo users, and starts v0.3. It automatically creates additional tables when the app is imported. No destructive migration is performed by this build.
6. Open **http://127.0.0.1:8000** and sign in with an existing account. Verify that older gift cards still appear in **My wallet**.
7. Open the admin/cashier demo and try the new owner-generated redemption PIN flow. **This replaces the old v0.2 code-only redemption behavior.**
8. Run `.\.venv\Scripts\python.exe -m pytest -q` to check the isolated test suite.
9. After reviewing `git status`, commit and push changes to your existing repository.

### If anything fails

- Use a fresh terminal inside the correct project directory, not `C:\WINDOWS\system32`.
- If `uvicorn` is not recognized, run `run.bat` or `.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload`.
- If a dependency is missing, run `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`.
- If port 8000 is in use, stop the other Uvicorn terminal before rerunning.
- If old data behaves unexpectedly, **stop the server first** and restore your backed-up `.db`. Avoid overwriting the database while the app is running.
- This is a sandbox and does not include a production-ready migration framework.
