from decimal import Decimal

from worker.config import ROOT, Settings, load_pricing, spending_ledger_path
from worker.runtime.runner import LiveRunner
from worker.store import Store


def test_settings_use_documented_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    settings = Settings.from_env(data_dir=tmp_path)
    assert settings.model == "google/gemini-2.5-flash-lite"
    assert settings.base_url == "https://api.aicredits.in/v1"
    assert settings.data_dir == tmp_path


def test_example_env_uses_the_documented_default_model():
    assert "LLM_MODEL=google/gemini-2.5-flash-lite" in (ROOT / ".env.example").read_text()


def test_console_and_live_evals_share_the_preserved_spending_ledger(tmp_path):
    store = Store(tmp_path / "worker.db")
    runner = LiveRunner(store, Settings.from_env(data_dir=tmp_path))
    assert runner.ledger.path == spending_ledger_path(tmp_path)
    assert spending_ledger_path(ROOT / "data") == ROOT / "data" / "live-eval-ledger.db"
    reset_target = (ROOT / "Makefile").read_text().split("reset-demo:", 1)[1].split("\n", 2)[1]
    assert "live-eval-ledger.db" not in reset_target


def test_prices_and_limits_are_decimal():
    pricing = load_pricing()
    assert pricing.global_limit_inr == Decimal(60)
    assert pricing.run_limit_inr == Decimal(4)
    assert pricing.models["google/gemini-2.5-flash"].input_per_million == Decimal("30.36")
