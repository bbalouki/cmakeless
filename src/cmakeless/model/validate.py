"""Freeze-time validation: every error that can be caught before CMake runs, is.

Each check raises ConfigurationError with what went wrong, where, and what to
try next.
"""

from __future__ import annotations

import re
from pathlib import Path

from cmakeless.errors import ConfigurationError
from cmakeless.model.nodes import (
    BUILD_TYPE_BY_OPTIMIZE,
    CPACK_GENERATOR_BY_FORMAT,
    PACKAGE_MANAGERS,
    SANITIZERS,
    SUPPORTED_CPP_STANDARDS,
    TEST_FRAMEWORKS,
    WARNING_PRESETS,
    DependencyModel,
    LibraryKind,
    LibraryModel,
    ProjectModel,
    TargetModel,
    TestModel,
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
    _check_package_manager(model)
    _check_target_names(model)
    _check_sources(model)
    _check_libraries(model)
    _check_tests(model)
    _check_sanitizers(model)
    _check_dependencies(model)
    _check_links(model)
    _check_link_cycles(model)
    _check_toolchains(model)
    _check_presets(model)
    _check_installs(model)
    _check_package_formats(model)
    _check_subprojects(model)
    _check_dependency_versions(model)


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


def _check_package_manager(model: ProjectModel) -> None:
    """Reject package manager names no dependency provider implements.

    Args:
        model: The frozen project to check.

    Raises:
        ConfigurationError: If ``model.package_manager`` is unknown.
    """
    if model.package_manager not in PACKAGE_MANAGERS:
        managers = ", ".join(repr(manager) for manager in sorted(PACKAGE_MANAGERS))
        raise ConfigurationError(
            f"Unknown package manager {model.package_manager!r} for project "
            f"{model.name!r} in {model.source_script}. Pick one of: {managers} "
            f'(for example project.package_manager = "vcpkg").'
        )


def _check_dependencies(model: ProjectModel) -> None:
    """Check every dependency's shape: valid name, version, and targets.

    Args:
        model: The frozen project to check.

    Raises:
        ConfigurationError: When a dependency has an unusable name, an
            empty version, or no imported targets to link.
    """
    for dependency in model.dependencies:
        if not _VALID_NAME.match(dependency.name):
            raise ConfigurationError(
                f"Invalid package name {dependency.name!r} in "
                f'{model.source_script}: specs look like "name/version", for '
                f'example depends("fmt/10.2.1").'
            )
        if not dependency.version:
            raise ConfigurationError(
                f"Package {dependency.name!r} in {model.source_script} has no "
                f'version. Specs look like "name/version", for example '
                f'depends("{dependency.name}/1.0.0").'
            )
        if not dependency.link_targets:
            raise ConfigurationError(
                f"Package {dependency.name!r} in {model.source_script} has no "
                f"imported targets to link. Pass targets=[...] to depends(), for "
                f'example targets=["{dependency.name}::{dependency.name}"].'
            )


def _check_dependency_versions(model: ProjectModel) -> None:
    """Require one version per package across the whole project tree.

    One tree resolves into one lockfile, so two projects requiring
    different versions of the same package can never both be satisfied.

    Args:
        model: The frozen root project to check.

    Raises:
        ConfigurationError: When two projects in the tree require different
            versions of the same package.
    """
    seen: dict[str, tuple[str, str]] = {}
    for script, dependency in _tree_dependencies(model):
        known = seen.setdefault(dependency.name, (dependency.version, script))
        if known[0] != dependency.version:
            raise ConfigurationError(
                f"Conflicting versions of package {dependency.name!r}: "
                f"{known[1]} requires {known[0]} but {script} requires "
                f"{dependency.version}. Align both on one version; the tree "
                f"shares a single lockfile."
            )


def _tree_dependencies(model: ProjectModel) -> list[tuple[str, DependencyModel]]:
    """Flatten every dependency in the tree with its declaring script.

    Args:
        model: The root project.

    Returns:
        (source_script, dependency) pairs, parents before children.
    """
    pairs = [(model.source_script, dependency) for dependency in model.dependencies]
    for subproject in model.subprojects:
        pairs.extend(_tree_dependencies(subproject.project))
    return pairs


def _check_target_names(model: ProjectModel) -> None:
    """Require every target name to be valid and unique within the project.

    Args:
        model: The frozen project to check.

    Raises:
        ConfigurationError: On an invalid or duplicated target name.
    """
    seen: set[str] = set()
    for target in model.all_targets():
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
    for target in model.all_targets():
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
    """Require every link edge to point at a library or a known dependency.

    Args:
        model: The frozen project to check.

    Raises:
        ConfigurationError: When a target links something that is neither
            one of the project's own libraries (subprojects are isolated by
            design) nor an imported target of one of its dependencies.
    """
    library_names = {library.name for library in model.libraries}
    imported_names = {
        target for dependency in model.dependencies for target in dependency.link_targets
    }
    for target in model.all_targets():
        for link in target.links:
            if link.external and link.target not in imported_names:
                raise ConfigurationError(
                    f"Target {target.name!r} in {model.source_script} links imported "
                    f"target {link.target!r}, which no dependency of this project "
                    f"provides. Add the matching depends() call, or fix the name."
                )
            if not link.external and link.target not in library_names:
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


def _check_tests(model: ProjectModel) -> None:
    """Check test-specific rules: the framework must be a known one.

    Args:
        model: The frozen project to check.

    Raises:
        ConfigurationError: When a test names an unknown framework.
    """
    for test in model.tests:
        if test.framework not in TEST_FRAMEWORKS:
            frameworks = ", ".join(repr(name) for name in sorted(TEST_FRAMEWORKS))
            raise ConfigurationError(
                f"Unknown test framework {test.framework!r} for test {test.name!r} "
                f"in {model.source_script}. Pick one of: {frameworks}."
            )


def _check_sanitizers(model: ProjectModel) -> None:
    """Check every target's sanitizer list: known names, sane combinations.

    Args:
        model: The frozen project to check.

    Raises:
        ConfigurationError: When a sanitizer is unknown, requested on a
            header-only library, or combined with an incompatible one.
    """
    for target in model.all_targets():
        if not target.sanitize:
            continue
        if _is_header_only(target):
            raise ConfigurationError(
                f"Header-only library {target.name!r} in {model.source_script} "
                f"cannot be sanitized: it compiles nothing. Set sanitize on the "
                f"targets that consume it instead."
            )
        _check_sanitizer_names(target.sanitize, where=f"target {target.name!r}", model=model)


def _check_sanitizer_names(sanitize: tuple[str, ...], *, where: str, model: ProjectModel) -> None:
    """Reject unknown sanitizer names and impossible combinations.

    Args:
        sanitize: The sanitizer names to check.
        where: Location phrase for the message ("target 'app'", "preset
            'debug'").
        model: The owning project, for message context.

    Raises:
        ConfigurationError: When a name is unknown or 'address' and
            'thread' are combined (the runtimes exclude each other).
    """
    for name in sanitize:
        if name not in SANITIZERS:
            known = ", ".join(repr(sanitizer) for sanitizer in sorted(SANITIZERS))
            raise ConfigurationError(
                f"Unknown sanitizer {name!r} on {where} in {model.source_script}. "
                f"Pick from: {known}."
            )
    if "address" in sanitize and "thread" in sanitize:
        raise ConfigurationError(
            f"Sanitizers 'address' and 'thread' on {where} in "
            f"{model.source_script} cannot be combined: their runtimes are "
            f"mutually exclusive. Keep one and run the other in a separate "
            f"preset."
        )


def _check_toolchains(model: ProjectModel) -> None:
    """Check toolchain rules: valid unique names, existing files, a compiler.

    Args:
        model: The frozen project to check.

    Raises:
        ConfigurationError: On a duplicate name, a missing toolchain file,
            or a generated toolchain without a compiler.
    """
    seen: set[str] = set()
    for toolchain in model.toolchains:
        _check_name(toolchain.name, kind="toolchain", script=model.source_script)
        if toolchain.name in seen:
            raise ConfigurationError(
                f"Duplicate toolchain name {toolchain.name!r} in "
                f"{model.source_script}: every toolchain needs a unique name. "
                f"Rename or remove one of them."
            )
        seen.add(toolchain.name)
        _check_toolchain_shape(toolchain.name, toolchain.file, toolchain.compiler, model)


def _check_toolchain_shape(
    name: str, file: Path | None, compiler: str | None, model: ProjectModel
) -> None:
    """Check one toolchain's shape: a real file, or enough to generate one.

    Args:
        name: The toolchain's name, for messages.
        file: The wrapped toolchain file path, or None when generated.
        compiler: The generated toolchain's compiler, or None.
        model: The owning project, for message context.

    Raises:
        ConfigurationError: When the wrapped file is missing or a
            generated toolchain names no compiler.
    """
    if file is not None:
        resolved = file if file.is_absolute() else model.root_dir / file
        if not resolved.is_file():
            raise ConfigurationError(
                f"Toolchain {name!r} in {model.source_script} wraps "
                f"'{file.as_posix()}', which does not exist (looked for "
                f"{resolved}). Fix the path passed to Toolchain.from_file()."
            )
    elif not compiler:
        raise ConfigurationError(
            f"Toolchain {name!r} in {model.source_script} has neither a file "
            f"nor a compiler. Pass compiler=... to Toolchain(), or wrap an "
            f"existing file with Toolchain.from_file()."
        )


def _check_presets(model: ProjectModel) -> None:
    """Check preset rules: unique names, known levels, resolvable toolchains.

    Args:
        model: The frozen project to check.

    Raises:
        ConfigurationError: On a duplicate preset name, an unknown optimize
            level, a bad sanitizer list, or a dangling toolchain reference.
    """
    toolchain_names = {toolchain.name for toolchain in model.toolchains}
    seen: set[str] = set()
    for preset in model.presets:
        _check_name(preset.name, kind="preset", script=model.source_script)
        if preset.name in seen:
            raise ConfigurationError(
                f"Duplicate preset name {preset.name!r} in {model.source_script}: "
                f"every preset needs a unique name. Rename or remove one of them."
            )
        seen.add(preset.name)
        if preset.optimize not in BUILD_TYPE_BY_OPTIMIZE:
            levels = ", ".join(repr(level) for level in sorted(BUILD_TYPE_BY_OPTIMIZE))
            raise ConfigurationError(
                f"Unknown optimize level {preset.optimize!r} on preset "
                f"{preset.name!r} in {model.source_script}. Pick one of: {levels}."
            )
        _check_sanitizer_names(preset.sanitize, where=f"preset {preset.name!r}", model=model)
        if preset.toolchain is not None and preset.toolchain not in toolchain_names:
            raise ConfigurationError(
                f"Preset {preset.name!r} in {model.source_script} references "
                f"toolchain {preset.toolchain!r}, which is not registered. Add "
                f"the matching project.add_toolchain(...) call, or fix the name."
            )


def _check_installs(model: ProjectModel) -> None:
    """Check install rules: each names one of this project's targets, once.

    Args:
        model: The frozen project to check.

    Raises:
        ConfigurationError: When an install rule names an unknown target,
            a test target, or repeats a target.
    """
    installable = {target.name for target in model.targets()}
    test_names = {test.name for test in model.tests}
    seen: set[str] = set()
    for install in model.installs:
        if install.target in test_names:
            raise ConfigurationError(
                f"Cannot install test target {install.target!r} in "
                f"{model.source_script}: tests are development tools, not "
                f"shipped artifacts. Remove the install() call."
            )
        if install.target not in installable:
            raise ConfigurationError(
                f"Cannot install {install.target!r} in {model.source_script}: it "
                f"is not a target of this project. Install only targets created "
                f"by this project's add_executable() or add_library()."
            )
        if install.target in seen:
            raise ConfigurationError(
                f"Target {install.target!r} is installed twice in "
                f"{model.source_script}. Remove the duplicate install() call."
            )
        seen.add(install.target)


def _check_package_formats(model: ProjectModel) -> None:
    """Check packaging rules: known formats, and something to package.

    Args:
        model: The frozen project to check.

    Raises:
        ConfigurationError: On an unknown format, or when package() was
            called without any install() rules to fill the package.
    """
    for format_name in model.package_formats:
        if format_name not in CPACK_GENERATOR_BY_FORMAT:
            formats = ", ".join(repr(name) for name in sorted(CPACK_GENERATOR_BY_FORMAT))
            raise ConfigurationError(
                f"Unknown package format {format_name!r} in {model.source_script}. "
                f"Pick from: {formats}."
            )
    if model.package_formats and not model.installs:
        raise ConfigurationError(
            f"project.package() in {model.source_script} has nothing to package: "
            f"no install() rules exist, so the archive would be empty. Add "
            f"project.install(...) calls for the targets you want to ship."
        )


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
        # One tree resolves through one backend; a child on a different
        # package manager would emit CMake its dependencies were never
        # resolved for.
        if subproject.project.package_manager != model.package_manager:
            raise ConfigurationError(
                f"Subproject '{key}' uses package_manager "
                f"{subproject.project.package_manager!r} but its parent in "
                f"{model.source_script} uses {model.package_manager!r}. Set the "
                f"same package_manager in both build descriptions."
            )
        validate_project(subproject.project)


def _is_header_only(target: TargetModel | TestModel) -> bool:
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
