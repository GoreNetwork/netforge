"""Engine registry. To add an engine, write a class with `name` and `run`, then
list it here. See "Adding an engine" in the README."""
from netforge.worker.engines.ansible import AnsibleEngine
from netforge.worker.engines.base import Engine, EngineError, RunContext
from netforge.worker.engines.python import PythonEngine

ENGINES: dict[str, type[Engine]] = {
    AnsibleEngine.name: AnsibleEngine,
    PythonEngine.name: PythonEngine,
}


def load_engines(names: list[str]) -> dict[str, Engine]:
    unknown = set(names) - ENGINES.keys()
    if unknown:
        raise ValueError(f"Unknown engines in WORKER_ENGINES: {sorted(unknown)}")
    return {name: ENGINES[name]() for name in names}


__all__ = ["ENGINES", "Engine", "EngineError", "RunContext", "load_engines"]
