import pytest

from bot_v.llm.client import ERROR_PREFIX, LLMError
from bot_v.llm.parsing import extract_json
from bot_v.project.writer import ProjectWriter
from bot_v.skills.auto_tool_generator import AutoToolGenerator


def test_extract_json_variants():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('Sure!\n```json\n{"a": [1, 2]}\n```\nDone') == {"a": [1, 2]}
    assert extract_json('Here: [1, 2] ok') == [1, 2]
    with pytest.raises(ValueError):
        extract_json("no json here")
    with pytest.raises(LLMError):
        extract_json(f"{ERROR_PREFIX} down")


def test_writer_writes_nested_project(tmp_path):
    out = tmp_path / "out"
    ProjectWriter().write_project({"src": {"a.py": "x = 1", "utils": {"b.py": ""}}}, str(out))
    assert (out / "src" / "a.py").read_text() == "x = 1"
    assert (out / "src" / "utils" / "b.py").exists()


@pytest.mark.parametrize("bad", ["../evil.py", "/tmp/evil.py", "a/../../evil.py"])
def test_writer_refuses_paths_outside_output(tmp_path, bad):
    with pytest.raises(ValueError):
        ProjectWriter().write(str(tmp_path / "out"), [{"path": bad, "content": "x"}])


def test_tool_generator_rejects_non_identifiers():
    with pytest.raises(ValueError):
        AutoToolGenerator().create_tool_file("../../evil", [])
    with pytest.raises(ValueError):
        AutoToolGenerator().create_tool_file("ok", ["a); import os; (b"])
