import sys
from typing import Any

from netforge.worker.engines.base import RunContext, read_output, run_process


class PythonEngine:
    name = "python"

    def run(self, context: RunContext) -> dict[str, Any]:
        run_process(context, [sys.executable, "-u", str(context.entrypoint)])
        return read_output(context)
