"""Start portal, register and live console on their documented local ports."""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

from scripts.serve_sandbox import commands, run
from worker.config import ROOT


def main() -> None:
    load_dotenv(ROOT / ".env", override=False)
    os.environ.setdefault("WORKER_ENGINE", "live")
    app_commands = commands() + [[
        sys.executable, "-m", "uvicorn", "worker.console.app:app",
        "--host", "127.0.0.1", "--port", "8100",
    ]]
    run(app_commands)


if __name__ == "__main__":
    main()
