import json
import uuid
from pathlib import Path

import pytest
import yaml

from netforge.catalog import TaskDefinition
from netforge.worker.engines import ENGINES, EngineError, RunContext, load_engines
from netforge.worker.engines.ansible import AnsibleEngine, mark_unsafe
from netforge.worker.engines.python import PythonEngine


def make_context(tmp_path: Path, engine: str, filename: str, body: str, variables=None, timeout=30):
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    (task_dir / filename).write_text(body)
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    variables = variables or {}
    (work_dir / "vars.json").write_text(json.dumps(variables))
    lines: list[str] = []
    context = RunContext(
        task_id=uuid.uuid4(),
        definition=TaskDefinition(
            name="t",
            title="t",
            description="",
            engine=engine,
            entrypoint=filename,
            directory=task_dir,
            timeout_seconds=timeout,
        ),
        variables=variables,
        work_dir=work_dir,
        log=lines.append,
    )
    return context, lines


def test_registry_rejects_unknown_engine():
    assert set(load_engines(list(ENGINES))) == set(ENGINES)
    with pytest.raises(ValueError):
        load_engines(["nope"])


def test_python_engine_contract(tmp_path):
    script = """
import json, os
variables = json.load(open(os.environ["NETFORGE_VARS_FILE"]))
print("hello", variables["who"])
json.dump({"greeted": variables["who"]}, open(os.environ["NETFORGE_OUTPUT_FILE"], "w"))
"""
    context, lines = make_context(tmp_path, "python", "run.py", script, {"who": "sw1"})
    assert PythonEngine().run(context) == {"greeted": "sw1"}
    assert lines == ["hello sw1"]


def test_nonzero_exit_fails_the_task(tmp_path):
    context, lines = make_context(tmp_path, "python", "run.py", "print('boom'); raise SystemExit(3)")
    with pytest.raises(EngineError, match="code 3"):
        PythonEngine().run(context)
    assert lines == ["boom"]


def test_timeout_kills_the_task(tmp_path):
    context, _ = make_context(tmp_path, "python", "run.py", "import time; time.sleep(30)", timeout=1)
    with pytest.raises(EngineError, match="Timed out"):
        PythonEngine().run(context)


def test_child_does_not_receive_worker_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://secret")
    monkeypatch.setenv("REDIS_URL", "redis://secret")
    context, lines = make_context(
        tmp_path, "python", "run.py", "import os; print('DATABASE_URL' in os.environ, 'REDIS_URL' in os.environ)"
    )
    PythonEngine().run(context)
    assert lines == ["False False"]


def test_entrypoint_cannot_escape_task_directory(tmp_path):
    context, _ = make_context(tmp_path, "python", "run.py", "")
    escaped = RunContext(
        task_id=context.task_id,
        definition=TaskDefinition(
            name="t", title="t", description="", engine="python", entrypoint="../outside.py",
            directory=context.definition.directory,
        ),
        variables={},
        work_dir=context.work_dir,
        log=lambda line: None,
    )
    (tmp_path / "outside.py").write_text("")
    with pytest.raises(EngineError, match="escapes"):
        PythonEngine().run(escaped)


def test_bad_output_file_fails_the_task(tmp_path):
    script = "import os; open(os.environ['NETFORGE_OUTPUT_FILE'], 'w').write('[1, 2]')"
    context, _ = make_context(tmp_path, "python", "run.py", script)
    with pytest.raises(EngineError, match="JSON object"):
        PythonEngine().run(context)


def test_unsafe_tags_cover_nested_strings():
    dumped = yaml.safe_dump(mark_unsafe({"a": "{{ x }}", "b": ["{{ y }}", 1], "c": {"d": "{{ z }}"}}))
    assert dumped.count("!unsafe") == 3


def test_ansible_never_renders_user_input(tmp_path):
    playbook = """
- hosts: localhost
  connection: local
  gather_facts: false
  tasks:
    - ansible.builtin.copy:
        dest: "{{ lookup('ansible.builtin.env', 'NETFORGE_OUTPUT_FILE') }}"
        content: "{{ {'value': payload} | to_json }}"
"""
    payload = "{{ lookup('ansible.builtin.env', 'HOME') }}"
    context, _ = make_context(tmp_path, "ansible", "playbook.yml", playbook, {"payload": payload})
    assert AnsibleEngine().run(context) == {"value": payload}
