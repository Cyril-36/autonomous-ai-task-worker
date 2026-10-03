from decimal import Decimal

import pytest

from worker.config import ModelPrice, Pricing
from worker.llm.ledger import BudgetExceeded, Ledger


@pytest.fixture
def ledger(tmp_path):
    pricing = Pricing("test", "2026-10-03", Decimal("0.05"), Decimal("0.03"),
                      {"test": ModelPrice(Decimal(100), Decimal(100))})
    return Ledger(tmp_path / "worker.db", pricing)


def test_reserves_before_dispatch_and_refuses_over_budget(ledger):
    request = {"messages": [{"role": "user", "content": "hello"}], "tools": [], "max_tokens": 100}
    entry = ledger.reserve("run1", "test", request)
    assert entry.state == "reserved"
    assert entry.reserved_inr > Decimal("0.01")
    with pytest.raises(BudgetExceeded):
        ledger.reserve("run1", "test", request)
    assert len(ledger.entries("run1")) == 1


def test_gateway_cost_settles_even_when_visible_tokens_understate_it(ledger):
    request = {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 100}
    entry = ledger.reserve("run1", "test", request)
    settled = ledger.settle(entry.entry_id, {"prompt_tokens": 2, "completion_tokens": 1,
                                            "total_tokens": 21, "cost": 0.017})
    assert settled.state == "settled"
    assert settled.settled_inr == Decimal("0.017")
    assert ledger.spent("run1") == Decimal("0.017")


def test_missing_usage_charges_full_reservation_and_retry_reserves_again(ledger):
    request = {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 30}
    first = ledger.reserve("run1", "test", request)
    charged = ledger.settle(first.entry_id, None)
    assert charged.state == "charged_unknown"
    assert charged.settled_inr == first.reserved_inr
    second = ledger.reserve("run1", "test", request)
    assert second.entry_id != first.entry_id
    assert len(ledger.entries("run1")) == 2


def test_observed_completion_over_max_expands_future_reservation(ledger):
    request = {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 5}
    first = ledger.reserve("run1", "test", request)
    ledger.settle(first.entry_id, {"prompt_tokens": 2, "completion_tokens": 9,
                                   "total_tokens": 11})
    second = ledger.reserve("run1", "test", request)
    assert second.reserved_inr > first.reserved_inr
    assert ledger.output_bound_enforced("test") is False


def test_unaccounted_total_tokens_expand_future_output_reservation(ledger):
    request = {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 5}
    first = ledger.reserve("run1", "test", request)
    ledger.settle(first.entry_id, {"prompt_tokens": 2, "completion_tokens": 1,
                                   "total_tokens": 13, "cost": "0.002"})
    assert ledger.reserve("run1", "test", request).reserved_inr > first.reserved_inr
