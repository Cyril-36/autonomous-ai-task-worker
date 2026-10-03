# Contract changes

- 2026-10-04: removed `ToolCall` and `ToolResult` from `worker/contracts.py`. Neither was used by the backend or the console; tool calls travel as provider dicts and results as `RunEvent` step data.
