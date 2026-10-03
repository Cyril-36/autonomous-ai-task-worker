"""The plan of a locked goal, built by code from the goal and the company procedure.

The model may sketch its own plan while it is still working out the goal. Once the goal is
locked, the plan follows the goal's sources and the procedure in config/apps.yaml, and each
step is marked done from evidence (recorded facts, confirmed writes, the export, the
verification), never from the model saying so.
"""

from __future__ import annotations


def _target(source) -> dict[str, str]:
    target = {"supplier_id": source.supplier_id}
    if source.kind == "invoice":
        target["invoice_number"] = source.key
    return target


def goal_plan(contract, apps, state, *, verified: bool = False) -> list[dict]:
    procedure = apps.procedure(contract.goal_type.value) if apps else {}
    read, write = procedure.get("read", "the source page"), procedure.get("write", "")
    write_page = write + (f"(id={contract.supplier_id})"
                          if procedure.get("write_id") == "supplier" else "")
    labels = {item.source_label for item in contract.field_map}
    committed = [item.target_key for item in state.pending if item.state == "committed"]
    steps: list[tuple[str, bool]] = []
    if write == "workspace.exports":
        steps.append(("Write the export file using the locked filter", bool(state.export_path)))
    elif any(item.kind == "no_write" for item in contract.obligations):
        keys = ", ".join(source.key for source in contract.sources)
        steps.append((f"Confirm {keys} is already recorded and change nothing", verified))
    else:
        for source in contract.sources:
            seen = {fact.field_locator for fact in state.facts.values()
                    if fact.doc_id == source.doc_id}
            steps.append((f"Read {source.key} at {read}", labels <= seen))
            steps.append((f"Enter {source.key} in {write_page}", _target(source) in committed))
    steps.append(("Check the result by reading it back", verified))
    first_open = next((index for index, (_, done) in enumerate(steps) if not done), None)
    return [{"text": text, "status": "done" if done else
             "doing" if index == first_open else "todo"}
            for index, (text, done) in enumerate(steps)]
