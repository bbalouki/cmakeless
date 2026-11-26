"""Drives cmake, ctest, and cpack, surfacing failures as structured errors."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree  # nosec B405 - CTest's own report

from cmakeless.driver.error_translation import extract_diagnostics
from cmakeless.driver.file_api import (
    CMakeInfo,
    TargetInfo,
    read_cmake_info,
    read_reply,
    write_query,
)
from cmakeless.driver.generators import Generator, GeneratorFamily, select_generator
from cmakeless.errors import CMakeError, Diagnostic, ToolchainError
from cmakeless.observer import (
    Observer,
    StepFailed,
    StepFinished,
    StepStarted,
    TestFinished,
    publish,
)

LOG_FILE_NAME = "cmakeless-log.txt"
COMPILE_COMMANDS_NAME = "compile_commands.json"

# Compiler caches wired as launchers when found on PATH, best first.
_CACHE_TOOLS = ("ccache", "sccache")

# CMAKE_CXX_COMPILER_LAUNCHER only works for these generator families; Visual
# Studio and Xcode need a different mechanism, so wiring it there would be a
# silently-ignored variable and configure-time noise.
_CACHE_LAUNCHER_FAMILIES: frozenset[GeneratorFamily] = frozenset(
    {GeneratorFamily.MAKEFILES, GeneratorFamily.NINJA, GeneratorFamily.NINJA_MULTI_CONFIG}
)


@dataclass(frozen=True, slots=True)
class BuildOptions:
    """How one build, test, or install step runs.

    Attributes:
        target: Build only this target, or None for everything.
        jobs: Parallel jobs, or None for the tool default.
        config: The configuration multi-config generators build.
        verbose: True to show the real compiler and linker command lines.
    """

    target: str | None = None
    jobs: int | None = None
    config: str | None = None
    verbose: bool = False


@dataclass(frozen=True, slots=True)
class TestOptions:
    """How 'ctest' selects and reports tests.

    Attributes:
        filter: A -R regular expression over test names, or None.
        label: A -L label expression, or None.
        repeat: Rerun each test until it fails, up to this many times.
        junit: Where to write JUnit XML, or None.
    """

    # Tell pytest this options holder is not a test case.
    __test__ = False

    filter: str | None = None
    label: str | None = None
    repeat: int | None = None
    junit: Path | None = None


def resolve_tool(tool: str) -> str:
    """Locate one of the CMake suite's executables on PATH.

    A module-level function (not just a CMakeDriver method) so
    project.include()/include_module() can resolve cmake for reflection
    without needing a full driver bound to a build directory.

    Args:
        tool: "cmake", "ctest", or "cpack"; they ship together.

    Returns:
        The absolute path to the tool.

    Raises:
        ToolchainError: When the tool is not on PATH, with install guidance.
    """
    path = shutil.which(tool)
    if path is None:
        raise ToolchainError(
            f"'{tool}' was not found on PATH, so this step cannot run. It "
            f"ships with CMake: install CMake 3.25 or newer from "
            f"https://cmake.org/download/ (or your package manager) and make "
            f"sure '{tool} --version' works in this shell. Generating "
            f"CMakeLists.txt with project.generate() works without CMake."
        )
    return path


class CMakeDriver:
    """Runs the CMake engine against an already-emitted source tree."""

    def __init__(
        self,
        *,
        source_dir: Path,
        build_dir: Path,
        generator: Generator | None = None,
        extra_configure_args: tuple[str, ...] = (),
        preset: str | None = None,
        use_cache: bool = True,
        observers: Sequence[Observer] = (),
        source_owners: Mapping[str, str] | None = None,
        cache_tool: str | None = None,
        cache_env: Mapping[str, str] | None = None,
    ) -> None:
        """Bind the driver to one source tree and build directory.

        Args:
            source_dir: Directory containing the generated CMakeLists.txt.
            build_dir: Out-of-source directory to configure and build into;
                for presets this must match the preset's binaryDir.
            generator: The CMake generator strategy; None auto-selects
                (Ninja when available, otherwise CMake's default).
            extra_configure_args: Additional configure arguments, for
                example a dependency backend's -DCMAKE_TOOLCHAIN_FILE.
            preset: The CMakePresets.json preset to configure with, or
                None for the default configuration.
            use_cache: True to wire ccache/sccache as the compiler
                launcher when one is on PATH (Makefiles, Ninja, and Ninja
                Multi-Config builds only).
            observers: Progress-event consumers notified for every step.
            source_owners: Project-relative source path to a description of
                the target that compiles it (and the cmakelessfile.py line
                that declared it), appended to translated diagnostics.
            cache_tool: An explicit compiler cache ("ccache" or "sccache")
                to use instead of auto-detection, or None.
            cache_env: Environment variables the cache backend needs.
        """
        self._source_dir = source_dir
        self._build_dir = build_dir
        self._explicit_generator = generator
        self._extra_configure_args = extra_configure_args
        self._preset = preset
        self._use_cache = use_cache
        self._observers = tuple(observers)
        self._source_owners = dict(source_owners or {})
        self._cache_tool = cache_tool
        self._cache_env = dict(cache_env or {})

    @property
    def generator(self) -> Generator:
        """The generator strategy, auto-selected on first use when none was given.

        Selection is deferred so it reflects the PATH at the moment CMake
        runs, not the moment the driver was constructed.
        """
        if self._explicit_generator is None:
            self._explicit_generator = select_generator(None)
        return self._explicit_generator

    def configure(self, *, fresh: bool = False, defines: Sequence[tuple[str, str]] = ()) -> None:
        """Run the CMake configure and generate step into the build directory.

        compile_commands.json is always exported and copied to the project
        root, so clangd and clang-tidy work with zero setup.

        Args:
            fresh: True to discard the existing CMake cache first.
            defines: Extra cache settings, passed as -DNAME=VALUE.

        Raises:
            ToolchainError: When cmake is not on PATH.
            CMakeError: When the configure step exits non-zero.
        """
        write_query(self._build_dir)
        command = self._configure_command()
        if fresh:
            command.append("--fresh")
        command.extend(f"-D{name}={value}" for name, value in defines)
        self._run(command, step="configure", cwd=self._source_dir)
        self._publish_compile_commands()

    def targets_info(self) -> tuple[TargetInfo, ...]:
        """Read the configured build from the CMake File API reply.

        Configure must have run first (it writes the query CMake answers).

        Returns:
            One TargetInfo per target, sorted by name; empty when the build
            has not been configured.
        """
        return read_reply(self._build_dir)

    def cmake_info(self) -> CMakeInfo:
        """Read the resolved generator, compilers, and cache from the File API reply.

        Configure must have run first (it writes the query CMake answers).

        Returns:
            The CMakeInfo; options are raw (name, value) cache-entry
            strings, which Project.cmake_info() filters to its own declared
            options and coerces to their declared types.
        """
        return read_cmake_info(self._build_dir)

    @property
    def build_dir(self) -> Path:
        """The build directory this driver configures and builds into."""
        return self._build_dir

    def build(self, options: BuildOptions | None = None) -> None:
        """Run the compile step through cmake --build.

        Args:
            options: Target, parallelism, configuration, and verbosity, or
                None for a full default build.

        Raises:
            ToolchainError: When cmake is not on PATH.
            CMakeError: When the build step exits non-zero.
        """
        settings = options or BuildOptions()
        command = [self._tool_executable("cmake"), "--build", str(self._build_dir)]
        if settings.target is not None:
            command.extend(("--target", settings.target))
        if settings.jobs is not None:
            command.extend(("--parallel", str(settings.jobs)))
        if settings.config is not None:
            command.extend(("--config", settings.config))
        if settings.verbose:
            command.append("--verbose")
        self._run(command, step="build")

    def test(
        self, options: TestOptions | None = None, *, build: BuildOptions | None = None
    ) -> None:
        """Run the configured test suite through ctest.

        Args:
            options: Selection, repetition, and JUnit reporting, or None.
            build: The jobs and configuration to test with, or None.

        Raises:
            ToolchainError: When ctest is not on PATH.
            CMakeError: When any test fails.
        """
        selection = options or TestOptions()
        settings = build or BuildOptions()
        command = [
            self._tool_executable("ctest"),
            "--test-dir",
            str(self._build_dir),
            "--output-on-failure",
        ]
        for flag, value in (
            ("-R", selection.filter),
            ("-L", selection.label),
            ("--parallel", settings.jobs),
            ("--build-config", settings.config),
            ("--output-junit", selection.junit),
        ):
            if value is not None:
                command.extend((flag, str(value)))
        if selection.repeat is not None:
            command.extend(("--repeat", f"until-fail:{selection.repeat}"))
        try:
            self._run(command, step="test")
        finally:
            if selection.junit is not None:
                for event in read_junit(selection.junit):
                    publish(self._observers, event)

    def install(
        self, *, prefix: str | None = None, config: str | None = None, component: str | None = None
    ) -> None:
        """Install the built targets through cmake --install.

        Args:
            prefix: Installation prefix, or None for CMake's default.
            config: The configuration to install, for multi-config builds.
            component: Install only this component, or None for all.

        Raises:
            ToolchainError: When cmake is not on PATH.
            CMakeError: When the install step exits non-zero.
        """
        command = [self._tool_executable("cmake"), "--install", str(self._build_dir)]
        for flag, value in (("--prefix", prefix), ("--config", config), ("--component", component)):
            if value is not None:
                command.extend((flag, value))
        self._run(command, step="install")

    def package(self) -> None:
        """Produce the requested packages through cpack.

        Raises:
            ToolchainError: When cpack is not on PATH.
            CMakeError: When the packaging step exits non-zero.
        """
        self._run([self._tool_executable("cpack")], step="package", cwd=self._build_dir)

    def _configure_command(self) -> list[str]:
        """Assemble the configure argument vector, preset-aware.

        Returns:
            The full configure command; --preset replaces the explicit
            -S/-B pair when a preset is active.
        """
        command = [self._tool_executable("cmake")]
        if self._preset is not None:
            command.extend(("--preset", self._preset))
        else:
            command.extend(("-S", str(self._source_dir), "-B", str(self._build_dir)))
        command.extend(self.generator.cmake_args)
        command.extend(self._extra_configure_args)
        command.append("-DCMAKE_EXPORT_COMPILE_COMMANDS=ON")
        command.extend(self._cache_launcher_args())
        return command

    def _cache_launcher_args(self) -> tuple[str, ...]:
        """Wire ccache or sccache as the compiler launcher when available.

        Only Makefiles, Ninja, and Ninja Multi-Config builds get the
        launcher: Visual Studio and Xcode do not honor this variable the
        same way, and warning about an unused variable on every configure
        would be noise.

        Returns:
            The -DCMAKE_CXX_COMPILER_LAUNCHER argument, or nothing.
        """
        if not self._use_cache or self.generator.family not in _CACHE_LAUNCHER_FAMILIES:
            return ()
        tools = (self._cache_tool,) if self._cache_tool is not None else _CACHE_TOOLS
        for tool in tools:
            path = shutil.which(tool)
            if path is not None:
                return (
                    f"-DCMAKE_CXX_COMPILER_LAUNCHER={path}",
                    f"-DCMAKE_C_COMPILER_LAUNCHER={path}",
                )
        return ()

    def _publish_compile_commands(self) -> None:
        """Copy compile_commands.json to the project root, when produced.

        Multi-config generators (Visual Studio) do not produce one; that is
        a CMake limitation, not an error. The copy is a real file, not a
        symlink, so it works on Windows without privileges.
        """
        exported = self._build_dir / COMPILE_COMMANDS_NAME
        if exported.is_file():
            shutil.copyfile(exported, self._source_dir / COMPILE_COMMANDS_NAME)

    def _tool_executable(self, tool: str) -> str:
        """Locate one of the CMake suite's executables on PATH.

        Args:
            tool: "cmake", "ctest", or "cpack"; they ship together.

        Returns:
            The absolute path to the tool.

        Raises:
            ToolchainError: When the tool is not on PATH, with install
                guidance.
        """
        return resolve_tool(tool)

    def _run(self, command: list[str], *, step: str, cwd: Path | None = None) -> None:
        """Run one tool invocation, logging and translating failures.

        Args:
            command: The full argument vector to execute.
            step: The pipeline step name ("configure", "build", "test",
                "install", or "package"), used in console output and
                error messages.
            cwd: Working directory for the invocation, or None to inherit.

        Raises:
            CMakeError: When the command exits non-zero, carrying the exact
                command, exit code, log path, and parsed diagnostics.
        """
        publish(self._observers, StepStarted(step=step, command=tuple(command)))
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(cwd) if cwd is not None else None,
            env={**os.environ, **self._cache_env} if self._cache_env else None,
        )
        log_path = self._append_log(step, command, completed)
        if completed.stdout:
            print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
        if completed.returncode != 0:
            self._raise_failure(step, command, completed, log_path)
        publish(self._observers, StepFinished(step=step, exit_code=completed.returncode))

    def _raise_failure(
        self,
        step: str,
        command: list[str],
        completed: subprocess.CompletedProcess[str],
        log_path: Path,
    ) -> None:
        """Translate a failed step into a CMakeError, after telling observers and CI.

        Args:
            step: The pipeline step name.
            command: The argument vector that failed.
            completed: The finished subprocess.
            log_path: The persistent log the output was saved to.

        Raises:
            CMakeError: Always, carrying the parsed diagnostics.
        """
        diagnostics = extract_diagnostics(f"{completed.stdout or ''}\n{completed.stderr or ''}")
        publish(
            self._observers,
            StepFailed(step=step, exit_code=completed.returncode, diagnostics=diagnostics),
        )
        _annotate_for_ci(diagnostics)
        summary = (
            f" First error: {diagnostics[0]}.{self._owner_hint(diagnostics[0])}"
            if diagnostics
            else ""
        )
        raise CMakeError(
            f"CMake {step} failed with exit code {completed.returncode} for "
            f"'{self._source_dir}'.{summary} The full output was saved to "
            f"{log_path}. Fix the first error, or rerun the exact command by "
            f"hand: {subprocess.list2cmdline(command)}",
            command=command,
            exit_code=completed.returncode,
            log_path=log_path,
            diagnostics=diagnostics,
        )

    def _owner_hint(self, diagnostic: Diagnostic) -> str:
        """Name the build-description target that compiles a failing file.

        Args:
            diagnostic: The first parsed error.

        Returns:
            " (compiled by ...)" when the file belongs to a known target,
            else an empty string.
        """
        if diagnostic.file is None:
            return ""
        normalized = Path(diagnostic.file).as_posix()
        for source, owner in self._source_owners.items():
            if normalized == source or normalized.endswith("/" + source):
                return f" ({source} is compiled by {owner}.)"
        return ""

    def _append_log(
        self,
        step: str,
        command: list[str],
        completed: subprocess.CompletedProcess[str],
    ) -> Path:
        """Append one invocation's full output to the persistent log file.

        Args:
            step: The pipeline step name ("configure", "build", ...).
            command: The argument vector that was executed.
            completed: The finished subprocess with captured output.

        Returns:
            The path of the log file inside the build directory.
        """
        self._build_dir.mkdir(parents=True, exist_ok=True)
        log_path = self._build_dir / LOG_FILE_NAME
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"== {step}: {subprocess.list2cmdline(command)}\n")
            log_file.write(completed.stdout or "")
            log_file.write(completed.stderr or "")
            log_file.write(f"== exit code: {completed.returncode}\n")
        return log_path


def _annotate_for_ci(diagnostics: Sequence[Diagnostic]) -> None:
    """Print GitHub Actions annotations so errors appear inline on the diff.

    Args:
        diagnostics: The parsed errors; only located ones are annotated.
    """
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    for diagnostic in diagnostics:
        if diagnostic.file is not None and diagnostic.line is not None:
            print(f"::error file={diagnostic.file},line={diagnostic.line}::{diagnostic.message}")


def run_program(executable: Path, arguments: Sequence[str]) -> int:
    """Run a freshly built program, streaming its output to this terminal.

    Args:
        executable: The built binary.
        arguments: Arguments passed through unchanged.

    Returns:
        The program's exit code.

    Raises:
        ToolchainError: When the binary does not exist.
    """
    if not executable.is_file():
        raise ToolchainError(
            f"The built program {executable} does not exist. Build it first, or "
            f"check the target name with 'cmakeless explain'."
        )
    return subprocess.run([str(executable), *arguments], check=False).returncode


def read_junit(report: Path) -> list[TestFinished]:
    """Turn CTest's JUnit report into one event per test case.

    Args:
        report: The --output-junit file.

    Returns:
        The events, in report order; empty when the report is missing or
        unreadable.
    """
    if not report.is_file():
        return []
    try:
        root = ElementTree.parse(report).getroot()  # nosec B314 - CTest wrote it locally
    except ElementTree.ParseError:
        return []
    events = []
    for case in root.iter("testcase"):
        status = case.get("status", "run")
        if case.find("failure") is not None or case.find("error") is not None:
            status = "failed"
        elif case.find("skipped") is not None or status == "notrun":
            status = "skipped"
        else:
            status = "passed"
        seconds = float(case.get("time", "0") or 0)
        events.append(
            TestFinished(step="test", name=case.get("name", "?"), status=status, seconds=seconds)
        )
    return events
