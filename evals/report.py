"""Generate an auditable numerator/denominator evaluation report."""

from __future__ import annotations

from decimal import Decimal

from worker.runtime.prompts import PROMPT_HASH


def render_report(results: list[dict], *, model: str, tier: str,
                  reference_date: str | None = None, seed: int | None = None,
                  excluded: list[str] | None = None) -> str:
    total = len(results)
    tasks = [row for row in results if row.get("kind", "task") in {"task", "understanding"}]
    controls = [row for row in results if row.get("kind") == "control"]
    fields = [row for row in tasks if row.get("saved_record_present",
                                             row.get("field_correct") is not None)]
    metrics = [
        ("Task success", sum(row["success"] for row in tasks), len(tasks)),
        ("Control pass", sum(row["success"] for row in controls), len(controls)),
        ("Field correctness", sum(row["field_correct"] is True for row in fields), len(fields)),
        ("False completions", sum(row["false_completion"] for row in results), total),
        ("Unauthorized writes", sum(row["unauthorized_writes"] > 0 for row in results), total),
        ("Unexpected writes", sum(row.get("unexpected_writes", 0) > 0 for row in results), total),
        ("Duplicate records", sum(row["duplicates"] > 0 for row in results), total),
    ]
    cost = sum((Decimal(str(row["cost_inr"])) for row in results), Decimal(0))
    lines = ["# Evaluation report", "", f"Tier: {tier}  ", f"Model: `{model}`  ",
             "Output cap: 512 tokens; tool choice: required; temperature: provider default  ",
             f"Prompt SHA-256: `{PROMPT_HASH}`  ",
             f"Reference date: {reference_date or 'unspecified'}; seed: {seed if seed is not None else 'unspecified'}",
             "",
             "| Metric | Result |", "| --- | ---: |"]
    lines += [f"| {label} | {numerator}/{denominator} |" for label, numerator, denominator in metrics]
    splits = sorted({row.get("split", "dev") for row in tasks})
    if len(splits) > 1 or splits[:1] not in ([], ["dev"]):
        lines += [f"| Task success, {split} | "
                  f"{sum(row['success'] for row in tasks if row.get('split', 'dev') == split)}/"
                  f"{sum(row.get('split', 'dev') == split for row in tasks)} |" for split in splits]
    failures: dict[str, int] = {}
    for row in tasks:
        if not row["success"] and row.get("failure"):
            key = row["failure"] if row.get("kind") != "understanding" else "misunderstood"
            failures[key] = failures.get(key, 0) + 1
    lines += [f"| Tool calls | {sum(row['tool_calls'] for row in results)}/{total} runs |",
              f"| Latency | {sum(row['latency_s'] for row in results):.2f} s/{total} runs |",
              f"| Settled cost | ₹{cost:.6f}/{total} scenarios |", "", "## Scenarios", "",
              "| ID | Split | Expected | Actual | Success | Why it missed | Field correct | Tools | Cost |",
              "| --- | --- | --- | --- | --- | --- | --- | ---: | ---: |"]
    lines += [
        f"| {row['id']} | {row.get('split', '-')} | {row.get('expected_status', '-')} | "
        f"{row.get('actual_status', '-')} | {'yes' if row['success'] else 'no'} | "
        f"{row.get('failure') or ''} | {row.get('field_correct')} | "
        f"{row['tool_calls']} | ₹{Decimal(str(row['cost_inr'])):.3f} |"
        for row in results
    ]
    if failures:
        lines.insert(lines.index("## Scenarios"), "")
        lines.insert(lines.index("## Scenarios"), "Misses by cause: " + ", ".join(
            f"{name} {count}" for name, count in sorted(failures.items(), key=lambda x: -x[1])))
        lines.insert(lines.index("## Scenarios"), "")
    failed = [row for row in results if not row["success"] and row.get("diagnostics")]
    if failed:
        lines += ["", "## Failed run diagnostics", ""]
        for row in failed:
            lines += [f"### {row['id']}", "", *[f"- {item}" for item in row["diagnostics"]], ""]
    if excluded:
        lines += ["", "## Script-only scenarios excluded from live tier", "",
                  ", ".join(f"`{name}`" for name in excluded), ""]
    return "\n".join(lines) + "\n"
