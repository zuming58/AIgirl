from __future__ import annotations

import argparse
import ctypes
import os
import threading

import uvicorn


def watch_parent_process(parent_pid: int | None) -> None:
    if not parent_pid or os.name != "nt":
        return

    def wait_for_parent() -> None:
        synchronize = 0x00100000
        infinite = 0xFFFFFFFF
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(synchronize, False, parent_pid)
        if not handle:
            return
        try:
            kernel32.WaitForSingleObject(handle, infinite)
        finally:
            kernel32.CloseHandle(handle)
        os._exit(0)

    threading.Thread(
        target=wait_for_parent,
        name="xinyu-parent-watch",
        daemon=True,
    ).start()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Xinyu local core service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--parent-pid", type=int)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost"}:
        parser.error("Xinyu Core may only listen on loopback")
    watch_parent_process(args.parent_pid)
    uvicorn.run(
        "xinyu_core.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
