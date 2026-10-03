import json

import pytest

from worker.runtime.prompts import build_messages
from worker.runtime.stall import StallDetector
from worker.tools.registry import TOOLS, validate_call
from worker.trace.writer import TraceWriter


def test_tool_registry_rejects_unknown_and_bad_args():
    assert {item["function"]["name"] for item in TOOLS} >= {
        "browser_snapshot", "browser_click", "commit_goal", "finish", "record_fact",
    }
    assert validate_call("browser_click", {"ref": "e1"}) == {"ref": "e1"}
    with pytest.raises(ValueError):
        validate_call("browser_click", {"ref": "e1", "script": "alert(1)"})
    with pytest.raises(ValueError):
        validate_call("shell", {"cmd": "ls"})


def test_stall_requires_verified_progress():
    detector = StallDetector()
    assert detector.observe("browser_snapshot", {}, progress=False) is None
    assert detector.observe("browser_snapshot", {}, progress=False) is None
    assert detector.observe("browser_snapshot", {}, progress=False) == "reflect"
    detector.observe("browser_snapshot", {}, progress=True)
    assert detector.observe("browser_snapshot", {}, progress=False) is None


def test_prompt_marks_pages_untrusted_and_keeps_last_three():
    observations = [f"Page {index}" for index in range(5)]
    messages = build_messages("Register latest invoice", phase="discover", contract=None,
                              observations=observations, facts=[], plan=[])
    rendered = json.dumps(messages)
    assert "<untrusted_page>Page 4</untrusted_page>" in rendered
    assert "<untrusted_page>Page 2</untrusted_page>" in rendered
    assert "<untrusted_page>Page 0</untrusted_page>" not in rendered


def test_trace_is_append_only_and_redacts_secrets(tmp_path):
    writer = TraceWriter(tmp_path, "r1", model="fake", base_url="local",
                         parameters={"max_tokens": 256}, prompt_hash="abc")
    writer.append("tool", {"name": "browser_click", "form_token": "secret"})
    lines = (tmp_path / "r1.jsonl").read_text().splitlines()
    assert len(lines) == 2
    assert "secret" not in "\n".join(lines)
    assert json.loads(lines[0])["model"] == "fake"
