"""Quality verbs: coverage, fuzzing, profile-guided optimization, profiling, lint.

Each instrumented run gets a build tree of its own (build/coverage,
build/pgo-generate, ...), so the normal build is never rebuilt or polluted.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from cmakeless._version import __version__
from cmakeless.api import _context
from cmakeless.api._runs import build_options, test_options
from cmakeless.driver.cmake_driver import BuildOptions, run_program
from cmakeless.driver.file_api import CMakeInfo, TargetInfo
from cmakeless.driver.insight import (
    HeaderCost,
    StepTime,
    chrome_trace,
    header_costs,
    read_ninja_log,
)
from cmakeless.driver.sarif import Finding, parse_clang_tidy, to_sarif
from cmakeless.emitter.instrumentation import CLANG_PROFDATA_NAME, PGO_DIRECTORY_VARIABLE
from cmakeless.errors import ConfigurationError, ToolchainError

if TYPE_CHECKING:
    from cmakeless.api.project import Project

_TOP = 10
_PCH_HINT_FLOOR_US = 2_000_000
_COMPILE_COMMANDS = "compile_commands.json"


@contextmanager
def _instrumented(*names: str) -> Generator[None]:
    """Switch instrumentation on for the pipeline runs inside the block.

    Args:
        *names: Instrumentation names (INSTRUMENTATIONS members).

    Yields:
        Nothing; freeze() sees the instrumentation while the block runs.
    """
    options = replace(_context.active_run_options(), instrumentation=names)
    with _context.run_options_override(options):
        yield


def run_coverage(project: Project) -> None:
    """Build an instrumented tree, run the tests, and write a coverage report.

    Args:
        project: The project being measured.
    """
    with _instrumented("coverage"):
        prepared = project._prepare()
        prepared.driver.configure(defines=(("CMAKE_BUILD_TYPE", "Debug"),))
        prepared.driver.build(build_options())
        prepared.driver.test(test_options(), build=build_options())
        compiler = _cxx_compiler_id(prepared.driver.cmake_info())
    report = prepared.build_dir / "report"
    report.mkdir(parents=True, exist_ok=True)
    gcovr = shutil.which("gcovr")
    if gcovr is None:
        print(
            f"[cmakeless] Tests ran with coverage; raw data is in {prepared.build_dir}. "
            f"Install gcovr (pip install gcovr) for HTML and Cobertura reports."
        )
        return
    command = [gcovr, "--root", str(project.root), "--object-directory", str(prepared.build_dir)]
    if compiler in ("Clang", "AppleClang"):
        command.extend(("--gcov-executable", "llvm-cov gcov"))
    command.extend(("--exclude", ".*/_deps/.*", "--exclude", ".*/build/.*"))
    command.extend(("--html-details", str(report / "index.html")))
    command.extend(("--cobertura", str(report / "cobertura.xml"), "--print-summary"))
    subprocess.run(command, check=True)
    print(f"[cmakeless] Wrote {report / 'index.html'} and {report / 'cobertura.xml'}")


def _cxx_compiler_id(info: CMakeInfo) -> str:
    """Read the C++ compiler id from a CMakeInfo.

    Args:
        info: The CMakeInfo the driver read after configure.

    Returns:
        The id, or an empty string when CMake reported none.
    """
    return next((c.compiler_id for c in info.compilers if c.language == "CXX"), "")


def run_fuzz(project: Project) -> None:
    """Build one fuzz target and run it against its corpus for a fixed time.

    Args:
        project: The project that declares the fuzz target.

    Raises:
        ConfigurationError: When the subject is not a fuzz target.
    """
    options = _context.active_run_options()
    model = project.freeze()
    names = sorted(target.name for target in model.fuzz_targets)
    if options.subject not in names:
        raise ConfigurationError(
            f"'cmakeless fuzz {options.subject}' needs a target declared with "
            f"project.add_fuzz_target(); this project declares: {', '.join(names) or 'none'}."
        )
    prepared = project._prepare()
    project._configure(prepared.driver)
    prepared.driver.build(BuildOptions(target=options.subject, jobs=options.jobs))
    corpus = project.root / "fuzz" / "corpus" / options.subject
    artifacts = project.root / "fuzz" / "artifacts" / options.subject
    corpus.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)
    binary = _built_binary(prepared.driver.targets_info(), options.subject, prepared.build_dir)
    arguments = [str(corpus), f"-max_total_time={options.fuzz_seconds}"]
    arguments.append(f"-artifact_prefix={artifacts.as_posix()}/")
    exit_code = run_program(binary, arguments)
    if exit_code != 0:
        print(f"[cmakeless] The fuzzer found a crash; reproducers are in {artifacts}")
        sys.exit(exit_code)


def _built_binary(infos: tuple[TargetInfo, ...], name: str, build_dir: Path) -> Path:
    """Locate a target's built binary from the File API reply.

    Args:
        infos: TargetInfo objects.
        name: The target name.
        build_dir: The build tree the artifact paths are relative to.

    Returns:
        The binary's absolute path.

    Raises:
        ConfigurationError: When the target produced no artifact.
    """
    for info in infos:
        if info.name == name and info.artifacts:
            artifact = info.artifacts[0]
            return artifact if artifact.is_absolute() else build_dir / artifact
    raise ConfigurationError(f"Target {name!r} produced no binary in {build_dir}.")


def run_pgo(project: Project) -> None:
    """Instrument, run the training command, merge profiles, and rebuild optimized.

    Args:
        project: The project being optimized.

    Raises:
        ConfigurationError: When no training command was given.
    """
    options = _context.active_run_options()
    if options.train is None:
        raise ConfigurationError(
            "'cmakeless pgo' needs a training command, for example: "
            'cmakeless pgo --train "build/pgo-generate/app --bench"'
        )
    profiles = project.root / "build" / "pgo-profiles"
    profiles.mkdir(parents=True, exist_ok=True)
    defines = ((PGO_DIRECTORY_VARIABLE, profiles.as_posix()), ("CMAKE_BUILD_TYPE", "Release"))
    with _instrumented("pgo-generate"):
        _configure_and_build(project, defines)
    environment = {**os.environ, "LLVM_PROFILE_FILE": str(profiles / "%m-%p.profraw")}
    subprocess.run(shlex.split(options.train), check=True, cwd=project.root, env=environment)
    _merge_clang_profiles(profiles)
    with _instrumented("pgo-use"):
        build_dir = _configure_and_build(project, defines)
    print(f"[cmakeless] Profile-optimized build is in {build_dir}")


def _configure_and_build(project: Project, defines: tuple[tuple[str, str], ...]) -> Path:
    """Run one stage of an instrumented pipeline.

    Args:
        project: The project.
        defines: Extra cache settings for the configure step.

    Returns:
        The stage's build tree.
    """
    prepared = project._prepare()
    prepared.driver.configure(defines=defines)
    prepared.driver.build(build_options())
    return prepared.build_dir


def _merge_clang_profiles(profiles: Path) -> None:
    """Merge Clang's raw profiles into the single file -fprofile-use reads.

    GCC reads its .gcda files in place, so this does nothing for GCC.

    Args:
        profiles: The profile directory.

    Raises:
        ToolchainError: When Clang profiles exist but llvm-profdata is missing.
    """
    raw = sorted(profiles.glob("*.profraw"))
    if not raw:
        return
    tool = shutil.which("llvm-profdata")
    if tool is None:
        raise ToolchainError(
            "Clang wrote raw profiles, but llvm-profdata is not on PATH to merge them. "
            "It ships with LLVM; add its bin directory to PATH."
        )
    output = profiles / CLANG_PROFDATA_NAME
    subprocess.run([tool, "merge", f"-output={output}", *map(str, raw)], check=True)


def run_profile(project: Project) -> None:
    """Rebuild from scratch with timing on, then report where the time went.

    Args:
        project: The project being profiled.
    """
    with _instrumented("time-trace"):
        build_dir = project._build_dir()
        if build_dir.is_dir():
            shutil.rmtree(build_dir)
        prepared = project._prepare()
        project._configure(prepared.driver)
        prepared.driver.build(build_options())
    steps = read_ninja_log(prepared.build_dir)
    trace_path = prepared.build_dir / "trace.json"
    trace_path.write_text(json.dumps(chrome_trace(steps)), encoding="utf-8")
    _print_profile(steps, header_costs(prepared.build_dir))
    print(f"[cmakeless] Wrote {trace_path} (open it in https://ui.perfetto.dev)")


def _print_profile(steps: list[StepTime], headers: list[HeaderCost]) -> None:
    """Print the slowest steps and the most expensive headers, with advice.

    Args:
        steps: Build steps, slowest first.
        headers: Header costs, most expensive first.
    """
    if not steps:
        print("[cmakeless] No Ninja log found; profiling needs the Ninja generator.")
    else:
        print("[cmakeless] slowest build steps")
        for step in steps[:_TOP]:
            print(f"  {step.duration_ms / 1000:7.1f}s  {step.output}")
    if headers:
        print("[cmakeless] most expensive headers (Clang time traces)")
        for cost in headers[:_TOP]:
            print(f"  {cost.total_us / 1_000_000:7.1f}s  {cost.header}  ({cost.count} TUs)")
        heavy = [cost for cost in headers[:_TOP] if cost.total_us > _PCH_HINT_FLOOR_US]
        if heavy:
            print(
                "[cmakeless] hint: add the heaviest headers to target.pch, "
                "or try target.unity = True"
            )


def run_lint_report(project: Project) -> None:
    """Run clang-tidy over every project source and report the findings.

    Args:
        project: The project being analyzed.

    Raises:
        ToolchainError: When clang-tidy is not on PATH.
    """
    options = _context.active_run_options()
    prepared = project._prepare()
    project._configure(prepared.driver)
    command = list(prepared.model.lint_clang_tidy or ("clang-tidy",))
    if shutil.which(command[0]) is None:
        raise ToolchainError(f"'{command[0]}' is not on PATH; install LLVM's clang-tidy.")
    findings: list[Finding] = []
    for source in _project_sources(project.root, prepared.build_dir):
        completed = subprocess.run(
            [*command, "-p", str(prepared.build_dir), str(source)],
            capture_output=True,
            text=True,
            check=False,
        )
        findings.extend(parse_clang_tidy(completed.stdout))
    _write_lint_report(project, findings, options.report, options.output)
    if findings and options.exit_code:
        sys.exit(1)


def _project_sources(root: Path, build_dir: Path) -> list[Path]:
    """List the compiled sources that belong to the project itself.

    Args:
        root: The project root.
        build_dir: The configured build tree, holding compile_commands.json.

    Returns:
        Absolute source paths, excluding fetched dependencies and generated files.
    """
    database = build_dir / _COMPILE_COMMANDS
    if not database.is_file():
        return []
    entries = json.loads(database.read_text(encoding="utf-8"))
    sources = set()
    for entry in entries:
        path = Path(entry["file"])
        path = path if path.is_absolute() else Path(entry["directory"]) / path
        if path.is_relative_to(root) and not path.is_relative_to(root / "build"):
            sources.add(path.resolve())
    return sorted(sources)


def _write_lint_report(
    project: Project, findings: list[Finding], report: str, output: str | None
) -> None:
    """Print findings as text, or write them as SARIF.

    Args:
        project: The project, for its root.
        findings: The collected findings.
        report: "text" or "sarif".
        output: Where to write the SARIF file, or None for stdout.
    """
    if report == "sarif":
        sarif = to_sarif(findings, root=project.root, tool_version=__version__)
        document = json.dumps(sarif, indent=2)
        if output is None:
            print(document)
        else:
            Path(output).write_text(document + "\n", encoding="utf-8", newline="\n")
            print(f"[cmakeless] Wrote {len(findings)} finding(s) to {output}")
        return
    for finding in findings:
        location = f"{finding.file}:{finding.line}:{finding.column}"
        print(f"{location}: {finding.level}: {finding.message} [{finding.check}]")
    print(f"[cmakeless] {len(findings)} finding(s).")
