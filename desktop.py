"""Desktop entry point: serve FastAPI on a fixed localhost port and open it in a browser."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.request import urlopen

import uvicorn

PORT = 18765
URL = f"http://127.0.0.1:{PORT}/"


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return True
    return False


def _wait_until_ready(url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=1) as resp:
                if resp.status < 500:
                    return
        except Exception:
            time.sleep(0.15)
    raise RuntimeError(f"Server did not become ready: {url}")


def _find_edge() -> str | None:
    candidates = [
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
        os.path.join(os.environ.get("LocalAppData", ""), "Microsoft", "Edge", "Application", "msedge.exe"),
    ]
    for path in candidates:
        if path and Path(path).is_file():
            return path
    return None


def _open_browser(url: str) -> None:
    edge = _find_edge()
    if edge:
        try:
            subprocess.Popen([edge, f"--app={url}"], close_fds=True)
            return
        except Exception:
            pass
    webbrowser.open(url)


def _print_banner() -> None:
    print("=" * 60)
    print("  PEAK — Project Efficiency & Automation Kernel")
    print(f"  Running at: {URL}")
    print("  Close this console window to exit PEAK.")
    print("=" * 60, flush=True)


def main() -> None:
    if _port_in_use(PORT):
        print(f"PEAK is already running. Opening {URL} in browser ...", flush=True)
        _open_browser(URL)
        return

    config = uvicorn.Config(
        "main:app",
        host="127.0.0.1",
        port=PORT,
        log_level="info",
        reload=False,
        access_log=False,
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    try:
        _wait_until_ready(URL)
    except Exception as exc:
        print(f"[PEAK] Failed to start server: {exc}", file=sys.stderr, flush=True)
        server.should_exit = True
        thread.join(timeout=5)
        sys.exit(1)

    _print_banner()
    _open_browser(URL)

    try:
        while thread.is_alive():
            thread.join(timeout=1)
    except KeyboardInterrupt:
        pass
    finally:
        server.should_exit = True
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
