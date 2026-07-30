"""Windows portable launcher for the bundled Streamlit application."""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path


DEFAULT_PORT = 8501
STARTUP_TIMEOUT_SECONDS = 45


def bundled_root() -> Path:
    """Return the directory that contains the bundled app.py and src package."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def portable_root() -> Path:
    """Keep mutable logs and Provider settings beside the portable executable."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return bundled_root()


def port_is_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def select_port() -> int:
    requested = os.environ.get("AERO_ANALYTICA_PORT", str(DEFAULT_PORT))
    try:
        requested_port = int(requested)
    except ValueError:
        requested_port = DEFAULT_PORT

    if 1 <= requested_port <= 65535 and port_is_available(requested_port):
        return requested_port

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def open_browser_when_ready(url: str, port: int) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                webbrowser.open(url, new=2)
                return
        except OSError:
            time.sleep(0.25)


def main() -> int:
    app_path = bundled_root() / "app.py"
    if not app_path.exists():
        raise RuntimeError(f"Bundled application is missing: {app_path}")

    root = portable_root()
    root.mkdir(parents=True, exist_ok=True)
    os.chdir(root)

    port = select_port()
    url = f"http://127.0.0.1:{port}"
    print(f"Aero-Analytica is starting at {url}")
    print("Keep this window open while using the application.")
    threading.Thread(
        target=open_browser_when_ready,
        args=(url, port),
        daemon=True,
    ).start()

    from streamlit.web import cli as streamlit_cli

    sys.argv = [
        "streamlit",
        "run",
        str(app_path),
        f"--server.port={port}",
        "--server.address=127.0.0.1",
        "--server.headless=true",
        "--server.fileWatcherType=none",
        "--global.developmentMode=false",
        "--browser.gatherUsageStats=false",
    ]
    return int(streamlit_cli.main() or 0)


if __name__ == "__main__":
    raise SystemExit(main())
