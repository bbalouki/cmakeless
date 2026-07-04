# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Model to CMakeLists.txt: a Visitor over the frozen build graph.

The generated file is our public face. The contract: modern target-centric
CMake only, byte-deterministic output, a self-describing header, and the
result must build with plain cmake on a machine without Python.

Target emission follows a fixed Template Method skeleton (declare, sources,
include dirs, compile features, properties, definitions, options, links) with
per-target-kind variations, which is what keeps the output uniform and boring.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from cmakeless._constants import CMAKELESS_SYSTEM_NAME_VAR, CMAKELESS_SYSTEM_PROCESSOR_VAR
from cmakeless.emitter.presets_emitter import emit_presets
from cmakeless.emitter.sanitizers import (
    MSVC_SUPPORTED_SANITIZERS,
    SANITIZE_CACHE_VARIABLE,
    preset_sanitize_lines,
    preset_sanitizer_union,
    static_sanitize_lines,
)
from cmakeless.emitter.toolchain_emitter import emit_toolchain
from cmakeless.emitter.when_emitter import guarded
from cmakeless.model.nodes import (
    BUILD_TYPE_BY_OPTIMIZE,
    CPACK_GENERATOR_BY_FORMAT,
    CommandModel,
    CompiledModel,
    CompileOptionsModel,
    CustomTargetModel,
    DependencyModel,
    ExecutableModel,
    InstallModel,
    LibraryKind,
    LibraryModel,
    LinkOptionsModel,
    ModuleKind,
    ModuleModel,
    OptionModel,
    OptionType,
    ProjectModel,
    PythonModuleModel,
    TestModel,
)

CMAKE_MINIMUM_VERSION = "3.25"

# Warning presets translated per compiler family; "default" emits nothing and
# leaves the compiler's own defaults in charge.
_STRICT_WARNINGS_MSVC: tuple[str, ...] = ("/W4", "/permissive-")
_STRICT_WARNINGS_OTHER: tuple[str, ...] = (
    "-Wall",
    "-Wextra",
    "-Wconversion",
    "-Wsign-conversion",
    "-pedantic",
)
_NO_WARNINGS_MSVC: tuple[str, ...] = ("/W0",)
_NO_WARNINGS_OTHER: tuple[str, ...] = ("-w",)

# Per-framework discovery-module setup, emitted once per framework in use.
# The guards make one file serve both worlds: an installed package provides
# the module on the module path, a source fetch keeps it in its own tree.
_INTEGRATION_BY_FRAMEWORK = {
    "catch2": (
        "# Catch2's per-case discovery module (extras/ when fetched from source).\n"
        "if(catch2_SOURCE_DIR)\n"
        "    list(APPEND CMAKE_MODULE_PATH ${catch2_SOURCE_DIR}/extras)\n"
        "endif()\n"
        "include(Catch)"
    ),
    "gtest": "include(GoogleTest)",
    "doctest": (
        "# doctest's per-case discovery module (scripts/cmake when fetched from source).\n"
        "if(doctest_SOURCE_DIR)\n"
        "    include(${doctest_SOURCE_DIR}/scripts/cmake/doctest.cmake)\n"
        "else()\n"
        "    include(doctest)\n"
        "endif()"
    ),
}

# The CTest registration command per framework; {name} is the test target.
_DISCOVERY_BY_FRAMEWORK = {
    "catch2": "catch_discover_tests({name})",
    "gtest": "gtest_discover_tests({name})",
    "doctest": "doctest_discover_tests({name})",
    "none": "add_test(NAME {name} COMMAND {name})",
}


def emit_cmakelists(model: ProjectModel, *, tool_version: str) -> str:
    """Generate the complete, standalone CMakeLists.txt for one project node.

    Args:
        model: The frozen project to emit (subprojects appear only as
            add_subdirectory calls; their files come from emit_tree).
        tool_version: The cmakeless version stamped into the header comment.

    Returns:
        The full CMakeLists.txt text, newline-terminated.
    """
    return _CMakeListsVisitor(model, tool_version).emit()


def emit_tree(model: ProjectModel, *, tool_version: str) -> dict[Path, str]:
    """Generate every build file in the project tree.

    Besides one CMakeLists.txt per project node, this includes each node's
    CMakePresets.json (when it defines presets), generated toolchain files,
    and the Config.cmake.in template consumed by its install rules.

    Args:
        model: The frozen root project.
        tool_version: The cmakeless version stamped into header comments.

    Returns:
        File contents keyed by path relative to the root project's
        directory; the root files first, subprojects following in path order.
    """
    files: dict[Path, str] = {
        Path("CMakeLists.txt"): emit_cmakelists(model, tool_version=tool_version)
    }
    if model.presets:
        files[Path("CMakePresets.json")] = emit_presets(model)
    for toolchain in sorted(model.toolchains, key=lambda node: node.name):
        if toolchain.file is None:
            files[Path("cmake") / "toolchains" / f"{toolchain.name}.cmake"] = emit_toolchain(
                toolchain, tool_version=tool_version, source_script=model.source_script
            )
    if model.installs:
        files[Path("cmake") / f"{model.name}Config.cmake.in"] = _config_template(model.name)
    for subproject in sorted(model.subprojects, key=lambda node: node.directory.as_posix()):
        subtree = emit_tree(subproject.project, tool_version=tool_version)
        for relative_path, text in subtree.items():
            files[subproject.directory / relative_path] = text
    return files


def _config_template(name: str) -> str:
    """Write the Config.cmake.in template for a project's export set.

    Args:
        name: The project name the package is found by.

    Returns:
        The template text configure_package_config_file() consumes.
    """
    return (
        f"@PACKAGE_INIT@\n"
        f"\n"
        f'include("${{CMAKE_CURRENT_LIST_DIR}}/{name}Targets.cmake")\n'
        f"\n"
        f"check_required_components({name})\n"
    )


class _CMakeListsVisitor:
    """Each node type contributes its own section; the traversal stays fixed."""

    def __init__(self, model: ProjectModel, tool_version: str) -> None:
        """Bind the visitor to one project node.

        Args:
            model: The frozen project to emit.
            tool_version: The cmakeless version stamped into the header.
        """
        self._model = model
        self._tool_version = tool_version

    def emit(self) -> str:
        """Walk the project and assemble the full file.

        Returns:
            The complete CMakeLists.txt text, newline-terminated.
        """
        sections = [
            self._header(),
            self._preamble(),
            self._reflection_preamble(),
            *self._default_build_config(),
            *self._options_section(),
            *self._raw_cmake_file_includes(),
            *self._module_sections(),
            *self._module_includes(),
        ]
        if _tree_has_tests(self._model):
            sections.append("enable_testing()")
        sections.extend(self._python_preamble())
        sections.extend(self._preset_sanitize_preamble())
        sections.extend(
            self._visit_dependency(dependency)
            for dependency in sorted(self._model.dependencies, key=lambda dep: dep.name)
        )
        subdirectories = sorted(node.directory.as_posix() for node in self._model.subprojects)
        sections.extend(f"add_subdirectory({directory})" for directory in subdirectories)
        sections.extend(self._command_sections())
        sections.extend(self._target_sections())
        sections.extend(self._custom_target_sections())
        sections.extend(self._install_sections())
        sections.extend(self._cpack_section())
        return "\n\n".join(sections) + "\n"

    def _target_sections(self) -> list[str]:
        """Emit every target, in the deterministic order the contract needs.

        Declaration order in cmakelessfile.py is meaningless to CMake, so targets are
        sorted within each kind (libraries, executables, Python modules, then
        tests) to keep the output diffable.

        Returns:
            One section per target, framework discovery includes included.
        """
        sections = [
            self._visit_library(library)
            for library in sorted(self._model.libraries, key=lambda target: target.name)
        ]
        sections.extend(
            self._visit_executable(target)
            for target in sorted(self._model.executables, key=lambda target: target.name)
        )
        sections.extend(
            self._visit_python_module(module)
            for module in sorted(self._model.python_modules, key=lambda target: target.name)
        )
        sections.extend(self._framework_includes())
        sections.extend(
            self._visit_test(test)
            for test in sorted(self._model.tests, key=lambda target: target.name)
        )
        return sections

    def _command_sections(self) -> list[str]:
        """Emit every add_command() step, sorted by first output for determinism.

        Returns:
            One add_custom_command() section per registered command.
        """
        return [
            self._visit_command(command)
            for command in sorted(
                self._model.commands, key=lambda command: command.outputs[0].as_posix()
            )
        ]

    def _anchor_command_token(self, token: str, *, depends: tuple[Path, ...]) -> str:
        """Anchor a COMMAND argument that names a declared output or depend.

        CMake runs a custom command's argument vector with the build
        directory as the default working directory, unlike OUTPUT/DEPENDS
        paths, which CMake always resolves itself regardless of where the
        command actually runs. A bare relative path *inside* the command
        line (a script's own argv, not the OUTPUT/DEPENDS clauses) would
        therefore be looked up from the wrong place. Anchoring only the
        tokens that exactly match a declared output (this command's own, or
        another command's, so chained code-generation steps work too) or
        depend keeps every other argument (flags, the interpreter name)
        untouched.

        Args:
            token: One argument from the command's argument vector.
            depends: The command's declared dependencies.

        Returns:
            The token, prefixed with ${CMAKE_CURRENT_BINARY_DIR}/ or
            ${CMAKE_CURRENT_SOURCE_DIR}/ when it names a declared path, else
            unchanged.
        """
        normalized = Path(token).as_posix()
        all_outputs = {output.as_posix() for cmd in self._model.commands for output in cmd.outputs}
        if normalized in all_outputs:
            return f"${{CMAKE_CURRENT_BINARY_DIR}}/{normalized}"
        if any(normalized == depend.as_posix() for depend in depends):
            return f"${{CMAKE_CURRENT_SOURCE_DIR}}/{normalized}"
        return token

    def _visit_command(self, command: CommandModel) -> str:
        """Emit one build-time step as add_custom_command(OUTPUT ...).

        Args:
            command: The command to emit.

        Returns:
            The command's complete section text.
        """
        argv = " ".join(
            self._anchor_command_token(token, depends=command.depends) for token in command.command
        )
        lines = ["add_custom_command(", "    OUTPUT"]
        lines.extend(f"        {output.as_posix()}" for output in command.outputs)
        lines.append("    COMMAND " + argv)
        if command.depends:
            depends = " ".join(depend.as_posix() for depend in sorted(command.depends))
            lines.append(f"    DEPENDS {depends}")
        if command.comment is not None:
            lines.append(f'    COMMENT "{command.comment}"')
        lines.append("    VERBATIM")
        lines.append(")")
        return "\n".join(lines)

    def _custom_target_sections(self) -> list[str]:
        """Emit every add_custom_target(), sorted by name for determinism.

        Returns:
            One add_custom_target() section per registered custom target.
        """
        return [
            self._visit_custom_target(target)
            for target in sorted(self._model.custom_targets, key=lambda target: target.name)
        ]

    def _visit_custom_target(self, target: CustomTargetModel) -> str:
        """Emit one always-runnable target as add_custom_target(...).

        Args:
            target: The custom target to emit.

        Returns:
            The target's complete section text.
        """
        argv = " ".join(
            self._anchor_command_token(token, depends=target.depends) for token in target.command
        )
        lines = [f"add_custom_target({target.name}", "    COMMAND " + argv]
        if target.depends:
            depends = " ".join(depend.as_posix() for depend in sorted(target.depends))
            lines.append(f"    DEPENDS {depends}")
        lines.append("    VERBATIM")
        lines.append(")")
        return "\n".join(lines)

    def _module_includes(self) -> list[str]:
        """Collect the include() lines the emitted commands rely on.

        Returns:
            Zero or more include commands, in a fixed order.
        """
        includes: list[str] = []
        if any(library.kind is LibraryKind.SHARED for library in self._model.libraries):
            includes.append("include(GenerateExportHeader)")
        if self._model.dependencies and self._model.package_manager == "auto":
            includes.append("include(FetchContent)")
        if self._model.installs:
            includes.append("include(GNUInstallDirs)")
        return includes

    def _header(self) -> str:
        """Write the self-describing header comment.

        Returns:
            Comment lines naming the tool version and the source cmakelessfile.py.
        """
        return (
            f"# Generated by cmakeless {self._tool_version} "
            f"from {self._model.source_script}.\n"
            f"# This file is standalone: it builds with plain CMake, no Python needed.\n"
            f"# Prefer editing {self._model.source_script} and regenerating over "
            f"editing this file."
        )

    def _preamble(self) -> str:
        """Write cmake_minimum_required and the project() declaration.

        Returns:
            The preamble section text.
        """
        return (
            f"cmake_minimum_required(VERSION {CMAKE_MINIMUM_VERSION})\n"
            f"\n"
            f"project({self._model.name}\n"
            f"    VERSION {self._model.version}\n"
            f"    LANGUAGES CXX\n"
            f")"
        )

    def _reflection_preamble(self) -> str:
        """Promote CMAKE_SYSTEM_NAME/PROCESSOR into cache entries cmake_info() reads.

        The CMake File API's cache object does not reliably carry these two
        variables for a native (non-cross) build, so cmake_info() cannot
        read them the way it reads every other resolved value; promoting
        them here keeps cmake_info() fully File-API-native, with no
        --trace-expand and no text scraping.

        Returns:
            The two set(... CACHE INTERNAL ...) lines, always emitted.
        """
        return (
            f'set({CMAKELESS_SYSTEM_NAME_VAR} "${{CMAKE_SYSTEM_NAME}}" CACHE INTERNAL "")\n'
            f'set({CMAKELESS_SYSTEM_PROCESSOR_VAR} "${{CMAKE_SYSTEM_PROCESSOR}}" '
            f'CACHE INTERNAL "")'
        )

    def _default_build_config(self) -> list[str]:
        """Set the default build type and LTO for the plain (no-preset) build.

        Both are guarded so an active preset, which delivers them as cache
        variables, always wins: the guards are false under a preset and true
        on a plain build. The CMAKE_CONFIGURATION_TYPES clause leaves
        multi-config generators (Visual Studio, Xcode) to their own defaults.

        Returns:
            Zero, one, or two sections; empty when neither optimize nor lto
            was set, so a plain project's output is unchanged.
        """
        sections: list[str] = []
        if self._model.optimize is not None:
            build_type = BUILD_TYPE_BY_OPTIMIZE[self._model.optimize]
            sections.append(
                f"# Default build type; an active preset overrides it.\n"
                f"if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)\n"
                f'    set(CMAKE_BUILD_TYPE "{build_type}" CACHE STRING\n'
                f'        "Build type for the default configuration" FORCE)\n'
                f"endif()"
            )
        if self._model.lto:
            sections.append(
                "# Project-level LTO default; a preset's own setting wins.\n"
                "if(NOT DEFINED CMAKE_INTERPROCEDURAL_OPTIMIZATION)\n"
                "    set(CMAKE_INTERPROCEDURAL_OPTIMIZATION ON)\n"
                "endif()"
            )
        return sections

    def _options_section(self) -> list[str]:
        """Declare every project.option() as a CMake cache variable.

        Returns:
            One command per option, sorted by name for determinism; empty
            when the project declares none.
        """
        return [
            self._visit_option(option)
            for option in sorted(self._model.options, key=lambda option: option.name)
        ]

    def _visit_option(self, option: OptionModel) -> str:
        """Emit one declared option as option() or a CACHE variable.

        Args:
            option: The option to emit.

        Returns:
            The command text.
        """
        help_text = option.help.replace('"', '\\"')
        if option.value_type is OptionType.BOOL:
            value = "ON" if option.default else "OFF"
            return f'option({option.name} "{help_text}" {value})'
        return f'set({option.name} "{option.default}" CACHE STRING "{help_text}")'

    def _raw_cmake_file_includes(self) -> list[str]:
        """Include the project's raw_cmake_file escape-hatch files near the top.

        Emitted in the order they were added, each fenced with a comment
        naming the cmakelessfile.py origin; the CMAKE_CURRENT_SOURCE_DIR prefix keeps
        the generated file standalone and relocatable.

        Returns:
            One section per file; empty when none were added.
        """
        script = self._model.source_script
        return [
            f"# raw_cmake_file from {script}: {raw_file.as_posix()}\n"
            f"include(${{CMAKE_CURRENT_SOURCE_DIR}}/{raw_file.as_posix()})"
            for raw_file in self._model.raw_cmake_files
        ]

    def _module_sections(self) -> list[str]:
        """Emit every project.include()/include_module() call, in declaration order.

        Unlike commands and custom targets, these are never sorted: a
        reflected include's calls can have order-dependent side effects,
        and CMakeless cannot know which.

        Returns:
            One section per include, each followed immediately by its
            validated calls; empty when none were added.
        """
        return [self._visit_module(module) for module in self._model.modules]

    def _visit_module(self, module: ModuleModel) -> str:
        """Emit one reflected include(), then its validated calls.

        Args:
            module: The include to emit.

        Returns:
            The include's complete section text.
        """
        script = self._model.source_script
        verb = "include_module" if module.kind is ModuleKind.NAMED else "include"
        lines = [f"# project.{verb}() from {script}: {module.reference}"]
        if module.module_path is not None:
            lines.append(
                f"list(APPEND CMAKE_MODULE_PATH "
                f'"${{CMAKE_CURRENT_SOURCE_DIR}}/{module.module_path.as_posix()}")'
            )
        if module.kind is ModuleKind.FILE:
            lines.append(f"include(${{CMAKE_CURRENT_SOURCE_DIR}}/{module.reference})")
        else:
            lines.append(f"include({module.reference})")
        lines.extend(f"{call.function}({' '.join(call.args)})" for call in module.calls)
        return "\n".join(lines)

    def _visit_dependency(self, dependency: DependencyModel) -> str:
        """Emit one external dependency, dispatching on the package manager.

        Args:
            dependency: The resolved dependency to emit.

        Returns:
            The dependency's complete section text.
        """
        if self._model.package_manager == "auto":
            return self._dependency_fallback_block(dependency)
        return self._dependency_find_package_block(dependency)

    def _dependency_find_package_block(self, dependency: DependencyModel) -> str:
        """Emit a plain find_package call for the single-backend modes.

        Args:
            dependency: The resolved dependency to emit.

        Returns:
            A commented find_package command.
        """
        name = _resolved_cmake_name(dependency)
        if self._model.package_manager == "vcpkg":
            comment = "provided by vcpkg (see vcpkg.json)"
            arguments = f"{name} CONFIG REQUIRED"
        elif self._model.package_manager == "conan":
            comment = "provided by Conan (see conanfile.txt)"
            arguments = f"{name} REQUIRED"
        else:
            comment = "system package, version-checked by find_package()"
            arguments = f"{name} {dependency.version} REQUIRED"
        return (
            f"# {dependency.name} {dependency.version}: {comment}.\n"
            f"find_package({arguments}{_components_suffix(dependency)})"
        )

    def _dependency_fallback_block(self, dependency: DependencyModel) -> str:
        """Emit the find_package-then-FetchContent fallback for "auto" mode.

        The TARGET guard keeps the block idempotent when a parent project
        in the same tree already provided the package.

        Args:
            dependency: The resolved dependency, fetch pin included.

        Returns:
            The commented fallback section.
        """
        name = _resolved_cmake_name(dependency)
        assert dependency.url is not None, "the auto strategy must pin a URL"
        assert dependency.sha256 is not None, "the auto strategy must pin a hash"
        assert dependency.link_targets, "validation guarantees imported targets"
        return (
            f"# {dependency.name} {dependency.version}: system package when "
            f"available, pinned source fetch otherwise.\n"
            f"find_package({name} {dependency.version} QUIET"
            f"{_components_suffix(dependency)})\n"
            f"if(NOT {name}_FOUND AND NOT TARGET {dependency.link_targets[0]})\n"
            f"    FetchContent_Declare({dependency.name}\n"
            f"        URL {dependency.url}\n"
            f"        URL_HASH SHA256={dependency.sha256}\n"
            f"    )\n"
            f"    FetchContent_MakeAvailable({dependency.name})\n"
            f"endif()"
        )

    def _cpp_std_for(self, target: CompiledModel) -> int:
        """The C++ standard a target compiles with: its own override, or the project's.

        Args:
            target: The target to resolve the standard for.

        Returns:
            The target's cpp_std override when set, else the project's.
        """
        return target.cpp_std if target.cpp_std is not None else self._model.cpp_std

    def _visit_executable(self, target: ExecutableModel) -> str:
        """Emit one executable target.

        Args:
            target: The executable to emit.

        Returns:
            The target's complete section text.
        """
        blocks = [f"add_executable({target.name})"]
        blocks.append(self._sources_block(target, "PRIVATE"))
        private_include_dirs = self._private_include_dirs_block(target, "PRIVATE")
        if private_include_dirs is not None:
            blocks.append(private_include_dirs)
        blocks.append(
            f"target_compile_features({target.name} PRIVATE cxx_std_{self._cpp_std_for(target)})"
        )
        blocks.extend(self._settings_blocks(target, "PRIVATE"))
        return "\n\n".join(blocks)

    def _python_preamble(self) -> list[str]:
        """Find the Python development headers when modules need them.

        Returns:
            A find_package(Python ...) section when the project has Python
            modules, plus the pybind11 hint that makes it use that same
            interpreter (its legacy default can pick a different one, which
            produces a module with the wrong ABI tag); empty otherwise.
        """
        if not self._model.python_modules:
            return []
        version = _max_python_version(
            module.python_version for module in self._model.python_modules
        )
        lines = (
            "# find_package(Python ...) takes a minimum version, not an exact one:\n"
            "# this is the highest floor any add_python_module(python_version=...) requested.\n"
            f"find_package(Python {version} COMPONENTS Interpreter "
            f"Development.Module REQUIRED)"
        )
        if any(module.binding == "pybind11" for module in self._model.python_modules):
            lines += "\n# Make pybind11 build against the Python found above, not its own guess.\n"
            lines += "set(PYBIND11_FINDPYTHON ON)"
        return [lines]

    def _visit_python_module(self, target: PythonModuleModel) -> str:
        """Emit one Python extension module built with its binding backend.

        Args:
            target: The Python module to emit.

        Returns:
            The target's complete section text.
        """
        blocks = [f"{target.binding}_add_module({target.name})"]
        blocks.append(self._sources_block(target, "PRIVATE"))
        private_include_dirs = self._private_include_dirs_block(target, "PRIVATE")
        if private_include_dirs is not None:
            blocks.append(private_include_dirs)
        blocks.append(
            f"target_compile_features({target.name} PRIVATE cxx_std_{self._cpp_std_for(target)})"
        )
        blocks.extend(self._settings_blocks(target, "PRIVATE"))
        if target.stubs and target.binding == "nanobind":
            blocks.append(self._stub_block(target))
        return "\n\n".join(blocks)

    def _stub_block(self, target: PythonModuleModel) -> str:
        """Emit a .pyi stub generation rule for a nanobind module.

        Args:
            target: The nanobind module to generate a stub for.

        Returns:
            The nanobind_add_stub command text.
        """
        return (
            f"nanobind_add_stub({target.name}_stub\n"
            f"    MODULE {target.name}\n"
            f"    OUTPUT {target.name}.pyi\n"
            f"    PYTHON_PATH $<TARGET_FILE_DIR:{target.name}>\n"
            f"    DEPENDS {target.name}\n"
            f")"
        )

    def _visit_library(self, target: LibraryModel) -> str:
        """Emit one library target, dispatching on its kind.

        Args:
            target: The library to emit.

        Returns:
            The target's complete section text.
        """
        if target.kind is LibraryKind.HEADER_ONLY:
            return self._visit_header_only_library(target)
        keyword = "STATIC" if target.kind is LibraryKind.STATIC else "SHARED"
        blocks = [f"add_library({target.name} {keyword})"]
        blocks.append(self._sources_block(target, "PRIVATE"))
        private_include_dirs = self._private_include_dirs_block(target, "PRIVATE")
        if private_include_dirs is not None:
            blocks.append(private_include_dirs)
        if target.public_include_dirs:
            blocks.append(self._include_dirs_block(target, "PUBLIC"))
        blocks.append(
            f"target_compile_features({target.name} PUBLIC cxx_std_{self._cpp_std_for(target)})"
        )
        # Explicit PIC keeps static libraries linkable into shared ones.
        blocks.append(
            f"set_target_properties({target.name} PROPERTIES POSITION_INDEPENDENT_CODE ON)"
        )
        if target.kind is LibraryKind.SHARED:
            blocks.append(self._export_header_block(target))
        blocks.extend(self._settings_blocks(target, "PRIVATE"))
        return "\n\n".join(blocks)

    def _visit_test(self, target: TestModel) -> str:
        """Emit one test target: an executable plus its CTest registration.

        Args:
            target: The test to emit.

        Returns:
            The target's complete section text.
        """
        blocks = [f"add_executable({target.name})"]
        blocks.append(self._sources_block(target, "PRIVATE"))
        private_include_dirs = self._private_include_dirs_block(target, "PRIVATE")
        if private_include_dirs is not None:
            blocks.append(private_include_dirs)
        blocks.append(
            f"target_compile_features({target.name} PRIVATE cxx_std_{self._cpp_std_for(target)})"
        )
        blocks.extend(self._settings_blocks(target, "PRIVATE"))
        if self._links_shared_library(target):
            blocks.append(self._runtime_dll_copy_block(target))
        blocks.append(_DISCOVERY_BY_FRAMEWORK[target.framework].format(name=target.name))
        return "\n\n".join(blocks)

    def _framework_includes(self) -> list[str]:
        """Emit the discovery-module includes for every framework in use.

        A source fetch keeps each framework's CMake module inside its own
        source tree, so the include is guarded to work both with installed
        packages and with the FetchContent fallback.

        Returns:
            One include block per framework, sorted by framework name.
        """
        frameworks = sorted({test.framework for test in self._model.tests} - {"none"})
        return [_INTEGRATION_BY_FRAMEWORK[framework] for framework in frameworks]

    def _links_shared_library(self, target: TestModel) -> bool:
        """Tell whether a test transitively links a shared library of this project.

        Args:
            target: The test to inspect.

        Returns:
            True when a project shared library is reachable through the
            link graph, so the test needs its DLLs next to it on Windows.
        """
        libraries_by_name = {library.name: library for library in self._model.libraries}
        stack = [link.target for link in target.links if not link.external]
        seen: set[str] = set()
        while stack:
            name = stack.pop()
            if name in seen or name not in libraries_by_name:
                continue
            seen.add(name)
            library = libraries_by_name[name]
            if library.kind is LibraryKind.SHARED:
                return True
            stack.extend(link.target for link in library.links if not link.external)
        return False

    def _runtime_dll_copy_block(self, target: TestModel) -> str:
        """Copy linked DLLs next to a test binary so it runs on Windows.

        Args:
            target: The test that links shared libraries.

        Returns:
            The guarded post-build copy command.
        """
        return (
            f"if(WIN32)\n"
            f"    add_custom_command(TARGET {target.name} POST_BUILD\n"
            f"        COMMAND ${{CMAKE_COMMAND}} -E copy_if_different\n"
            f"            $<TARGET_RUNTIME_DLLS:{target.name}> "
            f"$<TARGET_FILE_DIR:{target.name}>\n"
            f"        COMMAND_EXPAND_LISTS\n"
            f"    )\n"
            f"endif()"
        )

    def _preset_sanitize_preamble(self) -> list[str]:
        """Declare the cache variable presets use to switch sanitizers on.

        Returns:
            The declaration (and, when a requested sanitizer has no MSVC
            support, a loud configure-time rejection); empty when no preset
            requests sanitizers.
        """
        union = preset_sanitizer_union(self._model)
        if not union:
            return []
        sections = [
            f"# Sanitizers are switched on per preset; see CMakePresets.json.\n"
            f'set({SANITIZE_CACHE_VARIABLE} "" CACHE STRING\n'
            f'    "Sanitizers applied to every target (semicolon-separated)"\n'
            f")"
        ]
        if set(union) - MSVC_SUPPORTED_SANITIZERS:
            sections.append(
                f"if(MSVC)\n"
                f"    foreach(sanitizer IN LISTS {SANITIZE_CACHE_VARIABLE})\n"
                f'        if(NOT sanitizer STREQUAL "address")\n'
                f"            message(FATAL_ERROR \"Sanitizer '${{sanitizer}}' is not "
                f'supported by MSVC. Build with Clang or GCC, or pick a preset without it.")\n'
                f"        endif()\n"
                f"    endforeach()\n"
                f"endif()"
            )
        return sections

    def _visit_header_only_library(self, target: LibraryModel) -> str:
        """Emit a header-only library as an INTERFACE target.

        Args:
            target: The header-only library to emit.

        Returns:
            The target's complete section text.
        """
        blocks = [f"add_library({target.name} INTERFACE)"]
        blocks.append(self._include_dirs_block(target, "INTERFACE"))
        blocks.append(
            f"target_compile_features({target.name} INTERFACE cxx_std_{self._cpp_std_for(target)})"
        )
        blocks.extend(self._settings_blocks(target, "INTERFACE", warnings=False))
        return "\n\n".join(blocks)

    def _sources_block(self, target: CompiledModel, visibility: str) -> str:
        """Write a target_sources command with sorted sources.

        Args:
            target: The target whose sources to list.
            visibility: The CMake visibility keyword to use.

        Returns:
            The command text.
        """
        lines = [f"target_sources({target.name} {visibility}"]
        lines.extend(f"    {source.as_posix()}" for source in sorted(target.sources))
        lines.append(")")
        return "\n".join(lines)

    def _private_include_dirs_block(self, target: CompiledModel, visibility: str) -> str | None:
        """Write a target_include_directories command for a target's own private dirs.

        Unlike a library's public include dirs, private dirs never leak
        into an install interface, so no $<BUILD_INTERFACE:...> wrapping is
        needed here.

        Args:
            target: The target whose private include dirs to list.
            visibility: The CMake visibility keyword to use.

        Returns:
            The command text, or None when the target has none.
        """
        if not target.private_include_dirs:
            return None
        lines = [f"target_include_directories({target.name} {visibility}"]
        lines.extend(
            f"    {directory.as_posix()}" for directory in sorted(target.private_include_dirs)
        )
        lines.append(")")
        return "\n".join(lines)

    def _link_options_block(self, target: CompiledModel, visibility: str) -> str | None:
        """Write a target_link_options command, if any link options were requested.

        Args:
            target: The target whose link options to list.
            visibility: The CMake visibility keyword to use.

        Returns:
            The command text, or None when the target has no link options.
        """
        if not target.link_options:
            return None
        lines = [f"target_link_options({target.name} {visibility}"]
        lines.extend(f"    {self._link_option_line(options)}" for options in target.link_options)
        lines.append(")")
        return "\n".join(lines)

    def _pch_block(self, target: CompiledModel, visibility: str) -> str | None:
        """Write a target_precompile_headers command, if any headers were requested.

        Args:
            target: The target whose pch headers to list.
            visibility: The CMake visibility keyword to use.

        Returns:
            The command text, or None when the target has no pch headers.
        """
        if not target.pch_headers:
            return None
        lines = [f"target_precompile_headers({target.name} {visibility}"]
        lines.extend(f"    {_pch_token(header)}" for header in target.pch_headers)
        lines.append(")")
        return "\n".join(lines)

    def _unity_block(self, target: CompiledModel) -> str | None:
        """Write the UNITY_BUILD target property, if a unity build was requested.

        Args:
            target: The target to check.

        Returns:
            The set_target_properties command text, or None when unity
            builds were not requested.
        """
        if not target.unity:
            return None
        return f"set_target_properties({target.name} PROPERTIES UNITY_BUILD ON)"

    def _include_dirs_block(self, target: LibraryModel, visibility: str) -> str:
        """Write a target_include_directories command for public headers.

        Args:
            target: The library whose public include dirs to list.
            visibility: The CMake visibility keyword to use.

        Returns:
            The command text, with BUILD_INTERFACE guards on every path.
        """
        lines = [f"target_include_directories({target.name} {visibility}"]
        lines.extend(
            # The BUILD_INTERFACE guard keeps the path out of any future
            # install/export usage of this target.
            f"    $<BUILD_INTERFACE:${{CMAKE_CURRENT_SOURCE_DIR}}/{directory.as_posix()}>"
            for directory in sorted(target.public_include_dirs)
        )
        lines.append(")")
        return "\n".join(lines)

    def _export_header_block(self, target: LibraryModel) -> str:
        """Write export-macro generation for a shared library.

        generate_export_header writes <name>_export.h with the correct
        __declspec/visibility macros; consumers find it via the binary dir.

        Args:
            target: The shared library to generate the export header for.

        Returns:
            The command text.
        """
        return (
            f"generate_export_header({target.name})\n"
            f"target_include_directories({target.name} PUBLIC\n"
            f"    $<BUILD_INTERFACE:${{CMAKE_CURRENT_BINARY_DIR}}>\n"
            f")"
        )

    def _settings_blocks(
        self, target: CompiledModel, visibility: str, *, warnings: bool = True
    ) -> list[str]:
        """Emit the settings shared by all target kinds.

        Args:
            target: The target whose defines, options, and links to emit.
            visibility: The CMake visibility keyword for defines and options.
            warnings: Whether the project warning preset applies (it does
                not for INTERFACE targets, which compile nothing).

        Returns:
            Zero or more command blocks, in skeleton order.
        """
        blocks: list[str] = []
        if target.defines:
            blocks.append(self._defines_block(target, visibility))
        option_lines = []
        if warnings:
            option_lines.extend(self._warning_option_lines())
        option_lines.extend(
            self._compile_option_line(options) for options in target.compile_options
        )
        if option_lines:
            lines = [f"target_compile_options({target.name} {visibility}"]
            lines.extend(f"    {line}" for line in option_lines)
            lines.append(")")
            blocks.append("\n".join(lines))
        blocks.extend(
            block
            for block in (
                self._link_options_block(target, visibility),
                self._pch_block(target, visibility),
                self._unity_block(target),
            )
            if block is not None
        )
        if warnings:
            blocks.extend(self._sanitize_blocks(target, visibility))
        if target.links:
            blocks.append(self._links_block(target))
        if target.raw_cmake:
            blocks.append(self._raw_cmake_block(target))
        return blocks

    def _raw_cmake_block(self, target: CompiledModel) -> str:
        """Emit a target's raw_cmake snippets verbatim, fenced by their origin.

        The escape hatch: snippets are written exactly as given, in the order
        added, after everything CMakeless generates for the target, so they
        can override any property set above.

        Args:
            target: The compiled target whose raw snippets to emit.

        Returns:
            The fenced block of verbatim snippets.
        """
        fence = f"# raw_cmake from {self._model.source_script} for target '{target.name}':"
        return "\n".join((fence, *target.raw_cmake))

    def _sanitize_blocks(self, target: CompiledModel, visibility: str) -> list[str]:
        """Emit a target's sanitizer flags, compile and link always paired.

        Combines the target's own sanitize list (unconditional) with the
        preset-selectable sanitizers (guarded by the cache variable), so
        every compiled target honors both.

        Args:
            target: The compiled target to sanitize.
            visibility: The CMake visibility keyword to use.

        Returns:
            Zero to three command blocks: an MSVC rejection for unsupported
            requests, then the compile options, then the link options.
        """
        static_compile, static_link = static_sanitize_lines(target.sanitize)
        preset_compile, preset_link = preset_sanitize_lines(preset_sanitizer_union(self._model))
        compile_lines = [*static_compile, *preset_compile]
        link_lines = [*static_link, *preset_link]
        blocks: list[str] = []
        unsupported = sorted(set(target.sanitize) - MSVC_SUPPORTED_SANITIZERS)
        if unsupported:
            listing = ", ".join(unsupported)
            blocks.append(
                f"if(MSVC)\n"
                f"    message(FATAL_ERROR \"Target '{target.name}' requests sanitizers "
                f"MSVC does not support: {listing}. Build with Clang or GCC, or drop "
                f'them from sanitize in {self._model.source_script}.")\n'
                f"endif()"
            )
        for command, lines in (
            ("target_compile_options", compile_lines),
            ("target_link_options", link_lines),
        ):
            if lines:
                rendered = [f"{command}({target.name} {visibility}"]
                rendered.extend(f"    {line}" for line in lines)
                rendered.append(")")
                blocks.append("\n".join(rendered))
        return blocks

    def _install_sections(self) -> list[str]:
        """Emit every install rule plus the export set that ships them.

        Returns:
            One section per installed target (sorted by name), then the
            export/Config.cmake section; empty without install rules.
        """
        if not self._model.installs:
            return []
        sections = [
            self._visit_install(install)
            for install in sorted(self._model.installs, key=lambda rule: rule.target)
        ]
        sections.append(self._export_section())
        return sections

    def _visit_install(self, install: InstallModel) -> str:
        """Emit one install rule: the target, and its headers when asked.

        Args:
            install: The install rule to emit.

        Returns:
            The rule's complete section text.
        """
        lines = [
            f"install(TARGETS {install.target}",
            f"    EXPORT {self._model.name}Targets",
            "    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}",
            "    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}",
            "    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}",
        ]
        if install.headers:
            # INCLUDES DESTINATION teaches the exported target where its
            # headers land, replacing the BUILD_INTERFACE-only build path.
            lines.append("    INCLUDES DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}")
        lines.append(")")
        blocks = ["\n".join(lines)]
        if install.headers:
            blocks.extend(self._header_install_blocks(install.target))
        return "\n\n".join(blocks)

    def _header_install_blocks(self, target_name: str) -> list[str]:
        """Emit the header installs for one installed library.

        Args:
            target_name: The installed target's name.

        Returns:
            One install command per public header directory, plus the
            generated export header for shared libraries; empty when the
            target is not a library of this project.
        """
        library = next(
            (candidate for candidate in self._model.libraries if candidate.name == target_name),
            None,
        )
        if library is None:
            return []
        blocks = [
            f"install(DIRECTORY {directory.as_posix()}/ DESTINATION ${{CMAKE_INSTALL_INCLUDEDIR}})"
            for directory in sorted(library.public_include_dirs)
        ]
        if library.kind is LibraryKind.SHARED:
            blocks.append(
                f"install(FILES ${{CMAKE_CURRENT_BINARY_DIR}}/{library.name}_export.h "
                f"DESTINATION ${{CMAKE_INSTALL_INCLUDEDIR}})"
            )
        return blocks

    def _export_section(self) -> str:
        """Emit the export set and Config.cmake generation for find_package.

        Returns:
            The complete export section: install(EXPORT), the version and
            config files, and their installation.
        """
        name = self._model.name
        destination = f"${{CMAKE_INSTALL_LIBDIR}}/cmake/{name}"
        return (
            f"install(EXPORT {name}Targets\n"
            f"    FILE {name}Targets.cmake\n"
            f"    NAMESPACE {name}::\n"
            f"    DESTINATION {destination}\n"
            f")\n"
            f"\n"
            f"include(CMakePackageConfigHelpers)\n"
            f"\n"
            f"configure_package_config_file(\n"
            f"    ${{CMAKE_CURRENT_SOURCE_DIR}}/cmake/{name}Config.cmake.in\n"
            f"    ${{CMAKE_CURRENT_BINARY_DIR}}/{name}Config.cmake\n"
            f"    INSTALL_DESTINATION {destination}\n"
            f")\n"
            f"\n"
            f"write_basic_package_version_file(\n"
            f"    ${{CMAKE_CURRENT_BINARY_DIR}}/{name}ConfigVersion.cmake\n"
            f"    VERSION ${{PROJECT_VERSION}}\n"
            f"    COMPATIBILITY SameMajorVersion\n"
            f")\n"
            f"\n"
            f"install(FILES\n"
            f"    ${{CMAKE_CURRENT_BINARY_DIR}}/{name}Config.cmake\n"
            f"    ${{CMAKE_CURRENT_BINARY_DIR}}/{name}ConfigVersion.cmake\n"
            f"    DESTINATION {destination}\n"
            f")"
        )

    def _cpack_section(self) -> list[str]:
        """Emit the CPack configuration for the requested package formats.

        Returns:
            The settings block and the include(CPack) that must come last;
            empty when packaging was not requested.
        """
        if not self._model.package_formats:
            return []
        generators = ";".join(
            CPACK_GENERATOR_BY_FORMAT[format_name]
            for format_name in sorted(self._model.package_formats)
        )
        lines = [
            f"set(CPACK_PACKAGE_NAME {self._model.name})",
            f"set(CPACK_PACKAGE_VERSION {self._model.version})",
        ]
        if "deb" in self._model.package_formats:
            # Debian packages refuse to build without a maintainer contact.
            lines.append(f'set(CPACK_PACKAGE_CONTACT "{self._model.name} maintainers")')
        lines.append(f'set(CPACK_GENERATOR "{generators}")')
        return ["\n".join(lines), "include(CPack)"]

    def _defines_block(self, target: CompiledModel, visibility: str) -> str:
        """Write a target_compile_definitions command with sorted defines.

        Args:
            target: The target whose defines to list.
            visibility: The CMake visibility keyword to use.

        Returns:
            The command text.
        """
        lines = [f"target_compile_definitions({target.name} {visibility}"]
        for define in sorted(target.defines, key=lambda define: define.name):
            token = define.name if define.value is None else f"{define.name}={define.value}"
            lines.append(f"    {guarded(token, define.when)}")
        lines.append(")")
        return "\n".join(lines)

    def _warning_option_lines(self) -> list[str]:
        """Translate the project warning preset into per-compiler flags.

        Returns:
            Generator-expression-guarded flag lines; empty for "default".
        """
        if self._model.warnings == "strict":
            msvc_flags, other_flags = _STRICT_WARNINGS_MSVC, _STRICT_WARNINGS_OTHER
        elif self._model.warnings == "none":
            msvc_flags, other_flags = _NO_WARNINGS_MSVC, _NO_WARNINGS_OTHER
        else:
            return []
        return [
            f"$<$<CXX_COMPILER_ID:MSVC>:{';'.join(msvc_flags)}>",
            f"$<$<NOT:$<CXX_COMPILER_ID:MSVC>>:{';'.join(other_flags)}>",
        ]

    def _compile_option_line(self, options: CompileOptionsModel) -> str:
        """Render one compile_options() call as a single flag line.

        Args:
            options: The flags and their optional When guard.

        Returns:
            The flags joined for CMake, wrapped in a generator expression
            when guarded.
        """
        return guarded(";".join(options.flags), options.when)

    def _link_option_line(self, options: LinkOptionsModel) -> str:
        """Render one link_options() call as a single flag line.

        Args:
            options: The flags and their optional When guard.

        Returns:
            The flags joined for CMake, wrapped in a generator expression
            when guarded.
        """
        return guarded(";".join(options.flags), options.when)

    def _links_block(self, target: CompiledModel) -> str:
        """Write a target_link_libraries command with explicit visibility.

        Args:
            target: The target whose link edges to emit.

        Returns:
            The command text; header-only libraries use INTERFACE because
            it is the only correct visibility for them.
        """
        public = sorted(link.target for link in target.links if link.public)
        private = sorted(link.target for link in target.links if not link.public)
        is_interface = isinstance(target, LibraryModel) and target.kind is LibraryKind.HEADER_ONLY
        lines = [f"target_link_libraries({target.name}"]
        if is_interface:
            lines.extend(f"    INTERFACE {name}" for name in sorted({*public, *private}))
        else:
            lines.extend(f"    PUBLIC {name}" for name in public)
            lines.extend(f"    PRIVATE {name}" for name in private)
        lines.append(")")
        return "\n".join(lines)


def _tree_has_tests(model: ProjectModel) -> bool:
    """Tell whether a project or any of its subprojects defines tests.

    enable_testing() must appear in every directory on the path from the
    top-level CMakeLists down to the tests for ctest to find them.

    Args:
        model: The project node to inspect.

    Returns:
        True when tests exist anywhere in the subtree.
    """
    if model.tests:
        return True
    return any(_tree_has_tests(subproject.project) for subproject in model.subprojects)


def _max_python_version(versions: Iterable[str]) -> str:
    """Combine several "MAJOR.MINOR" floors into the single highest one.

    find_package(Python X.Y ...) accepts X.Y or newer, never an exact match,
    so when a project has several Python modules with different
    python_version= floors, requiring the highest one satisfies every module
    at once; no other module's requirement is violated by asking for more.

    Args:
        versions: One "MAJOR.MINOR" string per Python module in the project.

    Returns:
        The highest version, formatted "MAJOR.MINOR".
    """
    return max(versions, key=lambda version: tuple(int(part) for part in version.split(".")))


def _resolved_cmake_name(dependency: DependencyModel) -> str:
    """Read a dependency's find_package name, which resolution guarantees.

    Args:
        dependency: The dependency being emitted.

    Returns:
        The find_package name.
    """
    assert dependency.cmake_name is not None, "the emitter requires a resolved model"
    return dependency.cmake_name


def _pch_token(header: str) -> str:
    """Render one precompiled header for target_precompile_headers().

    Args:
        header: An angle-bracket system header ("<vector>") or a
            project-relative path.

    Returns:
        The header verbatim when it is already angle-bracketed, else quoted.
    """
    if header.startswith("<") and header.endswith(">"):
        return header
    return f'"{header}"'


def _components_suffix(dependency: DependencyModel) -> str:
    """Render a dependency's components for a find_package call.

    Args:
        dependency: The dependency being emitted.

    Returns:
        A " COMPONENTS ..." suffix, or an empty string without components.
    """
    if not dependency.components:
        return ""
    return " COMPONENTS " + " ".join(sorted(dependency.components))
