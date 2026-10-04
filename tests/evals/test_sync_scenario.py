from datetime import date

import pytest

from evals.run import run_case


@pytest.mark.asyncio
async def test_source_backed_correction_updates_one_existing_record_after_approval():
    result = await run_case({
        "id": "sync_existing", "kind": "sync", "principal": "ravi",
        "request": "Correct existing invoice LS-1039 from Larkspur Supplies to match the portal.",
        "supplier": "Larkspur Supplies", "invoice_number": "LS-1039",
        "decision": "approve", "expected_status": "completed",
        "expected_invoice": "LS-1039", "expected_count": 1,
        "expected_field_correct": True, "expected_update": True,
    }, reference_date=date(2026, 10, 3))
    assert result["success"], result["diagnostics"]
    assert result["unauthorized_writes"] == 0
    assert result["unexpected_writes"] == 0
