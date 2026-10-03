"""Sequential model-chosen work with code-owned writes and verification."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from playwright.async_api import Error as PlaywrightError

from worker.contracts import (
    Approval,
    ApprovalStatus,
    Fact,
    FactType,
    FileWriteIntent,
    FillSource,
    GoalProposal,
    MutationIntent,
    NetworkAllowance,
    RunStatus,
)
from worker.llm.ledger import BudgetExceeded
from worker.llm.provider import ProviderError
from worker.policy.approvals import create_approval, validate_approval
from worker.policy.gate import check_file_write, check_mutation
from worker.policy.pending import begin_pending, reconcile
from worker.policy.provenance import record_fact
from worker.runtime.apps import Apps
from worker.runtime.prompts import build_messages
from worker.runtime.recovery import reconcile_all
from worker.runtime.stall import StallDetector
from worker.runtime.state import RuntimeState, load_state, save_state
from worker.tools.files import WorkspaceFiles
from worker.tools.registry import tools_for_phase, validate_call
from worker.verify.goals import GoalRejection, commit_goal, revise_goal
from worker.verify.verifier import verify

PAGE_CHANGING = {"browser_navigate", "browser_click", "browser_fill",
                 "browser_fill_fact", "browser_fill_text", "browser_fill_literal",
                 "browser_select", "open_page", "fill_form", "submit_form"}
FILLABLE = {"textbox", "date", "textarea", "combobox"}


def _norm_label(text: str) -> str:
    return " ".join(text.replace("*", " ").replace(":", " ").split()).casefold()


def _slug(text: str) -> str:
    return "_".join(_norm_label(text).split())


def find_by_label(observation, label: str, roles: set[str] = FILLABLE):
    """Resolve a visible field label to one element; select names include their options."""
    wanted = _norm_label(label)
    fields = [item for item in observation.elements if item.role in roles]
    exact = [item for item in fields if _norm_label(item.name) == wanted]
    matches = exact or [item for item in fields if _norm_label(item.name).startswith(wanted + " ")]
    if len(matches) != 1:
        labels = sorted({item.name.split("  ")[0][:40] for item in fields})
        problem = "matches several fields" if matches else "is not a field on this page"
        raise ValueError(f"Label '{label}' {problem}. Fields here: {', '.join(labels)}")
    return matches[0]


def action_line(step: int, name: str, args: dict, result: dict) -> str:
    """One compact line of the model's own history: what it did and what happened."""
    shown = {key: value for key, value in args.items() if key != "observation_id"}
    text = json.dumps(shown, ensure_ascii=False, default=str)
    if len(text) > 180:
        text = text[:177] + "..."
    status = "ok" if result.get("ok") else "FAILED"
    return f"#{step} {name} {text} -> {status}: {str(result.get('summary', ''))[:300]}"


def ready_to_finish(state: RuntimeState) -> bool:
    """Prompt verification once all frozen write targets have settled."""
    if state.contract is None or state.verify_rounds or state.phase != "execute":
        return False
    if state.export_path:
        return True
    if not state.contract.sources:
        return False
    committed = [item.target_key for item in state.pending if item.state == "committed"]
    for source in state.contract.sources:
        target = {"supplier_id": source.supplier_id}
        if source.kind == "invoice":
            target["invoice_number"] = source.key
        if target not in committed:
            return False
    return True


class WorkerLoop:
    def __init__(self, *, store, provider, browser, probes, workspace: WorkspaceFiles | Path | None,
                 portal_url: str, register_url: str, trace=None, stop_after_goal: bool = False):
        self.store = store
        self.provider = provider
        self.browser = browser
        self.probes = probes
        self.workspace = (workspace if isinstance(workspace, WorkspaceFiles) or workspace is None
                          else WorkspaceFiles(workspace))
        self.portal_url = portal_url
        self.register_url = register_url
        self.trace = trace
        # evaluation of request understanding only: end the run once a goal is locked
        self.stop_after_goal = stop_after_goal
        self.apps = Apps.load({"portal": portal_url, "register": register_url})

    def _emit(self, run_id: str, kind: str, data: dict) -> None:
        self.store.append_event(run_id, kind, data)
        if self.trace:
            self.trace.append(kind, data)

    def _phase(self, state: RuntimeState, phase: str) -> None:
        state.phase = phase
        self.store.update_run(state.run_id, phase=phase)
        self._emit(state.run_id, "phase", {"phase": phase})
        self._checkpoint(state)

    def _checkpoint(self, state: RuntimeState) -> None:
        save_state(self.store.path, state)

    def _terminal(self, state: RuntimeState, status: RunStatus, reason: str) -> None:
        self._phase(state, "done")
        ledger = getattr(self.provider, "ledger", None)
        cost = ledger.spent(state.run_id) if ledger else None
        self.store.update_run(state.run_id, status=status.value, steps=state.steps,
                              cost_inr=cost)
        self._emit(state.run_id, "run_status", {"status": status.value, "reason": reason})

    async def run(self, run_id: str, *, max_steps: int = 60,
                  answer: str | None = None) -> None:
        run = self.store.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        state = load_state(self.store.path, run_id)
        if state is None:
            state = RuntimeState(run_id, [run.request], {self.portal_url, self.register_url})
            state.policy = await self.probes.register_policy() if self.probes else {"version": 1}
            state.pending = self.store.pending_for_run(run_id)
            self._phase(state, "setup")
            self.store.update_run(run_id, status="running")
            self._emit(run_id, "run_status", {"status": "running", "reason": "Signing in to sandbox apps."})
            self._phase(state, "discover")
        else:
            if state.phase == "done":
                return
            if answer:
                state.user_messages.append(answer)
                state.feedback.append("User answered: " + answer)
            if self.probes:
                decisions = await reconcile_all(self.store, run_id, self.probes)
                if any(item.pending.state == "conflict" for item in decisions):
                    self._terminal(state, RunStatus.blocked,
                                   "A prior write could not be safely reconciled.")
                    return
                state.pending = self.store.pending_for_run(run_id)
                state.wrote_business_data |= any(item.state == "committed" for item in state.pending)
                state.policy = await self.probes.register_policy()
            state.approvals = [Approval.model_validate(item)
                               for item in self.store.approvals(run_id)]
            if any(item.status == ApprovalStatus.rejected for item in state.approvals):
                self._terminal(state, RunStatus.blocked,
                               "The requested change was rejected. Nothing was saved.")
                return
            if any(item.status == ApprovalStatus.approved for item in state.approvals):
                state.feedback.append("Approval applies to the current form only. Click its "
                                      "existing Save control; do not navigate or change fields.")
            self.store.update_run(run_id, status="running")
            self._emit(run_id, "run_status", {"status": "running",
                                               "reason": "Continuing the saved run."})
            if self.browser and self.browser.page.url == "about:blank" and state.observations:
                latest = list(state.observations.values())[-1]
                await self.browser.navigate(latest.url)
                observed = await self.browser.snapshot()
                state.observations[observed.observation_id] = observed
                state.observations_text.append(observed.model_dump_json())
            self._checkpoint(state)
        stall = StallDetector()
        while state.steps < max_steps:
            messages = build_messages(run.request, phase=state.phase, contract=state.contract,
                                      observations=state.observations_text,
                                      facts=[item.model_dump(mode="json") for item in state.facts.values()],
                                      plan=state.plan, feedback=state.feedback,
                                      policy=state.policy, apps=self.apps)
            try:
                ready_to_verify = ready_to_finish(state)
                approved_form_pending = bool(
                    state.phase == "execute" and not state.wrote_business_data and
                    any(item.status == ApprovalStatus.approved for item in state.approvals)
                )
                response = await self.provider.complete(messages=messages,
                                                        tools=tools_for_phase(
                                                            state.phase,
                                                            allow_revision=state.verify_rounds > 0,
                                                            ready_to_verify=ready_to_verify,
                                                            approved_form_pending=
                                                            approved_form_pending),
                                                        max_tokens=512, run_id=run_id)
            except BudgetExceeded:
                self._terminal(state, RunStatus.blocked, "The estimated local spending limit was reached.")
                return
            except ProviderError as exc:
                status = RunStatus.blocked if exc.kind == "credit" else RunStatus.failed
                self._terminal(state, status, f"The model provider stopped: {exc.kind}.")
                return
            ledger = getattr(self.provider, "ledger", None)
            if ledger is not None:
                entry = next((item for item in ledger.entries(run_id)
                              if item.entry_id == response.entry_id), None)
                if entry:
                    spent = ledger.spent(run_id)
                    self.store.update_run(run_id, cost_inr=spent)
                    self._emit(run_id, "cost", {
                        "run_spent_inr": f"{spent:.2f}",
                        "run_limit_inr": f"{ledger.pricing.run_limit_inr:.2f}",
                        "global_spent_inr": f"{ledger.spent():.2f}",
                        "global_limit_inr": f"{ledger.pricing.global_limit_inr:.2f}",
                        "prompt_tokens": entry.prompt_tokens or 0,
                        "completion_tokens": entry.completion_tokens or 0,
                        "model": entry.model,
                    })
            if not response.tool_calls:
                state.steps += 1
                self._emit(run_id, "step", {"step": state.steps, "tool": "model_message",
                                             "args": {}, "ok": False,
                                             "summary": "Model returned no action", "duration_ms": 0})
                continue
            changed_page = False
            for call in response.tool_calls:
                state.steps += 1
                name = call["name"]
                args = call["arguments"]
                if call.get("invalid_arguments"):
                    result = {"ok": False, "summary": "Tool arguments were not valid JSON"}
                else:
                    try:
                        validate_call(name, args)
                        result = await self._dispatch(state, name, args)
                    except (ValueError, TypeError, KeyError, FileNotFoundError) as exc:
                        result = {"ok": False, "summary": str(exc)}
                    except PlaywrightError:
                        result = {"ok": False, "summary":
                                  "The browser action failed; re-observe the page or ask for help.",
                                  "error_code": "browser_error"}
                self._emit(run_id, "step", {"step": state.steps, "tool": name,
                                             "args": self._safe_args(args), "ok": result["ok"],
                                             "summary": result["summary"], "duration_ms": 0,
                                             **({"error_code": result["error_code"]}
                                                if result.get("error_code") else {}),
                                             **({"screenshot": result["screenshot"]}
                                                if result.get("screenshot") else {})})
                self.store.update_run(run_id, steps=state.steps)
                state.feedback.append(action_line(state.steps, name, self._safe_args(args), result))
                self._checkpoint(state)
                if name in PAGE_CHANGING and result["ok"]:
                    changed_page = True
                signal = stall.observe(name, args, progress=result.get("progress", False))
                if result.get("pause") or result.get("terminal"):
                    return
                if self.stop_after_goal and state.contract is not None:
                    return
                if signal == "reflect":
                    state.observations_text.append("Reflect on the stalled plan and choose a new action.")
                elif signal == "ask_user":
                    self._terminal(state, RunStatus.blocked,
                                   "The worker could not make progress without clarification.")
                    return
                if state.steps >= max_steps:
                    break
                if changed_page:
                    if len(response.tool_calls) > 1:
                        state.feedback.append("(Page changed, so the rest of that turn's calls "
                                              "were skipped. Use the new observation.)")
                    break
        self._terminal(state, RunStatus.blocked, "The run reached its step limit.")

    @staticmethod
    def _safe_args(args: dict) -> dict:
        return {key: "•••" if key in {"form_token", "password", "cookie"} else value
                for key, value in args.items()}

    async def _dispatch(self, state: RuntimeState, name: str, args: dict) -> dict:
        if name == "open_page":
            url = self.apps.url(args["app"], args["page"], args.get("id"))
            if self.browser.page.url == url and self.browser.current is not None:
                return {"ok": False, "summary": "Already on this page; use its current observation.",
                        "progress": False}
            await self.browser.navigate(url)
            observation = await self._observe(state)
            return {"ok": True, "summary": self._page_summary(observation), "progress": True}
        if name == "record_facts":
            return self._record_facts(state, args)
        if name == "fill_form":
            return await self._fill_form(state, args["fields"])
        if name == "submit_form":
            observation = self.browser.current or await self._observe(state)
            submits = [item for item in observation.elements if item.submits_form]
            if len(submits) != 1:
                return {"ok": False, "summary": "This page has no single form to submit."}
            return await self._submit(state, submits[0].ref)
        if name in {"browser_fill_fact", "browser_fill_text", "browser_fill_literal"}:
            name = "browser_fill"
        if name == "browser_navigate":
            if self.browser.page.url == args["url"]:
                return {"ok": False,
                        "summary": "Already on this page; use its current observation.",
                        "progress": False}
            await self.browser.navigate(args["url"])
            observation = await self._observe(state)
            return {"ok": True, "summary": f"Navigated and observed {observation.title}",
                    "progress": True}
        if name == "browser_snapshot":
            previous = list(state.observations.values())[-1] if state.observations else None
            observation = await self._observe(state)
            changed = previous is None or (previous.url, previous.content_hash) != (
                observation.url, observation.content_hash)
            return {"ok": True, "summary": "Observed page", "progress": changed}
        if name == "browser_fill":
            element = self._current_element(args["ref"])
            if "fact_key" in args:
                fact = state.facts[args["fact_key"]]
                value = fact.normalized
                source = FillSource(kind="fact", fact_key=fact.key)
            elif "user_literal" in args:
                value = args["user_literal"]
                source = FillSource(kind="user_literal")
            else:
                value = args["free_text"]
                source = FillSource(kind="free_text")
            if element.value == value:
                return {"ok": False,
                        "summary": f"{element.name} already has that value; move to the next field.",
                        "progress": False}
            await self.browser.fill(args["ref"], value)
            state.fills[element.name] = value
            state.fill_sources[element.name] = source
            await self._observe(state)
            return {"ok": True, "summary": f"Filled {element.name}", "progress": True}
        if name == "browser_select":
            element = self._current_element(args["ref"])
            await self.browser.select(args["ref"], args["option"])
            state.fills[element.name] = args["option"]
            await self._observe(state)
            return {"ok": True, "summary": f"Selected {element.name}", "progress": True}
        if name == "browser_click":
            element = self._current_element(args["ref"])
            if element.submits_form:
                return await self._submit(state, args["ref"])
            await self.browser.click(args["ref"])
            await self._observe(state)
            return {"ok": True, "summary": f"Clicked {element.name}", "progress": True}
        if name == "reauthenticate":
            await self.browser.reauthenticate(args["app"],
                                              principal=self.store.get_run(state.run_id).principal)
            return {"ok": True, "summary": "Session refreshed", "progress": True}
        if name == "record_fact":
            fact = record_fact(state, args["key"], args["observation_id"],
                               args["field_locator"], FactType(args["type"]))
            self._emit(state.run_id, "fact", {**fact.model_dump(mode="json"),
                                               "step": state.steps})
            return {"ok": True, "summary": f"Recorded {fact.key}", "progress": True}
        if name == "commit_goal":
            if state.phase != "discover":
                raise ValueError("Goal can only be committed during discovery")
            try:
                proposal = GoalProposal.model_validate(args["contract"])
            except ValueError:
                self._emit(state.run_id, "contract", {"action": "rejected",
                                                       "reason": "Unsupported task type"})
                self._terminal(state, RunStatus.unsupported,
                               "The request does not fit a supported task type.")
                return {"ok": False, "summary": "Unsupported task", "terminal": True}
            contract = await commit_goal(proposal, "\n".join(state.user_messages), self.probes,
                                         run_id=state.run_id)
            if isinstance(contract, GoalRejection):
                self._emit(state.run_id, "contract", {"action": "rejected",
                                                       "reason": contract.reason})
                if contract.code == "needs_clarification":
                    return self._question(state, contract.reason, contract.candidates)
                if contract.code == "unsupported":
                    self._terminal(state, RunStatus.unsupported, contract.reason)
                    return {"ok": False, "summary": contract.reason, "terminal": True}
                return {"ok": False, "summary": contract.reason}
            state.contract = contract
            state.source_values = next((item.params["source_values"]
                                        for item in contract.obligations
                                        if "source_values" in item.params), {})
            self._emit(state.run_id, "contract", {"action": "committed",
                                                   "contract": contract.model_dump(mode="json")})
            self._phase(state, "execute")
            self._goal_facts(state)
            sources = ", ".join(f"{source.key} ({source.doc_id})" for source in contract.sources)
            return {"ok": True,
                    "summary": "Goal locked." + (f" Sources: {sources}." if sources else ""),
                    "progress": True}
        if name == "revise_goal":
            if not state.contract:
                raise ValueError("No goal to revise")
            revised = revise_goal(state.contract, GoalProposal.model_validate(args["contract"]),
                                  wrote_business_data=state.wrote_business_data)
            if isinstance(revised, GoalRejection):
                return {"ok": False, "summary": revised.reason}
            state.contract = revised
            self._emit(state.run_id, "contract", {"action": "revised",
                                                   "contract": revised.model_dump(mode="json")})
            return {"ok": True, "summary": "Goal criteria revised", "progress": True}
        if name == "update_plan":
            state.plan = args["steps"]
            self._emit(state.run_id, "plan", {"steps": state.plan, "revision": 1,
                                              "reason": "Model plan"})
            return {"ok": True, "summary": "Plan updated"}
        if name == "files_list":
            return {"ok": True, "summary": json.dumps(self.workspace.list(args["path"]))}
        if name == "files_read":
            return {"ok": True, "summary": self.workspace.read(args["path"])[:8000]}
        if name == "files_write":
            return await self._write_export(state, args)
        if name == "ask_user":
            return self._question(state, args["question"], [])
        if name == "unsupported":
            reason = args["reason"].strip() or "The requested action is not supported."
            self._terminal(state, RunStatus.unsupported, reason[:500])
            return {"ok": True, "summary": reason[:500], "terminal": True}
        if name == "finish":
            if not state.contract:
                self._terminal(state, RunStatus.blocked,
                               "The worker did not lock a goal, so nothing can be verified.")
                return {"ok": False, "summary": "No locked goal", "terminal": True}
            self._phase(state, "verify")
            result = await verify(state.contract, self.probes, export_path=state.export_path)
            self._emit(state.run_id, "verification", result.model_dump(mode="json"))
            if result.status in {RunStatus.completed, RunStatus.partial}:
                self._terminal(state, result.status, result.summary)
                return {"ok": True, "summary": result.summary, "terminal": True}
            state.verify_rounds += 1
            if state.verify_rounds > 2:
                self._terminal(state, RunStatus.failed, result.summary)
                return {"ok": False, "summary": result.summary, "terminal": True}
            state.observations_text.append("Verification failed: " + result.summary + " " +
                                           json.dumps([item.model_dump(mode="json")
                                                       for item in result.checks]))
            self._phase(state, "execute")
            return {"ok": False, "summary": result.summary}
        raise ValueError("Unknown tool")

    @staticmethod
    def _page_summary(observation) -> str:
        parts = [f"Opened '{observation.title}'"]
        for block in observation.documents:
            labels = ", ".join(field.label for field in block.fields)
            parts.append(f"document {block.doc_id} revision {block.revision} with fields: {labels}")
        forms = [item.name.split("  ")[0][:40] for item in observation.elements
                 if item.role in FILLABLE]
        if forms:
            parts.append("form fields: " + ", ".join(forms))
        return "; ".join(parts)

    def _goal_facts(self, state: RuntimeState) -> None:
        """Values the locked goal already fixes; the model uses them, never re-types them."""
        contract = state.contract
        values = {}
        if contract.supplier_name:
            values["goal.supplier"] = contract.supplier_name
        for source in contract.sources:
            values[f"{source.doc_id}.document_id"] = source.doc_id
        for key, value in values.items():
            fact = Fact(key=key, value=value, normalized=value, type=FactType.text,
                        observation_id="goal", url="goal://locked", doc_id=None,
                        revision=None, field_locator=key)
            state.facts[key] = fact
            self._emit(state.run_id, "fact", {**fact.model_dump(mode="json"), "step": state.steps})

    def _record_facts(self, state: RuntimeState, args: dict) -> dict:
        if args.get("observation_id"):
            observation = state.observations.get(args["observation_id"])
        else:
            observation = next((item for item in reversed(list(state.observations.values()))
                                if item.documents), None)
        if observation is None or not observation.documents:
            return {"ok": False, "summary": "No labelled document is open. Open the document's "
                                            "page first."}
        types = ({item.source_label: item.type for item in state.contract.field_map}
                 if state.contract else {})
        available = {field.label for block in observation.documents for field in block.fields}
        recorded, missing = [], []
        for wanted in args["labels"]:
            label = next((item for item in available
                          if _norm_label(item) == _norm_label(str(wanted))), None)
            if label is None:
                missing.append(str(wanted))
                continue
            block = next(item for item in observation.documents
                         if any(field.label == label for field in item.fields))
            key = f"{block.doc_id}.{_slug(label)}"
            state.facts.pop(key, None)
            fact = record_fact(state, key, observation.observation_id, label,
                               types.get(label, FactType.text))
            self._emit(state.run_id, "fact", {**fact.model_dump(mode="json"), "step": state.steps})
            recorded.append(f"{key} = {fact.normalized}")
        if not recorded:
            return {"ok": False, "summary": f"None of those labels are on this document. "
                                            f"Labels here: {', '.join(sorted(available))}"}
        note = f" Not found: {', '.join(missing)}." if missing else ""
        return {"ok": True, "summary": "Recorded " + "; ".join(recorded) + "." + note,
                "progress": True}

    async def _fill_form(self, state: RuntimeState, items: list) -> dict:
        observation = self.browser.current or await self._observe(state)
        plan = []
        for item in items:
            if not isinstance(item, dict) or "label" not in item or \
                    sum(key in item for key in ("fact", "text")) != 1:
                return {"ok": False, "summary": "Each field needs a label and exactly one of "
                                                "fact or text."}
            element = find_by_label(observation, item["label"])
            if "fact" in item:
                fact = state.facts.get(item["fact"])
                if fact is None:
                    known = ", ".join(sorted(state.facts)) or "none yet"
                    return {"ok": False, "summary": f"Unknown fact {item['fact']}. Facts: {known}"}
                plan.append((item["label"], element, fact.normalized,
                             FillSource(kind="fact", fact_key=fact.key)))
            else:
                plan.append((item["label"], element, str(item["text"]),
                             FillSource(kind="free_text")))
        filled, unchanged = [], []
        for label, element, value, source in plan:
            current = self.browser.current or await self.browser.snapshot()
            element = find_by_label(current, label)
            if element.role == "combobox":
                if value not in element.options:
                    return {"ok": False, "summary": f"'{value}' is not an option for {label}. "
                                                    f"Options: {', '.join(element.options)}"}
                await self.browser.select(element.ref, value)
            elif element.value == value:
                unchanged.append(label)
                continue
            else:
                await self.browser.fill(element.ref, value)
            state.fills[element.name] = value
            state.fill_sources[element.name] = source
            filled.append(label)
        await self._observe(state)
        if not filled:
            return {"ok": False, "summary": "Every field already had that value; submit the form "
                                            "or change something else.", "progress": False}
        note = f" Already set: {', '.join(unchanged)}." if unchanged else ""
        return {"ok": True, "summary": f"Filled {', '.join(filled)}.{note}", "progress": True}

    async def _observe(self, state: RuntimeState):
        observation = await self.browser.snapshot()
        state.observations[observation.observation_id] = observation
        state.observations_text.append(observation.model_dump_json())
        return observation

    def _current_element(self, ref: str):
        observation = self.browser.current
        if observation is None:
            raise ValueError("Observe the page before using a ref")
        matches = [item for item in observation.elements if item.ref == ref]
        if len(matches) != 1:
            raise ValueError("Stale ref")
        return matches[0]

    def _question(self, state: RuntimeState, question: str, candidates: list[str]) -> dict:
        question_id = uuid4().hex
        self.store.save_question(question_id, state.run_id, question)
        self.store.update_run(state.run_id, status="awaiting_input")
        self._emit(state.run_id, "question", {"question_id": question_id, "text": question,
                                              "candidates": candidates})
        self._emit(state.run_id, "run_status", {"status": "awaiting_input",
                                                  "reason": question})
        return {"ok": True, "summary": question, "pause": True}

    async def _write_export(self, state: RuntimeState, args: dict) -> dict:
        name = args["name"] if args["name"].endswith(".csv") else args["name"] + ".csv"
        query = (state.contract.filter if state.contract and state.contract.filter is not None
                 else args.get("probe_query", {}))
        args = {**args, "name": name}
        intent = FileWriteIntent(mutation_id=uuid4().hex, run_id=state.run_id,
                                 path=f"exports/{name}", probe_query=query)
        decision = check_file_write(state, intent)
        self._emit(state.run_id, "gate", {"step": state.steps,
                                           **decision.model_dump(mode="json")})
        if not decision.allowed:
            return {"ok": False, "summary": decision.reason}
        rows = await self.probes.register_invoices(
            supplier_id=intent.probe_query.get("supplier_id"),
            due_before=intent.probe_query.get("due_before"),
        )
        self.workspace.write_csv(args["name"], rows)
        state.export_path = intent.path
        return {"ok": True, "summary": f"Wrote {len(rows)} export rows", "progress": True}

    async def _submit(self, state: RuntimeState, ref: str) -> dict:
        if state.phase != "execute" or state.contract is None:
            return {"ok": False, "summary": "Business writes require a locked goal"}
        form = await self.browser.capture_form(ref)
        fields = form["fields"]
        source = next((item for item in state.contract.sources
                       if item.key == fields.get("invoice_number") or
                       item.kind == "message" and item.supplier_id ==
                       urlsplit(form["action_url"]).path.rsplit("/", 1)[-1]), None)
        target_key = (
            {"supplier_id": source.supplier_id} if source and source.kind == "message" else
            {"supplier_id": fields.get("supplier_id", source.supplier_id),
             "invoice_number": fields.get("invoice_number", source.key)} if source else None
        )
        field_sources = {}
        for mapping in state.contract.field_map:
            for fact in state.facts.values():
                if (fact.doc_id == (source.doc_id if source else None)
                        and fact.field_locator == mapping.source_label
                        and fact.normalized == fields.get(mapping.target_field)):
                    field_sources[mapping.target_field] = FillSource(kind="fact", fact_key=fact.key)
                    break
        intent = MutationIntent(
            mutation_id=uuid4().hex, run_id=state.run_id,
            origin=f"{urlsplit(form['action_url']).scheme}://{urlsplit(form['action_url']).netloc}",
            action_url=form["action_url"], fields=fields, secret_fields=form["secret_fields"],
            filled_from=field_sources, form_token=fields.get("form_token"),
            target_key=target_key, target_version=int(fields["version"]) if "version" in fields else None,
            source=source,
        )
        decision = check_mutation(state, intent)
        self._emit(state.run_id, "gate", {
            "step": state.steps, **decision.model_dump(mode="json"),
            "mutation": {"action_url": intent.action_url, "fields": intent.fields,
                         "target_label": ", ".join(target_key.values()) if target_key else ""},
        })
        if not decision.allowed:
            if decision.code == "needs_approval":
                approval = create_approval(intent, decision.reason, int(state.policy["version"]))
                state.approvals.append(approval)
                payload = approval.model_dump(mode="json")
                self.store.save_approval(approval.approval_id, state.run_id, payload)
                self.store.update_run(state.run_id, status="awaiting_approval")
                self._emit(state.run_id, "approval", payload)
                self._emit(state.run_id, "run_status", {"status": "awaiting_approval",
                                                      "reason": decision.reason})
                screenshot = await self._capture_artifact(state)
                return {"ok": False, "summary": decision.reason, "pause": True,
                        "screenshot": screenshot}
            return {"ok": False, "summary": decision.reason}
        before = await self.probes.target_by_key(target_key)
        before_values = ({key: str(before[key]) for key in fields
                          if key in before and key not in {"form_token", "version"}}
                         if before else None)
        pending = begin_pending(self.store, intent, before_values=before_values,
                                before_version=before.get("version") if before else None)
        state.pending.append(pending)
        self._emit(state.run_id, "pending", pending.model_dump(mode="json"))
        self.browser.guard.arm(NetworkAllowance(run_id=state.run_id,
                                                mutation_id=intent.mutation_id,
                                                method="POST", url=intent.action_url,
                                                body=intent.fields))
        try:
            await asyncio.wait_for(self.browser.click(ref), timeout=5)
        except (TimeoutError, PlaywrightError) as exc:
            self._emit(state.run_id, "error", {"code": "write_response_uncertain",
                                                 "message": type(exc).__name__,
                                                 "retryable": True})
        finally:
            self.browser.guard.disarm()
        settled = await reconcile(pending, self.probes)
        self.store.save_pending(settled.pending)
        state.pending[-1] = settled.pending
        artifact_name = await self._capture_artifact(state)
        self._emit(state.run_id, "pending", settled.pending.model_dump(mode="json"))
        if self.browser.last_navigation_status == 403:
            body = await self.browser.page.locator("body").inner_text()
            try:
                detail = json.loads(body).get("detail", "This account cannot change that supplier")
            except ValueError:
                detail = "This account cannot change that supplier"
            self._terminal(state, RunStatus.blocked, f"{detail} Nothing was saved.")
            return {"ok": False, "summary": detail, "terminal": True,
                    "screenshot": artifact_name}
        if settled.pending.state == "committed":
            state.wrote_business_data = True
            for index, approval in enumerate(state.approvals):
                if validate_approval(approval, intent, int(state.policy["version"])):
                    used = approval.model_copy(update={"status": ApprovalStatus.used})
                    state.approvals[index] = used
                    payload = used.model_dump(mode="json")
                    self.store.save_approval(used.approval_id, state.run_id, payload)
                    self._emit(state.run_id, "approval", payload)
            return {"ok": True, "summary": "Write reconciled as committed", "progress": True,
                    "screenshot": artifact_name}
        return {"ok": False, "summary": settled.pending.reason or "Write not committed",
                "screenshot": artifact_name}

    async def _capture_artifact(self, state: RuntimeState) -> str | None:
        name = f"step-{state.steps}.png"
        path = self.store.path.parent / "artifacts" / state.run_id / name
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            await self.browser.page.screenshot(path=str(path))
            return name
        except PlaywrightError:
            return None
