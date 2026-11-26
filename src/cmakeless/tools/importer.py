"""Convert an existing CMake project into a cmakelessfile.py.

The importer never parses CMake text. It configures the existing project
with real CMake, reads the File API codemodel (targets, sources, include
directories, definitions, flags, and the link graph), and writes the Python
that describes the same build. What it cannot express is marked
`# TODO(import)` so a human reviews exactly those lines.
"""

from __future__ import annotations

import keyword
import re
import runpy
import shutil
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from cmakeless._constants import BUILD_SCRIPT_NAME
from cmakeless.api import _context
from cmakeless.driver.cmake_driver import CMakeDriver
from cmakeless.driver.file_api import TargetDetail, read_target_details

IMPORT_BUILD_DIR = Path("build") / "cmakeless-import"

# CMake target types the importer maps onto a CMakeless factory call.
_LIBRARY_KIND_BY_TYPE: dict[str, str] = {
    "STATIC_LIBRARY": "static",
    "SHARED_LIBRARY": "shared",
    "MODULE_LIBRARY": "plugin",
    "OBJECT_LIBRARY": "object",
    "INTERFACE_LIBRARY": "header_only",
}
_EXECUTABLE = "EXECUTABLE"
_DEFAULT_CXX_STANDARD = 17
_IDENTIFIER_CLEANUP = re.compile(r"[^0-9A-Za-z_]")


@dataclass(frozen=True, slots=True)
class ImportResult:
    """What the importer produced.

    Attributes:
        script: The generated cmakelessfile.py text.
        targets: How many targets were converted.
        todos: How many constructs need a human's review.
    """

    script: str
    targets: int
    todos: int


def import_project(source_dir: Path) -> ImportResult:
    """Configure an existing CMake project and describe it as Python.

    Args:
        source_dir: The directory holding the existing CMakeLists.txt.

    Returns:
        The generated script and a summary.
    """
    build_dir = source_dir / IMPORT_BUILD_DIR
    CMakeDriver(source_dir=source_dir, build_dir=build_dir, use_cache=False).configure()
    (name, version), details = read_target_details(build_dir)
    own = _dependency_order([d for d in details if _belongs_to_project(d, source_dir)])
    lines = _script_header(name or source_dir.name, version or "0.1.0", own)
    todos = 0
    variables = {detail.name: _variable(detail.name) for detail in own}
    for detail in own:
        block, block_todos = _target_block(detail, source_dir, variables)
        lines.extend(("", *block))
        todos += block_todos
    lines.extend(("", "project.build()", ""))
    return ImportResult(script="\n".join(lines), targets=len(own), todos=todos)


def _dependency_order(targets: list[TargetDetail]) -> list[TargetDetail]:
    """Order targets so every library is declared before anything links it.

    Args:
        targets: The project's own targets, in any order.

    Returns:
        The targets, dependencies first, otherwise by name.
    """
    by_name = {target.name: target for target in targets}
    placed: dict[str, TargetDetail] = {}
    visiting: set[str] = set()

    def visit(name: str) -> None:
        """Place one target after its dependencies; a cycle is left as found."""
        if name in visiting or name in placed:
            return
        visiting.add(name)
        for dependency in sorted(by_name[name].dependencies):
            if dependency in by_name:
                visit(dependency)
        placed[name] = by_name[name]

    for name in sorted(by_name):
        visit(name)
    return list(placed.values())


def _belongs_to_project(detail: TargetDetail, source_dir: Path) -> bool:
    """Keep only the project's own buildable targets.

    Args:
        detail: One configured target.
        source_dir: The project root.

    Returns:
        False for generator-provided and utility targets, and for anything
        a FetchContent dependency defined (its sources live under _deps).
    """
    if detail.generated or (
        detail.type != _EXECUTABLE and detail.type not in _LIBRARY_KIND_BY_TYPE
    ):
        return False
    return not any("_deps" in source.parts for source in detail.sources)


def _script_header(name: str, version: str, targets: list[TargetDetail]) -> list[str]:
    """Write the import line and the Project() call.

    Args:
        name: The CMake project name.
        version: The CMake project version.
        targets: The project's own targets, for the C++ standard.

    Returns:
        The opening lines.
    """
    standards = [detail.cxx_standard for detail in targets if detail.cxx_standard is not None]
    standard = max(standards) if standards else _DEFAULT_CXX_STANDARD
    return [
        '"""Imported from CMakeLists.txt by cmakeless import; review every TODO(import)."""',
        "",
        "from cmakeless import Project",
        "",
        f"project = Project({name!r}, version={version!r}, cpp_std={standard})",
    ]


def _variable(name: str) -> str:
    """Turn a target name into a Python variable name.

    Args:
        name: The CMake target name.

    Returns:
        A valid, non-keyword identifier.
    """
    cleaned = _IDENTIFIER_CLEANUP.sub("_", name)
    if not cleaned or cleaned[0].isdigit() or keyword.iskeyword(cleaned):
        cleaned = f"target_{cleaned}"
    return cleaned


def _target_block(
    detail: TargetDetail, source_dir: Path, variables: dict[str, str]
) -> tuple[list[str], int]:
    """Describe one target: its factory call, then its settings and links.

    Args:
        detail: The configured target.
        source_dir: The project root.
        variables: Target name to Python variable, for link() calls.

    Returns:
        (lines, number of TODO markers written).
    """
    variable = variables[detail.name]
    sources = collapse_globs(_relative(detail.sources, source_dir), source_dir)
    public, private = _split_includes(detail.include_dirs, source_dir)
    lines = [_factory_call(detail, variable, sources, public)]
    lines.extend(f"{variable}.include_dirs({directory!r})" for directory in private)
    lines.extend(_define_lines(variable, detail.defines))
    todos = 0
    for flag in detail.compile_flags:
        lines.append(f"{variable}.compile_options({flag!r})  # TODO(import): review this flag")
        todos += 1
    for dependency in detail.dependencies:
        if dependency in variables and dependency != detail.name:
            lines.append(f"{variable}.link({variables[dependency]})")
    for library in detail.link_libraries:
        lines.append(
            f"# TODO(import): {detail.name} links {library!r}; use depends(), "
            f"System.library(), or Imported() for it."
        )
        todos += 1
    return (lines, todos)


def _factory_call(
    detail: TargetDetail, variable: str, sources: list[str], public: list[str]
) -> str:
    """Write the add_executable() or add_library() call for one target.

    Args:
        detail: The configured target.
        variable: The Python variable to assign.
        sources: Project-relative sources, globs already collapsed.
        public: Public header directories.

    Returns:
        The call line.
    """
    if detail.type == _EXECUTABLE:
        return f"{variable} = project.add_executable({detail.name!r}, sources={sources!r})"
    kind = _LIBRARY_KIND_BY_TYPE[detail.type]
    headers = f", public_headers={public!r}" if public else ""
    return (
        f"{variable} = project.add_library({detail.name!r}, sources={sources!r}"
        f"{headers}, kind={kind!r})"
    )


def _define_lines(variable: str, defines: Iterable[str]) -> list[str]:
    """Write one define() call per preprocessor definition.

    Args:
        variable: The target's Python variable.
        defines: NAME or NAME=VALUE strings.

    Returns:
        The call lines.
    """
    lines = []
    for define in defines:
        name, _, value = define.partition("=")
        value_argument = f", {value!r}" if value else ""
        lines.append(f"{variable}.define({name!r}{value_argument})")
    return lines


def _relative(paths: Iterable[Path], source_dir: Path) -> list[Path]:
    """Express source paths relative to the project root.

    Args:
        paths: Paths as the codemodel reported them.
        source_dir: The project root.

    Returns:
        Root-relative paths, sorted.
    """
    resolved = []
    for path in paths:
        absolute = path if path.is_absolute() else source_dir / path
        resolved.append(absolute.resolve().relative_to(source_dir.resolve()))
    return sorted(resolved)


def _split_includes(includes: Iterable[Path], source_dir: Path) -> tuple[list[str], list[str]]:
    """Guess which include directories consumers need, the conventional way.

    The codemodel lists a target's effective include path without saying
    which directories it exports, so an "include" directory is treated as
    public and everything else inside the project as private.

    Args:
        includes: The target's include directories.
        source_dir: The project root.

    Returns:
        (public header directories, private include directories).
    """
    public: list[str] = []
    private: list[str] = []
    for directory in includes:
        absolute = (directory if directory.is_absolute() else source_dir / directory).resolve()
        if not absolute.is_relative_to(source_dir.resolve()):
            continue
        relative = absolute.relative_to(source_dir.resolve()).as_posix()
        if relative.startswith("build"):
            continue
        (public if PurePosixPath(relative).name == "include" else private).append(relative)
    return (public, private)


def collapse_globs(sources: list[Path], source_dir: Path) -> list[str]:
    """Replace a directory's full list of same-suffix files with one glob.

    A glob is used only when it matches exactly the listed files and nothing
    else, so the imported description builds the same files.

    Args:
        sources: Root-relative sources.
        source_dir: The project root, to check what a glob would match.

    Returns:
        Source entries: plain paths and "dir/*.ext" globs, sorted.
    """
    by_group: dict[tuple[PurePosixPath, str], list[Path]] = defaultdict(list)
    for source in sources:
        by_group[(PurePosixPath(source.parent.as_posix()), source.suffix)].append(source)
    entries: list[str] = []
    for (directory, suffix), files in by_group.items():
        on_disk = sorted(
            path for path in (source_dir / directory).glob(f"*{suffix}") if path.is_file()
        )
        if len(files) > 1 and len(on_disk) == len(files) and suffix:
            entries.append(f"{directory.as_posix()}/*{suffix}".removeprefix("./"))
        else:
            entries.extend(file.as_posix() for file in files)
    return sorted(entries)


def check_import(source_dir: Path, script: str) -> list[str]:
    """Prove a conversion: configure both projects and compare their codemodels.

    The original project is copied (without its build tree) into a scratch
    directory, the generated description replaces its CMakeLists.txt there,
    and both configured codemodels are compared target by target.

    Args:
        source_dir: The original project.
        script: The generated cmakelessfile.py text.

    Returns:
        Human-readable differences; empty when the builds match.
    """
    scratch = source_dir / "build" / "cmakeless-import-check"
    if scratch.exists():
        shutil.rmtree(scratch)
    shutil.copytree(source_dir, scratch, ignore=shutil.ignore_patterns("build", ".git"))
    (scratch / BUILD_SCRIPT_NAME).write_text(script, encoding="utf-8", newline="\n")
    with _context.verb_override("configure"):
        runpy.run_path(str(scratch / BUILD_SCRIPT_NAME), run_name="__main__")
    _, original = read_target_details(source_dir / IMPORT_BUILD_DIR)
    _, converted = read_target_details(scratch / "build")
    return compare_targets(
        [d for d in original if _belongs_to_project(d, source_dir)],
        [d for d in converted if _belongs_to_project(d, scratch)],
    )


def compare_targets(original: list[TargetDetail], converted: list[TargetDetail]) -> list[str]:
    """List how two sets of targets differ in name, type, and sources.

    Args:
        original: The original project's targets.
        converted: The converted project's targets.

    Returns:
        One line per difference.
    """
    before = {detail.name: detail for detail in original}
    after = {detail.name: detail for detail in converted}
    differences = [f"missing target {name!r}" for name in sorted(set(before) - set(after))]
    differences.extend(f"extra target {name!r}" for name in sorted(set(after) - set(before)))
    for name in sorted(set(before) & set(after)):
        if before[name].type != after[name].type:
            differences.append(f"{name}: type {before[name].type} became {after[name].type}")
        old_sources = {source.as_posix() for source in before[name].sources}
        new_sources = {source.as_posix() for source in after[name].sources}
        if old_sources != new_sources:
            changed = sorted(old_sources ^ new_sources)
            differences.append(f"{name}: sources differ ({', '.join(changed)})")
    return differences
