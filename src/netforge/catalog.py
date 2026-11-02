"""Task types live on disk as automations/tasks/<name>/task.yml.

The file declares the engine, what to run and the variables a user must supply.
The GUI form and the API validation both come from this one definition.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from netforge.config import get_settings

DEFAULT_TIMEOUT_SECONDS = 1800
VARIABLE_TYPES = {"string", "integer", "choice"}


class CatalogError(Exception):
    """A task.yml file is invalid."""


class ValidationFailed(Exception):
    def __init__(self, errors: dict[str, str]):
        super().__init__(str(errors))
        self.errors = errors


@dataclass(frozen=True)
class Variable:
    name: str
    label: str
    type: str = "string"
    required: bool = True
    default: Any = None
    help: str = ""
    pattern: str | None = None
    pattern_error: str | None = None
    min: int | None = None
    max: int | None = None
    choices: tuple[str, ...] = ()

    def clean(self, raw: Any) -> Any:
        """Return the typed value, or raise ValueError with a user-facing message."""
        if self.type == "integer":
            # bool is an int subclass, and "true" is not a number a user meant.
            if isinstance(raw, bool):
                raise ValueError("must be a whole number")
            try:
                value = int(raw)
            except (TypeError, ValueError):
                raise ValueError("must be a whole number") from None
            if self.min is not None and value < self.min:
                raise ValueError(f"must be at least {self.min}")
            if self.max is not None and value > self.max:
                raise ValueError(f"must be at most {self.max}")
            return value

        if not isinstance(raw, str):
            raise ValueError("must be text")
        if self.type == "choice" and raw not in self.choices:
            raise ValueError(f"must be one of: {', '.join(self.choices)}")
        if self.pattern and not re.fullmatch(self.pattern, raw):
            raise ValueError(self.pattern_error or f"must match {self.pattern}")
        return raw


@dataclass(frozen=True)
class TaskDefinition:
    name: str
    title: str
    description: str
    engine: str
    entrypoint: str
    directory: Path
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    variables: tuple[Variable, ...] = field(default_factory=tuple)

    def validate(self, submitted: dict[str, Any]) -> dict[str, Any]:
        """Return cleaned variables, or raise ValidationFailed listing every problem."""
        errors: dict[str, str] = {}
        cleaned: dict[str, Any] = {}
        known = {variable.name for variable in self.variables}
        for name in submitted.keys() - known:
            errors[name] = "unknown variable"

        for variable in self.variables:
            raw = submitted.get(variable.name)
            if raw is None or raw == "":
                if variable.default is not None:
                    raw = variable.default
                elif variable.required:
                    errors[variable.name] = "is required"
                    continue
                else:
                    continue
            try:
                cleaned[variable.name] = variable.clean(raw)
            except ValueError as exc:
                errors[variable.name] = str(exc)

        if errors:
            raise ValidationFailed(errors)
        return cleaned


def _load_definition(path: Path) -> TaskDefinition:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        variables = tuple(
            Variable(**{**item, "choices": tuple(item.get("choices", ()))})
            for item in raw.get("variables", [])
        )
        definition = TaskDefinition(
            name=path.parent.name,
            title=raw["title"],
            description=raw.get("description", ""),
            engine=raw["engine"],
            entrypoint=raw["entrypoint"],
            directory=path.parent,
            timeout_seconds=raw.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
            variables=variables,
        )
    except (KeyError, TypeError, AttributeError, yaml.YAMLError) as exc:
        raise CatalogError(f"{path}: {exc}") from exc

    for variable in variables:
        if variable.type not in VARIABLE_TYPES:
            raise CatalogError(f"{path}: {variable.name} has unknown type {variable.type}")
        if variable.pattern:
            try:
                re.compile(variable.pattern)
            except re.error as exc:
                raise CatalogError(f"{path}: {variable.name} has a bad pattern: {exc}") from exc
    return definition


def load_catalog(automations_dir: Path | None = None) -> dict[str, TaskDefinition]:
    """Read the catalog from disk, so a new task needs no restart."""
    root = automations_dir or get_settings().automations_dir
    definitions = (_load_definition(path) for path in sorted(root.glob("tasks/*/task.yml")))
    return {definition.name: definition for definition in definitions}
