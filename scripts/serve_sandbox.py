"""Run the two local sandbox apps together."""

from __future__ import annotations

import subprocess
import sys
import time


def commands() -> list[list[str]]:
    return [
        [sys.executable, "-m", "uvicorn", "sandbox.portal.app:app",
         "--host", "127.0.0.1", "--port", "8101"],
        [sys.executable, "-m", "uvicorn", "sandbox.register.app:app",
         "--host", "127.0.0.1", "--port", "8102"],
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
