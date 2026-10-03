"""Shared data contracts for the task worker.

Frozen before parallel work (spec §9). Backend modules and the console API are
built against these types; change them only together with docs/INTERFACES.md.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# --- identity -------------------------------------------------------------


class Principal(Frozen):
    user_id: str
    email: str
    display_name: str
    role: Literal["admin", "operator"]


# --- observation (spec §4.2) ----------------------------------------------


class Element(Frozen):
    ref: str  # "e12", valid only for the observation that produced it
    role: str  # textbox | button | link | combobox | checkbox | textarea | date
    name: str  # accessible name / label
    value: str | None = None  # current value; never populated for secret fields
    form_id: str | None = None
    submits_form: bool = False
    options: list[str] = Field(default_factory=list)
    href: str | None = None


class DocField(Frozen):
    label: str
    value: str


class DocBlock(Frozen):
    """A <dl> block rendered by a page that exposes data-doc-id / data-revision."""

    doc_id: str
    revision: str
    kind: Literal["invoice", "message", "record"]
    fields: list[DocField]


class Observation(Frozen):
    observation_id: str
    run_id: str
    step: int
    url: str
    title: str
    text: str  # truncated visible text
    elements: list[Element]
    documents: list[DocBlock] = Field(default_factory=list)
    content_hash: str
    screenshot_path: str | None = None


# --- facts and provenance (spec §5) -----------------------------------------


class FactType(str, Enum):
    amount = "amount"
    date = "date"
    text = "text"


class Fact(Frozen):
    key: str
    value: str  # as displayed
    normalized: str  # Decimal string with 2 places, ISO date, or trimmed text
    type: FactType
    observation_id: str
    url: str
    doc_id: str | None
    revision: str | None
    field_locator: str  # <dl> label or element ref


class FillSource(Frozen):
    kind: Literal["fact", "user_literal", "free_text", "page_default"]
    fact_key: str | None = None


# --- goal contract (spec §3) ------------------------------------------------


class GoalType(str, Enum):
    register_invoice = "register_invoice"
    check_or_register_invoice = "check_or_register_invoice"
    register_batch = "register_batch"
    update_supplier_contact = "update_supplier_contact"
    export_invoices = "export_invoices"


Selector = Literal["latest", "invoice_number", "all_unregistered", "message", "filter"]


class SourceRef(Frozen):
    app: Literal["portal"] = "portal"
    kind: Literal["invoice", "message"]
    doc_id: str
    revision: str
    supplier_id: str
    key: str  # invoice number or message id


class RequestConstraints(Frozen):
    supplier_text: str | None = None
    selector: Selector | None = None
    invoice_numbers: list[str] = Field(default_factory=list)
    dates: list[date] = Field(default_factory=list)
    cap: int | None = None


class Criterion(Frozen):
    """Extra model-written criterion; may add to obligations, never replace them."""

    probe: str
    where: dict[str, str]
    expect: dict[str, str]


class GoalProposal(Frozen):
    """Arguments of the commit_goal / revise_goal tools."""

    goal_type: GoalType
    supplier: str | None = None
    selector: Selector | None = None
    invoice_number: str | None = None
    source_doc_id: str | None = None
    max_count: int | None = None
    due_before: date | None = None
    extra_criteria: list[Criterion] = Field(default_factory=list)


class FieldMapping(Frozen):
    target_field: str  # register form field name
    source_label: str  # portal <dl> label
    type: FactType


ObligationKind = Literal[
    "supplier_resolved",
    "source_is_latest",
    "record_count",
    "record_fields",
    "no_write",
    "batch_complete",
    "contact_fields",
    "export_rows",
    "approval_recorded",
    "extra",
]


class Obligation(Frozen):
    obligation_id: str
    kind: ObligationKind
    description: str  # human-readable, shown in the console
    params: dict[str, Any] = Field(default_factory=dict)


class GoalContract(Frozen):
    contract_id: str
    run_id: str
    goal_type: GoalType
    constraints: RequestConstraints
    supplier_id: str | None
    supplier_name: str | None
    sources: list[SourceRef]  # one per record to write (frozen batch "selected")
    batch_remaining: list[SourceRef] = Field(default_factory=list)
    filter: dict[str, str] | None = None
    field_map: list[FieldMapping] = Field(default_factory=list)
    obligations: list[Obligation]
    locked_at: datetime
    revision: int = 1


# --- tools ------------------------------------------------------------------


class PlanStep(Frozen):
    text: str
    status: Literal["todo", "doing", "done", "blocked"] = "todo"


# --- writes, gate, approvals (spec §6, §7) ----------------------------------


class MutationIntent(Frozen):
    mutation_id: str
    run_id: str
    origin: str
    method: Literal["POST"] = "POST"
    action_url: str
    fields: dict[str, str]  # complete normalized form body incl. hidden fields
    secret_fields: list[str] = Field(default_factory=list)
    filled_from: dict[str, FillSource] = Field(default_factory=dict)
    form_token: str | None = None
    target_key: dict[str, str] | None = None
    target_version: int | None = None
    source: SourceRef | None = None


class FileWriteIntent(Frozen):
    mutation_id: str
    run_id: str
    path: str  # relative to workspace/, must be under exports/
    probe_query: dict[str, str]


class NetworkAllowance(Frozen):
    run_id: str
    mutation_id: str
    method: str
    url: str
    body: dict[str, str]


GateCode = Literal[
    "allowed",
    "needs_approval",
    "phase_discover",
    "no_contract",
    "origin_blocked",
    "path_blocked",
    "provenance_failed",
    "field_mismatch",
    "source_mismatch",
    "pending_unresolved",
    "approval_invalid",
    "filename_invalid",
    "query_mismatch",
    "not_a_mutation",
]


class GateDecision(Frozen):
    allowed: bool
    code: GateCode
    reason: str  # human-readable; shown to model and console
    approval_id: str | None = None


class ApprovalStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    used = "used"
    expired = "expired"
    invalidated = "invalidated"


class ValueChange(Frozen):
    field: str
    old: str | None
    new: str


class Approval(Frozen):
    approval_id: str
    run_id: str
    intent_hash: str
    reason: str  # which policy rule triggered it
    changes: list[ValueChange]
    target_label: str  # e.g. "Invoice LS-1042 · Larkspur Supplies"
    target_version: int | None
    policy_version: int
    expires_at: datetime
    status: ApprovalStatus = ApprovalStatus.pending
    decided_by: str | None = None
    decided_at: datetime | None = None


PendingState = Literal["dispatching", "committed", "rejected", "voided", "conflict"]


class PendingMutation(Frozen):
    mutation_id: str
    run_id: str
    form_token: str | None
    target_key: dict[str, str]
    before_values: dict[str, str] | None
    before_version: int | None
    intended_values: dict[str, str]
    state: PendingState
    reason: str | None = None
    retries: int = 0


# --- budget (spec §8.2) -----------------------------------------------------


class LedgerEntry(Frozen):
    entry_id: str
    run_id: str
    model: str
    reserved_inr: Decimal
    settled_inr: Decimal | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    state: Literal["reserved", "settled", "charged_unknown"]
    created_at: datetime


# --- verification and run lifecycle (spec §8.4, §8.6) ----------------------


class RunStatus(str, Enum):
    queued = "queued"
    running = "running"
    awaiting_input = "awaiting_input"
    awaiting_approval = "awaiting_approval"
    completed = "completed"
    partial = "partial"
    blocked = "blocked"
    failed = "failed"
    unsupported = "unsupported"
    interrupted = "interrupted"


TERMINAL_STATUSES = {
    RunStatus.completed,
    RunStatus.partial,
    RunStatus.blocked,
    RunStatus.failed,
    RunStatus.unsupported,
}

Phase = Literal["setup", "discover", "execute", "verify", "done"]


class CheckResult(Frozen):
    obligation_id: str
    description: str
    passed: bool
    expected: str | None = None
    actual: str | None = None
    detail: str | None = None


class EvidenceItem(Frozen):
    label: str
    value: str
    url: str | None = None  # link into a sandbox app
    screenshot_path: str | None = None


class VerificationResult(Frozen):
    run_id: str
    contract_id: str
    passed: bool
    checks: list[CheckResult]
    status: RunStatus
    summary: str  # rendered from checks, never from model text
    evidence: list[EvidenceItem] = Field(default_factory=list)
    remaining: list[str] = Field(default_factory=list)  # e.g. batch items beyond cap


RunEventType = Literal[
    "run_status",
    "phase",
    "plan",
    "step",
    "fact",
    "contract",
    "gate",
    "approval",
    "question",
    "answer",
    "pending",
    "verification",
    "cost",
    "error",
]


class RunEvent(Frozen):
    run_id: str
    seq: int  # strictly increasing per run, starts at 1
    ts: datetime
    type: RunEventType
    data: dict[str, Any]  # shape per type: docs/INTERFACES.md §Events


class RunSummary(Frozen):
    run_id: str
    request: str
    principal: Principal
    status: RunStatus
    phase: Phase
    created_at: datetime
    updated_at: datetime
    steps: int
    cost_inr: Decimal
    model: str
