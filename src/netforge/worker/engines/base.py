"""The contract between Netforge and whatever does the work.

Every engine gets a private work directory and runs a child process with:
  NETFORGE_TASK_ID      the task's id
  NETFORGE_VARS_FILE    the validated variables, as JSON
  NETFORGE_OUTPUT_FILE  where the child may write a JSON object as its result

Stdout and stderr become the task log. Exit code 0 means success.
"""
import json
import os
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from netforge.catalog import TaskDefinition

# The worker's own database and queue credentials are never passed to a child.
_CHILD_ENV_PREFIXES = ("ANSIBLE_", "NAUTOBOT_", "PYTHON", "TF_")
_CHILD_ENV_NAMES = {"PATH", "HOME", "LANG", "LC_ALL"}


class EngineError(Exception):
    """The task failed. The message is shown to the user."""


@dataclass(frozen=True)
class RunContext:
    task_id: UUID
    definition: TaskDefinition
    variables: dict[str, Any]
    work_dir: Path
    log: Callable[[str], None]

    @property
    def vars_file(self) -> Path:
        return self.work_dir / "vars.json"

    @property
    def output_file(self) -> Path:
        return self.work_dir / "output.json"

    @property
    def entrypoint(self) -> Path:
        path = (self.definition.directory / self.definition.entrypoint).resolve()
        if not path.is_relative_to(self.definition.directory.resolve()):
            raise EngineError(f"Entrypoint escapes its task directory: {self.definition.entrypoint}")
        if not path.is_file():
            raise EngineError(f"Entrypoint not found: {self.definition.entrypoint}")
        return path


class Engine(Protocol):
    name: str

    def run(self, context: RunContext) -> dict[str, Any]:
        """Do the work and return the task's result. Raise EngineError on failure."""
        ...


def child_env(context: RunContext) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key in _CHILD_ENV_NAMES or key.startswith(_CHILD_ENV_PREFIXES)
    }
    env.update(
        NETFORGE_TASK_ID=str(context.task_id),
        NETFORGE_VARS_FILE=str(context.vars_file),
        NETFORGE_OUTPUT_FILE=str(context.output_file),
    )
    return env


def run_process(context: RunContext, command: list[str]) -> None:
    """Run a command to completion, streaming its output into the task log."""
    process = subprocess.Popen(
        command,
        cwd=context.definition.directory,
        env=child_env(context),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        start_new_session=True,
    )
    timed_out = threading.Event()

    def on_timeout() -> None:
        timed_out.set()
        process.kill()

    timer = threading.Timer(context.definition.timeout_seconds, on_timeout)
    timer.start()
    try:
        assert process.stdout is not None
        for line in process.stdout:
            context.log(line.rstrip("\n"))
        returncode = process.wait()
    finally:
        timer.cancel()
        if process.poll() is None:
            process.kill()

    if timed_out.is_set():
        raise EngineError(f"Timed out after {context.definition.timeout_seconds} seconds")
    if returncode != 0:
        raise EngineError(f"{context.definition.engine} exited with code {returncode}")


def read_output(context: RunContext) -> dict[str, Any]:
    """Return the object the child wrote, or {} if it wrote nothing."""
    if not context.output_file.exists():
        return {}
    try:
        output = json.loads(context.output_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EngineError(f"Output file is not valid JSON: {exc}") from exc
    if not isinstance(output, dict):
        raise EngineError("Output file must contain a JSON object")
    return output
