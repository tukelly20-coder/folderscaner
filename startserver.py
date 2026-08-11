#!/usr/bin/env python3
"""
startserver.py - Single entry point for the Folder Sync System.

Consolidates the backend server (FastAPI/uvicorn) and the frontend
client into one process supervisor.  The frontend can run in two modes:

  * Vite dev server  (``python startserver.py``)           — default dev mode
  * Python proxy      (``python startserver.py --proxy``)  — serves frontend/dist
                      and proxies /api + /ws to the backend (no Node.js needed)

When this script exits — whether via Ctrl+C, SIGTERM, or any unhandled
exception — **all** child processes are terminated automatically.

Usage:
    python startserver.py             # start backend + vite frontend
    python startserver.py --proxy     # start backend + python proxy frontend
    python startserver.py --backend   # backend only
    python startserver.py --frontend  # frontend only (vite)
    python startserver.py --stop      # stop all started processes
"""

import argparse
import atexit
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR / "backend"
FRONTEND_DIR = BASE_DIR / "frontend"
FRONTEND_DIST = FRONTEND_DIR / "dist"

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

BACKEND_LOG = LOG_DIR / "startserver_backend.log"
FRONTEND_LOG = LOG_DIR / "startserver_frontend.log"


processes: list[subprocess.Popen] = []
_lock = threading.Lock()


def _log(msg: str) -> None:
    print(f"[startserver] {msg}", flush=True)


def _open_log(path: Path):
    return path.open("w")


# --------------------------------------------------------------------------- #
# Process management helpers
# --------------------------------------------------------------------------- #

def _win_kill_tree(pid: int) -> None:
    """Force-kill *pid* and every child process (Windows)."""
    try:
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except Exception as exc:
        _log(f"  taskkill for PID {pid} failed: {exc}")


def _nix_kill_tree(proc: subprocess.Popen) -> None:
    """Kill an entire process group (POSIX)."""
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=5)
    except Exception:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _terminate_proc(proc: subprocess.Popen) -> None:
    """Terminate a single Popen handle, killing its whole tree on Windows."""
    if proc.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            try:
                proc.send_signal(signal.CTRL_BREAK_EVENT)
            except Exception:
                _win_kill_tree(proc.pid)
        else:
            proc.send_signal(signal.SIGTERM)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

    try:
        proc.wait(timeout=10)
    except Exception:
        if sys.platform == "win32":
            _win_kill_tree(proc.pid)
        else:
            try:
                proc.kill()
            except Exception:
                pass
            try:
                proc.wait(timeout=5)
            except Exception:
                pass


def stop_all() -> None:
    """Terminate every process in the *processes* list."""
    with _lock:
        if not processes:
            return
        _log("Stopping all processes...")
        for p in processes:
            _terminate_proc(p)
        processes.clear()
        _log("All stopped.")


def _monitor_worker(proc: subprocess.Popen, name: str) -> None:
    """Monitor a child; if it exits, log it (does not kill siblings)."""
    try:
        proc.wait()
    except Exception:
        pass
    if proc.returncode is not None:
        _log(f"{name} (PID {proc.pid}) exited with code {proc.returncode}")


# --------------------------------------------------------------------------- #
# Starters
# --------------------------------------------------------------------------- #

def start_backend() -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND_DIR)
    env.setdefault("SERVER_PORT", "8000")
    env.setdefault("SERVER_HOST", "0.0.0.0")

    log_fh = _open_log(BACKEND_LOG)
    _log("Starting backend (uvicorn)...")
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "app.main:app",
            "--reload",
            "--port", env["SERVER_PORT"],
            "--host", env["SERVER_HOST"],
        ],
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        **(
            {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            if sys.platform == "win32"
            else {"start_new_session": True}
        ),
    )
    with _lock:
        processes.append(proc)
    _log(f"Backend PID {proc.pid} — log: {BACKEND_LOG}")
    threading.Thread(target=_monitor_worker, args=(proc, "Backend"), daemon=True).start()
    return proc


def start_vite_frontend() -> subprocess.Popen:
    """Frontend via Vite dev server (npm run dev)."""
    log_fh = _open_log(FRONTEND_LOG)
    _log("Starting frontend (vite)...")
    proc = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=str(FRONTEND_DIR),
        env=os.environ.copy(),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        shell=(sys.platform == "win32"),
        **(
            {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            if sys.platform == "win32"
            else {"start_new_session": True}
        ),
    )
    with _lock:
        processes.append(proc)
    _log(f"Frontend PID {proc.pid} — log: {FRONTEND_LOG}")
    threading.Thread(target=_monitor_worker, args=(proc, "Frontend"), daemon=True).start()
    return proc


def start_proxy_frontend() -> subprocess.Popen:
    """Frontend via the Python proxy server (no Node.js required).

    Launches ``serve_frontend.py`` as a child process so that all
    lifecycle management stays inside *startserver.py*.
    """
    if not FRONTEND_DIST.exists():
        _log(f"  frontend/dist not found — building with Vite first...")
        try:
            subprocess.run(
                ["npm", "run", "build"],
                cwd=str(FRONTEND_DIR),
                env=os.environ.copy(),
                check=True,
                timeout=120,
            )
        except Exception as exc:
            _log(f"  Build failed: {exc}")

    log_fh = _open_log(FRONTEND_LOG)
    _log("Starting frontend (python proxy)...")
    proc = subprocess.Popen(
        [sys.executable, str(BASE_DIR / "serve_frontend.py")],
        env=os.environ.copy(),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        **(
            {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            if sys.platform == "win32"
            else {"start_new_session": True}
        ),
    )
    with _lock:
        processes.append(proc)
    _log(f"Frontend PID {proc.pid} — log: {FRONTEND_LOG}")
    threading.Thread(target=_monitor_worker, args=(proc, "Frontend"), daemon=True).start()
    return proc


# --------------------------------------------------------------------------- #
# Signal / lifecycle
# --------------------------------------------------------------------------- #

_shutting_down = False


def _handle_signal(signum, frame):
    global _shutting_down
    if _shutting_down:
        _log("Force kill requested, terminating immediately...")
        for p in list(processes):
            try:
                p.kill()
            except Exception:
                pass
        sys.exit(130)
    _shutting_down = True
    _log(f"Received signal {signum}, shutting down...")
    stop_all()
    sys.exit(130)


def _install_signal_handlers():
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handle_signal)
        except (ValueError, OSError):
            pass


atexit.register(stop_all)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Single entry point for the Folder Sync System (backend + frontend client)."
    )
    parser.add_argument("--backend", action="store_true", help="Start backend (API server) only")
    parser.add_argument("--frontend", action="store_true", help="Start frontend (vite) only")
    parser.add_argument("--proxy", action="store_true",
                        help="Use the Python proxy server for the frontend instead of Vite "
                             "(serves frontend/dist, proxies /api and /ws to backend)")
    parser.add_argument("--stop", action="store_true", help="Stop all started processes")
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    _install_signal_handlers()

    if args.stop:
        stop_all()
        return 0

    if args.backend and not args.frontend and not args.proxy:
        start_backend()
    elif args.frontend and not args.backend and not args.proxy:
        start_vite_frontend()
    elif args.proxy and not args.backend and not args.frontend:
        start_proxy_frontend()
    else:
        start_backend()
        # Give the backend a moment to bind before the frontend starts
        time.sleep(2)
        if args.proxy:
            start_proxy_frontend()
        else:
            start_vite_frontend()

    _log("Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        stop_all()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
