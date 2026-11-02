import json
from dataclasses import replace
from typing import Any

from netforge.catalog import PIPELINE_ENGINE
from netforge.worker.engines.base import EngineError, RunContext


class PipelineEngine:
    """Runs a task's steps in order, each with its own engine.

    A step's result is merged into the variables of the steps after it, and the
    last step's result becomes the task's. The first failure stops the task.
    """

    name = PIPELINE_ENGINE

    def run(self, context: RunContext) -> dict[str, Any]:
        # Imported here because the registry imports this module.
        from netforge.worker.engines import ENGINES

        variables = context.variables
        result: dict[str, Any] = {}
        for number, step in enumerate(context.definition.steps, start=1):
            if step.engine not in ENGINES or step.engine == PIPELINE_ENGINE:
                raise EngineError(f"Step {number} has an unusable engine: {step.engine}")
            context.log(f"--- Step {number}: {step.engine} {step.entrypoint} ---")
            context.output_file.unlink(missing_ok=True)
            context.vars_file.write_text(json.dumps(variables), encoding="utf-8")
            result = ENGINES[step.engine]().run(
                replace(
                    context,
                    definition=replace(
                        context.definition, engine=step.engine, entrypoint=step.entrypoint
                    ),
                    variables=variables,
                )
            )
            variables = {**variables, **result}
        return result
