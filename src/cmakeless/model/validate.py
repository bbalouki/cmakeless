"""Freeze-time validation: every error that can be caught before CMake runs, is.

Each check raises ConfigurationError with what went wrong, where, and what to
try next.
"""

from __future__ import annotations

import re

from cmakeless.errors import ConfigurationError
from cmakeless.model.nodes import (
    SUPPORTED_CPP_STANDARDS,
    WARNING_PRESETS,
    LibraryKind,
    LibraryModel,
    ProjectModel,
    TargetModel,
)

# CMake target and project names: conservative subset that never needs quoting.
_VALID_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.+-]*$")


def validate_project(model: ProjectModel) -> None:
    """Validate the whole frozen graph, raising ConfigurationError on the first defect."""
    _check_name(model.name, kind="project", script=model.source_script)
    _check_cpp_std(model)
    _check_warnings(model)
    _check_target_names(model)
    _check_sources(model)
    _check_libraries(model)
    _check_links(model)
    _check_link_cycles(model)
    _check_subprojects(model)


def _check_name(name: str, *, kind: str, script: str) -> None:
    if not _VALID_NAME.match(name):
        raise ConfigurationError(
            f"Invalid {kind} name {name!r} in {script}: names must start with a letter "
            f"or underscore and contain only letters, digits, '_', '.', '+', or '-'. "
            f"Rename the {kind} to something like {_suggest_name(name)!r}."
        )


def _check_cpp_std(model: ProjectModel) -> None:
    if model.cpp_std not in SUPPORTED_CPP_STANDARDS:
        supported = ", ".join(str(std) for std in sorted(SUPPORTED_CPP_STANDARDS))
        raise ConfigurationError(
            f"Unknown C++ standard {model.cpp_std!r} for project {model.name!r} "
            f"in {model.source_script}. Pick one of: {supported} "
            f"(for example cpp_std=20)."
        )


def _check_warnings(model: ProjectModel) -> None:
    if model.warnings not in WARNING_PRESETS:
        presets = ", ".join(repr(preset) for preset in sorted(WARNING_PRESETS))
        raise ConfigurationError(
            f"Unknown warnings preset {model.warnings!r} for project {model.name!r} "
            f"in {model.source_script}. Pick one of: {presets}."
        )


def _check_target_names(model: ProjectModel) -> None:
    seen: set[str] = set()
    for target in model.targets():
        _check_name(target.name, kind="target", script=model.source_script)
        if target.name in seen:
            raise ConfigurationError(
                f"Duplicate target name {target.name!r} in {model.source_script}: "
                f"every target needs a unique name. Rename one of the "
                f"{target.name!r} targets."
            )
        seen.add(target.name)


def _check_sources(model: ProjectModel) -> None:
    for target in model.targets():
        if _is_header_only(target):
            continue
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


def _check_libraries(model: ProjectModel) -> None:
    for library in model.libraries:
        if library.kind is LibraryKind.HEADER_ONLY:
            if library.sources:
                raise ConfigurationError(
                    f"Header-only library {library.name!r} in {model.source_script} "
                    f"must not list source files, but got "
                    f"{', '.join(source.as_posix() for source in library.sources)}. "
                    f"Remove the 'sources' argument, or change kind to 'static'."
                )
            if not library.public_include_dirs:
                raise ConfigurationError(
                    f"Header-only library {library.name!r} in {model.source_script} "
                    f"needs a 'public_headers' directory so consumers can find its "
                    f"headers. Add public_headers='include/'."
                )
        for include_dir in library.public_include_dirs:
            resolved = model.root_dir / include_dir
            if not resolved.is_dir():
                raise ConfigurationError(
                    f"Public header directory '{include_dir.as_posix()}' for library "
                    f"{library.name!r} does not exist (looked for {resolved}). Check "
                    f"the 'public_headers' argument in {model.source_script}, or "
                    f"create the directory."
                )


def _check_links(model: ProjectModel) -> None:
    library_names = {library.name for library in model.libraries}
    for target in model.targets():
        for link in target.links:
            if link.target not in library_names:
                raise ConfigurationError(
                    f"Target {target.name!r} in {model.source_script} links against "
                    f"{link.target!r}, which is not a library of this project. "
                    f"Targets can only link libraries created by the same project's "
                    f"add_library(); subprojects are isolated by design."
                )


def _check_link_cycles(model: ProjectModel) -> None:
    edges_by_name: dict[str, tuple[str, ...]] = {
        library.name: tuple(link.target for link in library.links) for library in model.libraries
    }
    in_progress: set[str] = set()
    finished: set[str] = set()

    def visit(name: str, path: list[str]) -> None:
        if name in finished:
            return
        if name in in_progress:
            cycle_start = path.index(name)
            cycle = " -> ".join([*path[cycle_start:], name])
            raise ConfigurationError(
                f"Link cycle detected in {model.source_script}: {cycle}. Break the "
                f"cycle by removing one of these link() calls or by extracting the "
                f"shared code into a third library."
            )
        in_progress.add(name)
        for neighbor in edges_by_name.get(name, ()):
            visit(neighbor, [*path, name])
        in_progress.discard(name)
        finished.add(name)

    for library_name in sorted(edges_by_name):
        visit(library_name, [])


def _check_subprojects(model: ProjectModel) -> None:
    seen_dirs: set[str] = set()
    for subproject in model.subprojects:
        directory = subproject.directory
        if directory.is_absolute() or ".." in directory.parts:
            raise ConfigurationError(
                f"Subproject directory '{directory.as_posix()}' in "
                f"{model.source_script} must be a relative path inside the project "
                f"root. Move the subproject under the root, or make it its own "
                f"project."
            )
        key = directory.as_posix()
        if key in seen_dirs:
            raise ConfigurationError(
                f"Subproject directory '{key}' is added twice in "
                f"{model.source_script}. Remove the duplicate add_subproject() call."
            )
        seen_dirs.add(key)
        validate_project(subproject.project)


def _is_header_only(target: TargetModel) -> bool:
    return isinstance(target, LibraryModel) and target.kind is LibraryKind.HEADER_ONLY


def _suggest_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.+-]", "_", name) or "my_target"
    if not re.match(r"^[A-Za-z_]", cleaned):
        cleaned = f"_{cleaned}"
    return cleaned
