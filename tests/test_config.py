from decimal import Decimal

from worker.config import Settings, load_pricing


def test_settings_use_documented_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    settings = Settings.from_env(data_dir=tmp_path)
    assert settings.model == "google/gemini-2.5-flash-lite"
    assert settings.base_url == "https://api.aicredits.in/v1"
    assert settings.data_dir == tmp_path


def test_prices_and_limits_are_decimal():
    pricing = load_pricing()
    assert pricing.global_limit_inr == Decimal(50)
    assert pricing.run_limit_inr == Decimal(4)
    assert pricing.models["google/gemini-2.5-flash"].input_per_million == Decimal("30.36")
