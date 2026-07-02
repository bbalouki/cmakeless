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
    """Validate the whole frozen graph, subprojects included.

    Args:
        model: The frozen project to check.

    Raises:
        ConfigurationError: On the first defect found, with a message naming
            the problem, its location, and what to try next.
    """
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
    """Reject names CMake could choke on or that would need quoting.

    Args:
        name: The project or target name to check.
        kind: What the name names ("project" or "target"), for the message.
        script: Display name of the build description, for the message.

    Raises:
        ConfigurationError: If the name is not a safe CMake identifier.
    """
    if not _VALID_NAME.match(name):
        raise ConfigurationError(
            f"Invalid {kind} name {name!r} in {script}: names must start with a letter "
            f"or underscore and contain only letters, digits, '_', '.', '+', or '-'. "
            f"Rename the {kind} to something like {_suggest_name(name)!r}."
        )


def _check_cpp_std(model: ProjectModel) -> None:
    """Reject C++ standards CMake's compile features do not know.

    Args:
        model: The frozen project to check.

    Raises:
        ConfigurationError: If ``model.cpp_std`` is not a known standard.
    """
    if model.cpp_std not in SUPPORTED_CPP_STANDARDS:
        supported = ", ".join(str(std) for std in sorted(SUPPORTED_CPP_STANDARDS))
        raise ConfigurationError(
            f"Unknown C++ standard {model.cpp_std!r} for project {model.name!r} "
            f"in {model.source_script}. Pick one of: {supported} "
            f"(for example cpp_std=20)."
        )


def _check_warnings(model: ProjectModel) -> None:
    """Reject warning preset names the emitter cannot translate.

    Args:
        model: The frozen project to check.

    Raises:
        ConfigurationError: If ``model.warnings`` is not a known preset.
    """
    if model.warnings not in WARNING_PRESETS:
        presets = ", ".join(repr(preset) for preset in sorted(WARNING_PRESETS))
        raise ConfigurationError(
            f"Unknown warnings preset {model.warnings!r} for project {model.name!r} "
            f"in {model.source_script}. Pick one of: {presets}."
        )


def _check_target_names(model: ProjectModel) -> None:
    """Require every target name to be valid and unique within the project.

    Args:
        model: The frozen project to check.

    Raises:
        ConfigurationError: On an invalid or duplicated target name.
    """
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
    """Require every compiled target to have sources that exist on disk.

    Args:
        model: The frozen project to check.

    Raises:
        ConfigurationError: When a target has no sources or names a file
            that does not exist under the project root.
    """
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
    """Check library-specific rules: header-only shape and include dirs.

    Args:
        model: The frozen project to check.

    Raises:
        ConfigurationError: When a header-only library lists sources or has
            no public headers, or when a public header directory is missing.
    """
    for library in model.libraries:
        if library.kind is LibraryKind.HEADER_ONLY:
            _check_header_only_shape(library, model)
        for include_dir in library.public_include_dirs:
            resolved = model.root_dir / include_dir
            if not resolved.is_dir():
                raise ConfigurationError(
                    f"Public header directory '{include_dir.as_posix()}' for library "
                    f"{library.name!r} does not exist (looked for {resolved}). Check "
                    f"the 'public_headers' argument in {model.source_script}, or "
                    f"create the directory."
                )


def _check_header_only_shape(library: LibraryModel, model: ProjectModel) -> None:
    """Require header-only libraries to ship headers and nothing compiled.

    Args:
        library: The header-only library to check.
        model: The owning project, for message context.

    Raises:
        ConfigurationError: When the library lists sources or lacks a
            public header directory.
    """
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


def _check_links(model: ProjectModel) -> None:
    """Require every link edge to point at a library of this project.

    Args:
        model: The frozen project to check.

    Raises:
        ConfigurationError: When a target links something that is not one of
            the project's own libraries (subprojects are isolated by design).
    """
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
    """Reject circular library link graphs, naming the cycle.

    Args:
        model: The frozen project to check.

    Raises:
        ConfigurationError: When the libraries link each other in a cycle.
    """
    edges_by_name: dict[str, tuple[str, ...]] = {
        library.name: tuple(link.target for link in library.links) for library in model.libraries
    }
    finished: set[str] = set()
    for library_name in sorted(edges_by_name):
        cycle = _find_cycle(library_name, edges_by_name, (), finished)
        if cycle is not None:
            raise ConfigurationError(
                f"Link cycle detected in {model.source_script}: {' -> '.join(cycle)}. "
                f"Break the cycle by removing one of these link() calls or by "
                f"extracting the shared code into a third library."
            )


def _find_cycle(
    name: str,
    edges_by_name: dict[str, tuple[str, ...]],
    path: tuple[str, ...],
    finished: set[str],
) -> tuple[str, ...] | None:
    """Depth-first search for a link cycle reachable from one library.

    Args:
        name: The library to start (or continue) the search from.
        edges_by_name: Outgoing link edges for every library.
        path: Libraries on the current DFS path, root first.
        finished: Libraries already proven cycle-free; updated in place.

    Returns:
        The cycle as a name sequence ending where it started, or None.
    """
    if name in finished:
        return None
    if name in path:
        return (*path[path.index(name) :], name)
    for neighbor in edges_by_name.get(name, ()):
        cycle = _find_cycle(neighbor, edges_by_name, (*path, name), finished)
        if cycle is not None:
            return cycle
    finished.add(name)
    return None


def _check_subprojects(model: ProjectModel) -> None:
    """Check subproject mounting rules, then validate each child recursively.

    Args:
        model: The frozen project to check.

    Raises:
        ConfigurationError: When a subproject directory escapes the root or
            is mounted twice, or when a child project is itself invalid.
    """
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
    """Tell whether a target is a header-only library.

    Args:
        target: Any target of the project.

    Returns:
        True when the target is a library of kind HEADER_ONLY.
    """
    return isinstance(target, LibraryModel) and target.kind is LibraryKind.HEADER_ONLY


def _suggest_name(name: str) -> str:
    """Derive a valid CMake-safe name from an invalid one, for error messages.

    Args:
        name: The rejected name.

    Returns:
        A cleaned-up name that would pass validation.
    """
    cleaned = re.sub(r"[^A-Za-z0-9_.+-]", "_", name) or "my_target"
    if not re.match(r"^[A-Za-z_]", cleaned):
        cleaned = f"_{cleaned}"
    return cleaned
