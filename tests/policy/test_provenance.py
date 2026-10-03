from types import SimpleNamespace

import pytest

from worker.contracts import DocBlock, DocField, FactType, Observation
from worker.policy.provenance import check_fill, record_fact


def observed_state():
    observation = Observation(
        observation_id="o1", run_id="r1", step=1, url="http://portal/invoices/d1",
        title="Invoice", text="Amount ₹48,250.00", elements=[],
        documents=[DocBlock(doc_id="d1", revision="1", kind="invoice",
                            fields=[DocField(label="Amount", value="₹48,250.00")])],
        content_hash="hash",
    )
    return SimpleNamespace(observations={"o1": observation}, facts={},
                           user_messages=["Use 48250.00"], request="Use 48250.00")


def test_record_fact_copies_observed_value_with_source_identity():
    state = observed_state()
    fact = record_fact(state, "amount", "o1", "Amount", FactType.amount)
    assert fact.value == "₹48,250.00"
    assert fact.normalized == "48250.00"
    assert (fact.doc_id, fact.revision) == ("d1", "1")
    assert state.facts["amount"] == fact
    with pytest.raises(ValueError):
        record_fact(state, "bad", "o1", "Due date", FactType.date)


def test_fill_requires_observed_fact_or_exact_user_literal():
    state = observed_state()
    record_fact(state, "amount", "o1", "Amount", FactType.amount)
    assert check_fill(state, "fact", "48250.00", "amount", FactType.amount)
    assert not check_fill(state, "fact", "100.00", "amount", FactType.amount)
    assert check_fill(state, "user_literal", "48250.00", None, FactType.amount)
    assert not check_fill(state, "user_literal", "999.00", None, FactType.amount)
    assert not check_fill(state, "free_text", "anything", None, FactType.text,
                          obligation_checked=True)
