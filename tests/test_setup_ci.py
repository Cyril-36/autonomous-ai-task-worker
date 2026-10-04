"""Guard the free, reproducible setup and CI path used by reviewers."""

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_make_setup_installs_both_apps_and_browser_without_paid_calls():
    result = subprocess.run(["make", "-n", "setup"], cwd=ROOT, capture_output=True,
                            text=True, check=True)
    commands = result.stdout
    assert "uv sync --locked" in commands
    assert "playwright install chromium" in commands
    assert "npm --prefix console ci" in commands
    assert "npm --prefix console run build" in commands
    assert "eval-live" not in commands
    assert "smoke_llm" not in commands


def test_ci_runs_fake_backend_evals_and_console_checks_without_a_key():
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    assert "push" in workflow["on"] and "pull_request" in workflow["on"]
    steps = workflow["jobs"]["checks"]["steps"]
    commands = "\n".join(step.get("run", "") for step in steps)
    for expected in ("uv sync --locked", "ruff check .", "pytest", "evals.run",
                     "npm ci", "npm test", "npm run build"):
        assert expected in commands
    assert "--live" not in commands
    assert "AICREDITS_API_KEY" not in str(workflow)
