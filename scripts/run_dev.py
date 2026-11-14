"""Run the API and Streamlit processes together and stop them on Ctrl+C."""

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    env_path = ROOT / ".env"
    contents = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    configured = any(
        line.partition("=")[2].strip().strip("'\"")
        for line in contents.splitlines()
        if line.startswith("DEV_USERS_JSON=")
    )
    if not configured:
        subprocess.run([sys.executable, "scripts/bootstrap_dev_env.py"], cwd=ROOT, check=True)

    api_port = os.environ.get("API_PORT", "8000")
    ui_port = os.environ.get("UI_PORT", "8501")
    api = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "apps.api.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            api_port,
        ],
        cwd=ROOT,
    )
    ui = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "apps/ui/main.py",
            "--server.port",
            ui_port,
            "--server.headless",
            "true",
        ],
        cwd=ROOT,
    )
    exit_code = 0
    try:
        while api.poll() is None and ui.poll() is None:
            time.sleep(0.5)
        exit_code = api.returncode or ui.returncode or 0
    except KeyboardInterrupt:
        exit_code = 0
    finally:
        for process in (ui, api):
            if process.poll() is None:
                process.terminate()
        deadline = time.monotonic() + 10
        while any(process.poll() is None for process in (ui, api)) and time.monotonic() < deadline:
            try:
                time.sleep(0.1)
            except KeyboardInterrupt:
                continue
        for process in (ui, api):
            if process.poll() is None:
                process.kill()
                process.wait()
    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
