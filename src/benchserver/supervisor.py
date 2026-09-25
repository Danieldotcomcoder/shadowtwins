"""A small process supervisor for the single-container deployment.

1. Apply migrations and load shipped packs (before any worker starts).
2. Start the API and the worker as child processes.
3. Restart a child that exits unexpectedly (bounded: 5 restarts per child per 5 minutes).
4. On SIGTERM/SIGINT, stop both gracefully (SIGTERM, then kill after a grace period).
"""

from __future__ import annotations

import logging
import signal
import subprocess
import sys
import time
from collections import deque

from .app_state import configure_logging, prepare_database
from .config import load_settings

log = logging.getLogger("benchserver.supervisor")
GRACE_S = 35.0
MAX_RESTARTS = 5
RESTART_WINDOW_S = 300.0


def supervise(host: str, port: int) -> int:
    settings = load_settings()
    configure_logging(settings, "supervisor")
    log.info("preparing database: %s", prepare_database(settings))
    cmds = {
        "api": [sys.executable, "-m", "benchserver.cli", "api", "--host", host, "--port", str(port)],
        "worker": [sys.executable, "-m", "benchserver.cli", "worker"],
    }
    procs: dict[str, subprocess.Popen[bytes]] = {}
    restarts: dict[str, deque[float]] = {k: deque() for k in cmds}
    stopping = False

    def start(name: str) -> None:
        procs[name] = subprocess.Popen(cmds[name])
        log.info("started %s (pid %d)", name, procs[name].pid)

    def request_stop(signum: int, _frame: object) -> None:
        nonlocal stopping
        log.info("received signal %d; stopping", signum)
        stopping = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    for name in cmds:
        start(name)
    exit_code = 0
    while not stopping:
        time.sleep(0.5)
        for name, p in list(procs.items()):
            rc = p.poll()
            if rc is None or stopping:
                continue
            log.error("%s exited with code %s", name, rc)
            window = restarts[name]
            t = time.monotonic()
            while window and t - window[0] > RESTART_WINDOW_S:
                window.popleft()
            if len(window) >= MAX_RESTARTS:
                log.error("%s restarted %d times in %.0fs; giving up", name, MAX_RESTARTS, RESTART_WINDOW_S)
                stopping, exit_code = True, 1
                break
            window.append(t)
            time.sleep(min(10.0, 2 ** len(window)))
            start(name)
    for p in procs.values():
        if p.poll() is None:
            p.terminate()
    deadline = time.monotonic() + GRACE_S
    for name, p in procs.items():
        try:
            p.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            log.warning("%s did not stop in time; killing", name)
            p.kill()
    log.info("supervisor stopped")
    return exit_code
