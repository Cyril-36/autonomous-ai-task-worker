from worker.runtime.memory import chosen_candidate


def test_supplier_answer_uses_positive_or_exclusion_evidence():
    choices = ["Larkspur Supplies", "Larkspur Logistics"]
    assert chosen_candidate("logistics", choices) == "Larkspur Logistics"
    assert chosen_candidate("the Logistics one", choices) == "Larkspur Logistics"
    assert chosen_candidate("Not Larkspur Supplies, the other one", choices) == "Larkspur Logistics"
    assert chosen_candidate("Not Larkspur Supplies", choices) == "Larkspur Logistics"
    assert chosen_candidate("Larkspur", choices) is None
    assert chosen_candidate("the other one", choices, suggested="Larkspur Supplies") == "Larkspur Logistics"
