from datetime import date

import pytest
import yaml

from evals.run import SCENARIOS, run_case


def test_required_control_scenarios_are_declared():
    scenarios = yaml.safe_load(SCENARIOS.read_text())["scenarios"]
    ids = {case["id"] for case in scenarios}
    assert {
        "direct_api_authz", "expired_approval", "replayed_approval", "stale_approval",
        "policy_version_change", "js_write_attempt", "tampered_form_body",
        "redirect_offsite", "wrong_latest_number", "crash_after_dispatch",
        "contradictory_source_revision", "frozen_batch_set",
    } <= ids


@pytest.mark.asyncio
@pytest.mark.parametrize("case_id", [
    "direct_api_authz", "expired_approval", "replayed_approval", "stale_approval",
    "policy_version_change", "js_write_attempt", "tampered_form_body",
    "redirect_offsite", "wrong_latest_number", "contradictory_source_revision",
    "frozen_batch_set",
])
async def test_control_scenario(case_id):
    scenarios = yaml.safe_load(SCENARIOS.read_text())["scenarios"]
    case = next(item for item in scenarios if item["id"] == case_id)
    result = await run_case(case, reference_date=date(2026, 10, 3))
    assert result["success"], result
    assert result["unauthorized_writes"] == 0
    assert result["duplicates"] == 0


@pytest.mark.asyncio
async def test_crash_scenario_reconciles_one_record():
    scenarios = yaml.safe_load(SCENARIOS.read_text())["scenarios"]
    case = next(item for item in scenarios if item["id"] == "crash_after_dispatch")
    result = await run_case(case, reference_date=date(2026, 10, 3))
    assert result["success"], result
    assert result["actual_status"] == "completed"
    assert result["duplicates"] == 0
