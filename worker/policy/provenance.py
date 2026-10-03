"""Source-bound facts copied by code from stored observations."""

from __future__ import annotations

from worker.contracts import Fact, FactType
from worker.policy.normalize import normalize


def record_fact(state, key: str, observation_id: str, field_locator: str,
                kind: FactType) -> Fact:
    if key in state.facts:
        raise ValueError(f"Fact key {key} was already recorded; use a distinct field key")
    observation = state.observations.get(observation_id)
    if observation is None:
        raise ValueError("Unknown observation")
    candidates = [
        (field.value, block.doc_id, block.revision)
        for block in observation.documents for field in block.fields
        if field.label == field_locator
    ]
    candidates.extend(
        (element.value, None, None) for element in observation.elements
        if element.ref == field_locator and element.value is not None
    )
    if len(candidates) != 1:
        raise ValueError("Field locator does not identify exactly one observed value")
    value, doc_id, revision = candidates[0]
    fact = Fact(
        key=key, value=value, normalized=normalize(value, kind), type=kind,
        observation_id=observation_id, url=observation.url, doc_id=doc_id,
        revision=revision, field_locator=field_locator,
    )
    state.facts[key] = fact
    return fact


def check_fill(
    state, kind: str, value: str, fact_key: str | None, value_type: FactType,
    *, obligation_checked: bool = False, free_text_field: bool = False,
) -> bool:
    if kind == "fact":
        fact = state.facts.get(fact_key)
        return bool(fact and fact.type == value_type and fact.normalized == value)
    if kind == "user_literal":
        try:
            normalized = normalize(value, value_type)
        except ValueError:
            return False
        return any(value in message or normalized in message
                   for message in state.user_messages)
    if kind == "free_text":
        return bool(free_text_field and not obligation_checked and len(value) <= 500)
    return kind == "page_default" and not obligation_checked
