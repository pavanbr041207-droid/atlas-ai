"""launcher.py — Atlas AI entry point
Starts Flask backend silently, opens frontend in default browser.
Works when frozen by PyInstaller (sys._MEIPASS) or run from source.
"""

import sys, os, threading, time, webbrowser, subprocess

# ── Path fix for PyInstaller frozen bundle ──────────────────────
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Add backend to path so Flask blueprints resolve
BACKEND_DIR = os.path.join(BASE_DIR, 'backend') if not getattr(sys, 'frozen', False) else BASE_DIR
sys.path.insert(0, BACKEND_DIR)

PORT = 5001
URL  = f"http://localhost:{PORT}"


def check_ollama():
    """Warn user if Ollama not running."""
    import urllib.request
    try:
        urllib.request.urlopen("http://localhost:11434", timeout=3)
    except Exception:
        print("⚠️  Ollama not detected at localhost:11434")
        print("   Atlas AI needs Ollama running for AI features.")
        print("   Download: https://ollama.com")


def open_browser():
    """Wait for Flask to boot, then open browser."""
    import urllib.request
    for _ in range(30):           # wait up to 15s
        try:
            urllib.request.urlopen(f"{URL}/api/health", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    webbrowser.open(URL)


def run_flask():
    os.environ['FLASK_ENV'] = 'production'
    # Set storage path next to executable
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        os.environ['ATLAS_STORAGE'] = os.path.join(exe_dir, 'atlas_storage')

    from app import app
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)


if __name__ == '__main__':
    check_ollama()

    # Start Flask in background thread
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()

    # Open browser after Flask boots
    open_browser()

    # Keep main thread alive (required on Windows)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sys.exit(0)
