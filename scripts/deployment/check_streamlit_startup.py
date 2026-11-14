"""Start the Streamlit app and check its local health endpoint.

This credential-free CI smoke test uses a temporary loopback port and always
stops the local child process after probing its health and root routes.
"""

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    """Ask the operating system for an available local TCP port.

    Returns:
        A port number released for the short Streamlit smoke process.
    """
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def main() -> int:
    """Launch Streamlit, check health and the rendered app, then stop it.

    Returns:
        Zero only when the application serves both health and root routes.
    """
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    environment = dict(os.environ)
    environment["STREAMLIT_SERVER_HEADLESS"] = "true"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "apps/ui/main.py",
            "--server.address",
            "127.0.0.1",
            "--server.port",
            str(port),
            "--server.headless",
            "true",
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline and process.poll() is None:
            try:
                with urllib.request.urlopen(
                    f"{base_url}/_stcore/health",
                    timeout=2,
                ) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, TimeoutError, OSError):
                time.sleep(0.5)
        else:
            print("Streamlit did not become healthy before the timeout.")
            return 1
        with urllib.request.urlopen(
            base_url,
            timeout=5,
        ) as response:
            body = response.read().decode("utf-8", errors="replace")
            if response.status != 200 or "streamlit" not in body.lower():
                print("Streamlit root page returned an unexpected response.")
                return 1
        print("Streamlit app startup, health, and root page passed.")
        return 0
    except (urllib.error.URLError, TimeoutError, OSError):
        print("Streamlit health or root route could not be reached.")
        return 1
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    sys.exit(main())
