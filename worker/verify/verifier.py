"""Independent checks for every required goal obligation."""

from __future__ import annotations

from collections import Counter

from worker.contracts import (
    CheckResult,
    EvidenceItem,
    GoalContract,
    GoalType,
    RunStatus,
    VerificationResult,
)
from worker.policy.normalize import normalize
from worker.tools.files import EXPORT_COLUMNS


def _check(obligation, passed: bool, *, expected: str | None = None,
           actual: str | None = None, detail: str | None = None) -> CheckResult:
    return CheckResult(obligation_id=obligation.obligation_id,
                       description=obligation.description, passed=passed,
                       expected=expected, actual=actual, detail=detail)


def _record_matches(saved: dict, source: dict) -> bool:
    try:
        return (
            saved["supplier_id"] == source["supplier_id"]
            and saved["invoice_number"] == source["invoice_number"]
            and normalize(saved["amount"], "amount") == normalize(source["amount"], "amount")
            and saved["currency"] == source["currency"]
            and normalize(saved["due_date"], "date") == normalize(source["due_date"], "date")
        )
    except (KeyError, ValueError):
        return False


async def verify(contract: GoalContract, probes, *, export_path: str | None = None) -> VerificationResult:
    checks = []
    evidence = []
    source_docs = {}
    for ref in contract.sources:
        source_docs[ref.doc_id] = await probes.portal_document(ref.doc_id)
    saved_rows = await probes.register_invoices(supplier_id=contract.supplier_id)
    supplier_rows = await probes.register_suppliers()
    for obligation in contract.obligations:
        kind = obligation.kind
        if kind == "supplier_resolved":
            matches = [row for row in supplier_rows if row["id"] == contract.supplier_id]
            checks.append(_check(obligation, len(matches) == 1, expected="1",
                                 actual=str(len(matches))))
        elif kind == "source_is_latest":
            portal = await probes.portal_invoices(contract.supplier_id)
            newest = max((row["issue_date"] for row in portal), default=None)
            matches = [row for row in portal if row["issue_date"] == newest]
            passed = len(matches) == 1 and bool(contract.sources) and (
                matches[0]["doc_id"] == contract.sources[0].doc_id
                and str(matches[0]["revision"]) == contract.sources[0].revision
            )
            checks.append(_check(obligation, passed, expected=contract.sources[0].doc_id,
                                 actual=matches[0]["doc_id"] if len(matches) == 1 else "tie/missing"))
        elif kind == "record_count":
            counts = [sum(row["supplier_id"] == ref.supplier_id and
                          row["invoice_number"] == ref.key for row in saved_rows)
                      for ref in contract.sources]
            passed = all(count == 1 for count in counts)
            checks.append(_check(obligation, passed, expected="1 each",
                                 actual=", ".join(map(str, counts))))
        elif kind == "record_fields":
            mismatches = []
            for ref in contract.sources:
                rows = [row for row in saved_rows if row["supplier_id"] == ref.supplier_id
                        and row["invoice_number"] == ref.key]
                doc = source_docs[ref.doc_id]
                frozen = obligation.params.get("source_values", {}).get(ref.doc_id, {})
                source_intact = all(str(doc.get(label.casefold().replace(" ", "_"))) == value
                                    for label, value in frozen.items())
                expected = {
                    "supplier_id": ref.supplier_id,
                    "invoice_number": frozen.get("Invoice number", ref.key),
                    "amount": frozen.get("Amount", ""),
                    "currency": frozen.get("Currency", ""),
                    "due_date": frozen.get("Due date", ""),
                }
                if (str(doc["revision"]) != ref.revision or not source_intact
                        or len(rows) != 1 or not _record_matches(rows[0], expected)):
                    mismatches.append(ref.key)
                else:
                    evidence.append(EvidenceItem(label="Saved invoice", value=ref.key,
                                                 url=f"http://127.0.0.1:8102/invoices/{rows[0].get('id', '')}"))
            checks.append(_check(obligation, not mismatches,
                                 expected="Amount, currency and due date equal frozen source",
                                 actual="mismatch: " + ", ".join(mismatches) if mismatches else "all match"))
        elif kind == "no_write":
            target = next((row for row in saved_rows if str(row.get("id", "")) ==
                           obligation.params.get("record_id")), None)
            passed = target is not None and str(target.get("version", "")) == obligation.params.get("version")
            checks.append(_check(obligation, passed, expected=obligation.params.get("version"),
                                 actual=str(target.get("version")) if target else None))
        elif kind == "batch_complete":
            remaining = [ref.key for ref in contract.batch_remaining]
            checks.append(_check(obligation, not remaining, expected="0 remaining",
                                 actual=str(len(remaining))))
        elif kind == "contact_fields":
            ref = contract.sources[0]
            saved = await probes.register_supplier(ref.supplier_id)
            doc = source_docs[ref.doc_id]
            frozen = obligation.params.get("source_values", {}).get(ref.doc_id, {})
            passed = str(doc["revision"]) == ref.revision and all(
                saved.get(field) == frozen.get(field.replace("_", " ").capitalize())
                for field in ("contact_name", "contact_email", "remittance_email")
            )
            checks.append(_check(obligation, passed, expected="source contact fields",
                                 actual="match" if passed else "mismatch"))
        elif kind == "approval_recorded":
            passed = await probes.approval_recorded(contract.run_id)
            checks.append(_check(obligation, passed, expected="approved", actual=str(passed)))
        elif kind == "export_rows":
            filter_values = contract.filter or {}
            expected_rows = await probes.register_invoices(
                supplier_id=filter_values.get("supplier_id"),
                due_before=filter_values.get("due_before"),
            )
            actual_rows = await probes.workspace_csv(export_path) if export_path else None
            expected = Counter(tuple(str(row.get(column, "")) for column in EXPORT_COLUMNS)
                               for row in expected_rows)
            actual = Counter(tuple(str(row.get(column, "")) for column in EXPORT_COLUMNS)
                             for row in actual_rows or [])
            declared_columns = getattr(actual_rows, "columns", None)
            columns_ok = actual_rows is not None and (
                set(declared_columns) == set(EXPORT_COLUMNS) if declared_columns is not None
                else bool(actual_rows) and all(set(row) == set(EXPORT_COLUMNS)
                                               for row in actual_rows)
            )
            passed = columns_ok and expected == actual
            checks.append(_check(obligation, passed, expected=f"{len(expected_rows)} rows",
                                 actual=f"{len(actual_rows) if actual_rows is not None else 0} rows",
                                 detail="correct columns and exact multiset" if passed else "Missing, extra or incorrect row/column"))
            if passed and export_path:
                evidence.append(EvidenceItem(
                    label="Export", value=export_path,
                    download_url=(f"/api/runs/{contract.run_id}/exports/"
                                  f"{export_path.rsplit('/', 1)[-1]}")))
        elif kind == "extra":
            criterion = obligation.params
            where = criterion["where"]
            rows = await probes.register_invoices(supplier_id=where["supplier_id"])
            matching = [row for row in rows if row["invoice_number"] == where["invoice_number"]]
            passed = len(matching) == 1 and all(
                str(matching[0].get(key)) == value
                for key, value in criterion["expect"].items()
            )
            checks.append(_check(obligation, passed, expected=str(criterion["expect"]),
                                 actual=str(matching[0]) if len(matching) == 1 else
                                 f"{len(matching)} rows"))
        else:
            checks.append(_check(obligation, False, detail="Unknown obligation"))
    all_passed = all(check.passed for check in checks)
    remaining = [ref.key for ref in contract.batch_remaining]
    status = RunStatus.completed if all_passed else (
        RunStatus.partial if contract.goal_type == GoalType.register_batch and remaining and
        all(check.passed for check in checks if check.obligation_id != "batch_complete")
        else RunStatus.failed
    )
    summary = (
        f"{sum(check.passed for check in checks)}/{len(checks)} obligations verified; "
        f"status {status.value}."
    )
    return VerificationResult(
        run_id=contract.run_id, contract_id=contract.contract_id,
        passed=status == RunStatus.completed, checks=checks, status=status,
        summary=summary, evidence=evidence, remaining=remaining,
    )
