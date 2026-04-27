"""Desktop entry point: serve FastAPI in-process and show a native window."""

from __future__ import annotations

import socket
import threading
import time
from urllib.request import urlopen

import uvicorn
import webview


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_ready(url: str, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=1) as resp:
                if resp.status < 500:
                    return
        except Exception:
            time.sleep(0.15)
    raise RuntimeError(f"Server did not become ready: {url}")


def main() -> None:
    port = _free_port()
    config = uvicorn.Config(
        "main:app",
        host="127.0.0.1",
        port=port,
        log_level="info",
        reload=False,
        access_log=False,
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    url = f"http://127.0.0.1:{port}/"
    _wait_until_ready(url)

    webview.create_window(
        "PEAK — Project Efficiency & Automation Kernel",
        url,
        width=1400,
        height=900,
        resizable=True,
    )
    webview.start()

    server.should_exit = True
    thread.join(timeout=5)


if __name__ == "__main__":
    main()
