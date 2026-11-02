from typing import Any

import yaml

from netforge.worker.engines.base import RunContext, read_output, run_process


class _Unsafe(str):
    pass


yaml.SafeDumper.add_representer(
    _Unsafe, lambda dumper, value: dumper.represent_scalar("!unsafe", str(value))
)


def mark_unsafe(value: Any) -> Any:
    """Tag strings so Ansible never evaluates user input as a Jinja template."""
    if isinstance(value, str):
        return _Unsafe(value)
    if isinstance(value, dict):
        return {key: mark_unsafe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [mark_unsafe(item) for item in value]
    return value


class AnsibleEngine:
    name = "ansible"

    def run(self, context: RunContext) -> dict[str, Any]:
        extra_vars = context.work_dir / "extra_vars.yml"
        extra_vars.write_text(yaml.safe_dump(mark_unsafe(context.variables)), encoding="utf-8")
        run_process(
            context,
            ["ansible-playbook", str(context.entrypoint), "--extra-vars", f"@{extra_vars}"],
        )
        return read_output(context)
