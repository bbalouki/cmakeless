"""Drives cmake configure and build, surfacing failures as structured errors."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from cmakeless.driver.error_translation import extract_diagnostics
from cmakeless.driver.generators import Generator, select_generator
from cmakeless.errors import CMakeError, ToolchainError

LOG_FILE_NAME = "cmakeless-log.txt"


class CMakeDriver:
    """Runs the CMake engine against an already-emitted source tree."""

    def __init__(
        self,
        *,
        source_dir: Path,
        build_dir: Path,
        generator: Generator | None = None,
    ) -> None:
        """Bind the driver to one source tree and build directory.

        Args:
            source_dir: Directory containing the generated CMakeLists.txt.
            build_dir: Out-of-source directory to configure and build into.
            generator: The CMake generator strategy; None auto-selects
                (Ninja when available, otherwise CMake's default).
        """
        self._source_dir = source_dir
        self._build_dir = build_dir
        self._generator = generator if generator is not None else select_generator(None)

    def configure(self) -> None:
        """Run the CMake configure and generate step into the build directory.

        Raises:
            ToolchainError: When cmake is not on PATH.
            CMakeError: When the configure step exits non-zero.
        """
        command = [
            self._cmake_executable(),
            "-S",
            str(self._source_dir),
            "-B",
            str(self._build_dir),
            *self._generator.cmake_args,
        ]
        self._run(command, step="configure")

    def build(self) -> None:
        """Run the compile step through cmake --build.

        Raises:
            ToolchainError: When cmake is not on PATH.
            CMakeError: When the build step exits non-zero.
        """
        command = [self._cmake_executable(), "--build", str(self._build_dir)]
        self._run(command, step="build")

    def _cmake_executable(self) -> str:
        """Locate the cmake executable on PATH.

        Returns:
            The absolute path to cmake.

        Raises:
            ToolchainError: When cmake is not on PATH, with install guidance.
        """
        cmake = shutil.which("cmake")
        if cmake is None:
            raise ToolchainError(
                "CMake was not found on PATH, so the build cannot run. Install "
                "CMake 3.25 or newer from https://cmake.org/download/ (or your "
                "package manager) and make sure 'cmake --version' works in this "
                "shell. Generating CMakeLists.txt with project.generate() works "
                "without CMake."
            )
        return cmake

    def _run(self, command: list[str], *, step: str) -> None:
        """Run one cmake invocation, logging and translating failures.

        Args:
            command: The full argument vector to execute.
            step: The pipeline step name ("configure" or "build"), used in
                console output and error messages.

        Raises:
            CMakeError: When the command exits non-zero, carrying the exact
                command, exit code, log path, and parsed diagnostics.
        """
        print(f"[cmakeless] Running {step}: {subprocess.list2cmdline(command)}")
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        log_path = self._append_log(step, command, completed)
        if completed.stdout:
            print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
        if completed.returncode != 0:
            diagnostics = extract_diagnostics(f"{completed.stdout or ''}\n{completed.stderr or ''}")
            summary = f" First error: {diagnostics[0]}." if diagnostics else ""
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

    def _append_log(
        self,
        step: str,
        command: list[str],
        completed: subprocess.CompletedProcess[str],
    ) -> Path:
        """Append one invocation's full output to the persistent log file.

        Args:
            step: The pipeline step name ("configure" or "build").
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
