"""Local-only launcher for GiftBridge v0.4. Browser opens after server health is ready."""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:8000'

def main():
    os.chdir(ROOT)
    print('\n  ✦ GiftBridge Ethiopia v0.4 | DEMO MODE (no real payments)')
    print('  Starting local web server at', URL)
    env = os.environ.copy()
    env.setdefault('APP_ENV', 'development')
    env.setdefault('ENABLE_DEMO_FUNDING', 'true')
    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.main:app',
                                '--host', '127.0.0.1', '--port', '8000', '--reload'], env=env)
    opened = False
    try:
        for _ in range(60):
            if process.poll() is not None:
                raise RuntimeError('Web server stopped during startup. See error output above.')
            try:
                with urllib.request.urlopen(URL + '/api/health', timeout=0.5) as response:
                    data=json.loads(response.read())
                    if data.get('version')=='0.4.0':
                        print('  Ready! Opening your browser...')
                        if os.getenv('GIFTBRIDGE_NO_BROWSER')!='1':webbrowser.open(URL)
                        opened=True
                        break
                    raise RuntimeError('Another application or older GiftBridge version is using port 8000.')
            except (urllib.error.URLError,TimeoutError):
                time.sleep(0.25)
        if not opened:raise RuntimeError('GiftBridge did not become ready. Check the terminal for errors.')
        print('  Press Ctrl+C to stop GiftBridge.\n')
        return process.wait()
    except KeyboardInterrupt:
        print('\nStopping GiftBridge...')
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill()

if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print('Launcher error:',exc)
        sys.exit(1)
