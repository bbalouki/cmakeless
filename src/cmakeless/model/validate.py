"""Freeze-time validation: every error that can be caught before CMake runs, is.

Each check raises ConfigurationError with what went wrong, where, and what to
try next.
"""

from __future__ import annotations

import re

from cmakeless.errors import ConfigurationError
from cmakeless.model.nodes import SUPPORTED_CPP_STANDARDS, ProjectModel

# CMake target and project names: conservative subset that never needs quoting.
_VALID_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.+-]*$")


def validate_project(model: ProjectModel) -> None:
    """Validate the whole frozen graph, raising ConfigurationError on the first defect."""
    _check_name(model.name, kind="project", script=model.source_script)
    _check_cpp_std(model)
    _check_target_names(model)
    _check_sources_exist(model)


def _check_cpp_std(model: ProjectModel) -> None:
    if model.cpp_std not in SUPPORTED_CPP_STANDARDS:
        supported = ", ".join(str(std) for std in sorted(SUPPORTED_CPP_STANDARDS))
        raise ConfigurationError(
            f"Unknown C++ standard {model.cpp_std!r} for project {model.name!r} "
            f"in {model.source_script}. Pick one of: {supported} "
            f"(for example cpp_std=20)."
        )


def _check_name(name: str, *, kind: str, script: str) -> None:
    if not _VALID_NAME.match(name):
        raise ConfigurationError(
            f"Invalid {kind} name {name!r} in {script}: names must start with a letter "
            f"or underscore and contain only letters, digits, '_', '.', '+', or '-'. "
            f"Rename the {kind} to something like {_suggest_name(name)!r}."
        )


def _check_target_names(model: ProjectModel) -> None:
    seen: set[str] = set()
    for target in model.executables:
        _check_name(target.name, kind="target", script=model.source_script)
        if target.name in seen:
            raise ConfigurationError(
                f"Duplicate target name {target.name!r} in {model.source_script}: "
                f"every target needs a unique name. Rename one of the "
                f"{target.name!r} targets."
            )
        seen.add(target.name)


def _check_sources_exist(model: ProjectModel) -> None:
    for target in model.executables:
        if not target.sources:
            raise ConfigurationError(
                f"Target {target.name!r} in {model.source_script} has no source files. "
                f"Add at least one file to its 'sources' argument."
            )
        for source in target.sources:
            resolved = model.root_dir / source
            if not resolved.is_file():
                raise ConfigurationError(
                    f"Source file '{source.as_posix()}' for target {target.name!r} "
                    f"does not exist (looked for {resolved}). Check the 'sources' "
                    f"argument in {model.source_script} for a typo, or create the file."
                )


def _suggest_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.+-]", "_", name) or "my_target"
    if not re.match(r"^[A-Za-z_]", cleaned):
        cleaned = f"_{cleaned}"
    return cleaned
