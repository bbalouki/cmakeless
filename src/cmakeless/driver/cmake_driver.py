"""Drives cmake, ctest, and cpack, surfacing failures as structured errors."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from cmakeless.driver.error_translation import extract_diagnostics
from cmakeless.driver.generators import Generator, select_generator
from cmakeless.errors import CMakeError, ToolchainError

LOG_FILE_NAME = "cmakeless-log.txt"
COMPILE_COMMANDS_NAME = "compile_commands.json"

# Compiler caches wired as launchers when found on PATH, best first.
_CACHE_TOOLS = ("ccache", "sccache")


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
                launcher when one is on PATH (Ninja builds only).
        """
        self._source_dir = source_dir
        self._build_dir = build_dir
        self._generator = generator if generator is not None else select_generator(None)
        self._extra_configure_args = extra_configure_args
        self._preset = preset
        self._use_cache = use_cache

    def configure(self) -> None:
        """Run the CMake configure and generate step into the build directory.

        compile_commands.json is always exported and copied to the project
        root, so clangd and clang-tidy work with zero setup.

        Raises:
            ToolchainError: When cmake is not on PATH.
            CMakeError: When the configure step exits non-zero.
        """
        self._run(self._configure_command(), step="configure", cwd=self._source_dir)
        self._publish_compile_commands()

    def build(self) -> None:
        """Run the compile step through cmake --build.

        Raises:
            ToolchainError: When cmake is not on PATH.
            CMakeError: When the build step exits non-zero.
        """
        command = [self._tool_executable("cmake"), "--build", str(self._build_dir)]
        self._run(command, step="build")

    def test(self) -> None:
        """Run the configured test suite through ctest.

        Raises:
            ToolchainError: When ctest is not on PATH.
            CMakeError: When any test fails.
        """
        command = [
            self._tool_executable("ctest"),
            "--test-dir",
            str(self._build_dir),
            "--output-on-failure",
        ]
        self._run(command, step="test")

    def install(self, *, prefix: str | None = None) -> None:
        """Install the built targets through cmake --install.

        Args:
            prefix: Installation prefix, or None for CMake's default.

        Raises:
            ToolchainError: When cmake is not on PATH.
            CMakeError: When the install step exits non-zero.
        """
        command = [self._tool_executable("cmake"), "--install", str(self._build_dir)]
        if prefix is not None:
            command.extend(("--prefix", prefix))
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
        command.extend(self._generator.cmake_args)
        command.extend(self._extra_configure_args)
        command.append("-DCMAKE_EXPORT_COMPILE_COMMANDS=ON")
        command.extend(self._cache_launcher_args())
        return command

    def _cache_launcher_args(self) -> tuple[str, ...]:
        """Wire ccache or sccache as the compiler launcher when available.

        Only Ninja builds get the launcher: the Visual Studio generator
        ignores it, and warning about an unused variable on every configure
        would be noise.

        Returns:
            The -DCMAKE_CXX_COMPILER_LAUNCHER argument, or nothing.
        """
        if not self._use_cache or self._generator.name != "ninja":
            return ()
        for tool in _CACHE_TOOLS:
            path = shutil.which(tool)
            if path is not None:
                return (f"-DCMAKE_CXX_COMPILER_LAUNCHER={path}",)
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
        print(f"[cmakeless] Running {step}: {subprocess.list2cmdline(command)}")
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(cwd) if cwd is not None else None,
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
