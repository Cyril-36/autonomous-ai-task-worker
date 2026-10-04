"""Run the two local sandbox apps together."""

from __future__ import annotations

import os
import subprocess
import sys
import time

# 127.0.0.1 locally; the container sets 0.0.0.0 so its published ports are reachable.
HOST = os.getenv("BIND_HOST", "127.0.0.1")


def commands() -> list[list[str]]:
    return [
        [sys.executable, "-m", "uvicorn", "sandbox.portal.app:app",
         "--host", HOST, "--port", "8101"],
        [sys.executable, "-m", "uvicorn", "sandbox.register.app:app",
         "--host", HOST, "--port", "8102"],
    ]


def run(commands_to_start: list[list[str]]) -> None:
    processes = [subprocess.Popen(command) for command in commands_to_start]
    try:
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    run(commands())
