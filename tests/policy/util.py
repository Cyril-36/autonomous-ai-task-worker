from datetime import UTC, datetime
from types import SimpleNamespace

from worker.contracts import (
    Fact,
    FactType,
    FieldMapping,
    FillSource,
    GoalContract,
    GoalType,
    MutationIntent,
    Obligation,
    RequestConstraints,
    SourceRef,
)


def source():
    return SourceRef(kind="invoice", doc_id="ls-1042", revision="1",
                     supplier_id="larkspur-supplies", key="LS-1042")


def contract():
    return GoalContract(
        contract_id="c1", run_id="r1", goal_type=GoalType.register_invoice,
        constraints=RequestConstraints(supplier_text="Larkspur Supplies", selector="latest"),
        supplier_id="larkspur-supplies", supplier_name="Larkspur Supplies",
        sources=[source()],
        field_map=[FieldMapping(target_field="invoice_number", source_label="Invoice number",
                                type=FactType.text),
                   FieldMapping(target_field="amount", source_label="Amount", type=FactType.amount),
                   FieldMapping(target_field="currency", source_label="Currency", type=FactType.text),
                   FieldMapping(target_field="due_date", source_label="Due date", type=FactType.date)],
        obligations=[Obligation(obligation_id="o1", kind="record_fields", description="Fields match")],
        locked_at=datetime(2026, 10, 3, tzinfo=UTC),
    )


def intent():
    return MutationIntent(
        mutation_id="m1", run_id="r1", origin="http://127.0.0.1:8102",
        action_url="http://127.0.0.1:8102/invoices",
        fields={"form_token": "t1", "supplier_id": "larkspur-supplies",
                "invoice_number": "LS-1042", "amount": "48250.00", "currency": "INR",
                "due_date": "2026-11-01", "source_doc_id": "ls-1042"},
        filled_from={field: FillSource(kind="fact", fact_key=field)
                     for field in ("invoice_number", "amount", "currency", "due_date")},
        form_token="t1", target_key={"supplier_id": "larkspur-supplies",
                                      "invoice_number": "LS-1042"}, source=source(),
    )


def state():
    facts = {
        field: Fact(key=field, value=value, normalized=normalized, type=kind,
                    observation_id="o1", url="http://127.0.0.1:8101/invoices/ls-1042",
                    doc_id="ls-1042", revision="1", field_locator=label)
        for field, label, value, normalized, kind in [
            ("invoice_number", "Invoice number", "LS-1042", "LS-1042", FactType.text),
            ("amount", "Amount", "₹48,250.00", "48250.00", FactType.amount),
            ("currency", "Currency", "INR", "INR", FactType.text),
            ("due_date", "Due date", "1 Nov 2026", "2026-11-01", FactType.date),
        ]
    }
    return SimpleNamespace(
        run_id="r1", phase="execute", contract=contract(), facts=facts,
        source_values={"ls-1042": {"Invoice number": "LS-1042", "Amount": "48250.00",
                                   "Currency": "INR", "Due date": "2026-11-01"}},
        allowed_origins={"http://127.0.0.1:8102"}, pending=[], approvals=[],
        policy={"threshold": "100000.00", "version": 1}, user_messages=["Register LS-1042"],
    )
