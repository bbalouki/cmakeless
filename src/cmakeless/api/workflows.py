"""Verbs that orchestrate the pipeline beyond configure, build, and test.

Each workflow drives the same Project pipeline the core verbs use, so a
description that builds also explains, diffs, audits, and verifies without
any extra configuration.
"""

from __future__ import annotations

import difflib
import json
import sys
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from cmakeless._version import __version__
from cmakeless.api import _context
from cmakeless.api._evidence import verify_reproducible, write_evidence
from cmakeless.api._quality import run_coverage, run_fuzz, run_lint_report, run_pgo, run_profile
from cmakeless.api._runs import build_options, test_options
from cmakeless.deps.lockfile import LockedPackage, read_lockfile, write_lockfile
from cmakeless.deps.registry import registry_entry
from cmakeless.driver.cmake_driver import run_program
from cmakeless.driver.file_api import TargetInfo
from cmakeless.emitter.cmake_emitter import emit_target_section, emit_tree
from cmakeless.errors import CMakeError, ConfigurationError
from cmakeless.model.nodes import CompiledModel, LinkModel, ProjectModel

if TYPE_CHECKING:
    from cmakeless.api.project import Project


def run_workflow(project: Project, verb: str) -> None:
    """Dispatch one workflow verb.

    Args:
        project: The project being built.
        verb: A WORKFLOW_VERBS member.
    """
    _WORKFLOWS[verb](project)


def _run(project: Project) -> None:
    """Build one executable and run it with the arguments after '--'.

    Args:
        project: The project being built.

    Raises:
        ConfigurationError: When no target was named or it is not runnable.
    """
    options = _context.active_run_options()
    if options.target is None:
        raise ConfigurationError("'cmakeless run' needs a target: cmakeless run <target> -- args")
    prepared = project._prepare()
    project._configure(prepared.driver)
    prepared.driver.build(build_options())
    artifact = _artifact_of(project, prepared.driver.targets_info(), options.target)
    exit_code = run_program(artifact, options.program_args)
    if exit_code != 0:
        sys.exit(exit_code)


def _artifact_of(project: Project, infos: tuple[TargetInfo, ...], name: str) -> Path:
    """Find the built file of one target in the configured build.

    Args:
        project: The project, for its root.
        infos: The TargetInfo tuple from the File API.
        name: The target name.

    Returns:
        The absolute path of the target's first artifact.

    Raises:
        ConfigurationError: When the target has no runnable artifact.
    """
    for info in infos:
        if info.name == name and info.artifacts:
            artifact = info.artifacts[0]
            return artifact if artifact.is_absolute() else project._build_dir() / artifact
    raise ConfigurationError(
        f"Target {name!r} has no runnable artifact in this build. Run "
        f"'cmakeless explain {name}' to see what it is."
    )


def _explain(project: Project) -> None:
    """Show where a target was declared and exactly what CMake it produced.

    Args:
        project: The project being described.

    Raises:
        ConfigurationError: When the subject names no target or line.
    """
    subject = _context.active_run_options().subject
    model = project.freeze()
    target = _find_subject(model, subject)
    line = target.properties.declared_line
    origin = f"{model.source_script}:{line}" if line is not None else model.source_script
    section = emit_target_section(model, target.name, tool_version=__version__)
    print(f"{origin}   target {target.name!r}")
    for reason in _link_reasons(target):
        print(f"  why: {reason}")
    print(section)


def _find_subject(model: ProjectModel, subject: str | None) -> CompiledModel:
    """Resolve an explain subject: a target name or a "file:line" location.

    Args:
        model: The frozen project.
        subject: The user's argument.

    Returns:
        The matching target.

    Raises:
        ConfigurationError: When nothing matches.
    """
    targets = model.all_targets()
    if subject is not None and ":" in subject and subject.rsplit(":", 1)[1].isdigit():
        line = int(subject.rsplit(":", 1)[1])
        before = [t for t in targets if (t.properties.declared_line or line + 1) <= line]
        if before:
            return max(before, key=lambda t: t.properties.declared_line or 0)
    for target in targets:
        if target.name == subject:
            return target
    names = ", ".join(sorted(target.name for target in targets)) or "none"
    raise ConfigurationError(
        f"'cmakeless explain {subject}' matched no target. Pass a target name ({names}) "
        f"or a {model.source_script}:LINE location."
    )


def _link_reasons(target: CompiledModel) -> list[str]:
    """Explain the visibility CMakeless chose for each link edge.

    Args:
        target: The target whose links to explain.

    Returns:
        One sentence per link edge.
    """
    return [_link_reason(target, link) for link in target.links]


def _link_reason(target: CompiledModel, link: LinkModel) -> str:
    """Explain one link edge's visibility.

    Args:
        target: The linking target.
        link: The edge.

    Returns:
        A sentence naming the edge and why it has that visibility.
    """
    if link.public:
        return f"{link.target} is PUBLIC: {target.name}'s own headers expose it."
    kind = type(target).__name__.removesuffix("Model").lower()
    return f"{link.target} is PRIVATE: an implementation detail of this {kind}."


def _diff(project: Project) -> None:
    """Show how the committed build files differ from what would be generated.

    Args:
        project: The project being described.
    """
    options = _context.active_run_options()
    model = project._resolved_model()
    changed = 0
    for relative, text in emit_tree(model, tool_version=__version__).items():
        on_disk = project.root / relative
        current = on_disk.read_text(encoding="utf-8") if on_disk.is_file() else ""
        if current != text:
            changed += 1
            diff = difflib.unified_diff(
                current.splitlines(keepends=True),
                text.splitlines(keepends=True),
                fromfile=f"{relative.as_posix()} (on disk)",
                tofile=f"{relative.as_posix()} (would be generated)",
            )
            sys.stdout.writelines(diff)
    print(f"[cmakeless] {changed} generated file(s) differ from disk.")
    if changed and options.exit_code:
        sys.exit(1)


def _audit(project: Project) -> None:
    """Report how every locked pin was obtained, and approve reviewed ones.

    Args:
        project: The project being audited.
    """
    lock_path = project.lock_path
    lock = read_lockfile(lock_path)
    approve = set(_context.active_run_options().approve)
    if approve:
        unknown = approve - set(lock.packages)
        if unknown:
            listing = ", ".join(sorted(unknown))
            raise ConfigurationError(f"Cannot approve packages that are not locked: {listing}.")
        packages = {
            name: replace(package, pin_source="reviewed") if name in approve else package
            for name, package in lock.packages.items()
        }
        write_lockfile(lock_path, packages, vcpkg_baseline=lock.vcpkg_baseline)
        lock = read_lockfile(lock_path)
    rows = [_audit_row(package) for package in sorted(lock.packages.values(), key=lambda p: p.name)]
    _print_audit(rows)
    if any(row[3] for row in rows) and _context.active_run_options().exit_code:
        sys.exit(1)


def _audit_row(package: LockedPackage) -> tuple[str, str, str, str]:
    """Summarize one locked package's provenance.

    Args:
        package: The locked package.

    Returns:
        (name, version, pin source, problems or "") for the table.
    """
    source = package.pin_source or "unrecorded"
    problems = []
    if source in ("tofu", "unrecorded") and package.sha256:
        problems.append("trust-on-first-use pin; review it, then --approve")
    if (package.url or "").startswith("http://"):
        problems.append("plain HTTP")
    entry = registry_entry(package.name)
    curated = sorted(entry.sha256_by_version) if entry is not None else []
    if curated and package.version not in curated:
        problems.append(f"registry curates {', '.join(curated)}")
    return (package.name, package.version, source, "; ".join(problems))


def _print_audit(rows: list[tuple[str, str, str, str]]) -> None:
    """Print the audit table.

    Args:
        rows: (name, version, pin source, problems) rows.
    """
    if not rows:
        print("[cmakeless] No locked packages to audit.")
        return
    print(f"  {'package':<16} {'version':<12} {'pin':<12} notes")
    for name, version, source, problems in rows:
        print(f"  {name:<16} {version:<12} {source:<12} {problems}")
    flagged = sum(1 for row in rows if row[3])
    print(f"[cmakeless] {flagged} of {len(rows)} package(s) need attention.")


def _matrix(project: Project) -> None:
    """Configure, build, and test every requested preset, then summarize.

    Args:
        project: The project being built.
    """
    options = _context.active_run_options()
    model = project.freeze()
    names = list(options.presets) or [preset.name for preset in model.presets]
    if not names:
        raise ConfigurationError(
            "'cmakeless matrix' needs presets; add some with project.add_preset()."
        )
    results = [_matrix_row(project, name) for name in names]
    if options.report == "json":
        print(json.dumps(results, indent=2, sort_keys=True))
    else:
        columns = ("preset", "configure", "build", "test", "seconds")
        print("  " + " ".join(f"{column:<12}" for column in columns))
        for row in results:
            print("  " + " ".join(f"{row[column]!s:<12}" for column in columns))
    if any(row["test"] == "FAIL" or row["build"] == "FAIL" for row in results):
        sys.exit(1)


def _matrix_row(project: Project, preset: str) -> dict[str, object]:
    """Run one preset through configure, build, and test.

    Args:
        project: The project being built.
        preset: The preset name.

    Returns:
        The step outcomes and elapsed seconds for the summary.
    """
    row: dict[str, object] = {"preset": preset, "configure": "-", "build": "-", "test": "-"}
    started = time.monotonic()
    with _context.preset_override(preset):
        prepared = project._prepare()
        steps: tuple[tuple[str, Callable[[], None]], ...] = (
            ("configure", lambda: project._configure(prepared.driver)),
            ("build", lambda: prepared.driver.build(build_options())),
            ("test", lambda: prepared.driver.test(test_options(), build=build_options())),
        )
        for step, action in steps:
            try:
                action()
                row[step] = "ok"
            except CMakeError:
                row[step] = "FAIL"
                break
    row["seconds"] = round(time.monotonic() - started, 1)
    return row


_WORKFLOWS: dict[str, Callable[[Project], None]] = {
    "run": _run,
    "explain": _explain,
    "diff": _diff,
    "audit": _audit,
    "matrix": _matrix,
    "coverage": run_coverage,
    "fuzz": run_fuzz,
    "pgo": run_pgo,
    "profile": run_profile,
    "lint": run_lint_report,
    "evidence": write_evidence,
    "verify": verify_reproducible,
}

WORKFLOW_VERBS: frozenset[str] = frozenset(_WORKFLOWS)
