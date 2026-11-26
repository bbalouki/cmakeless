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

from cmakeless._constants import (
    CMAKE_MINIMUM_VERSION,
    CMAKELESS_SYSTEM_NAME_VAR,
    CMAKELESS_SYSTEM_PROCESSOR_VAR,
    CPS_MINIMUM_VERSION,
    CXX_MODULES_MINIMUM_VERSION,
)
from cmakeless.emitter.flags import needs_x86_detection, syntax_preamble
from cmakeless.emitter.install_emitter import (
    PKG_CONFIG_TEMPLATE_SUFFIX,
    SIGNING_SCRIPT_NAME,
    cpack_sections,
    install_sections,
    pkg_config_template,
    signing_script,
)
from cmakeless.emitter.instrumentation import instrumentation_section
from cmakeless.emitter.presets_emitter import emit_presets
from cmakeless.emitter.quoting import quote_argument
from cmakeless.emitter.sanitizers import (
    MSVC_SUPPORTED_SANITIZERS,
    SANITIZE_CACHE_VARIABLE,
    preset_sanitize_lines,
    preset_sanitizer_union,
    static_sanitize_lines,
)
from cmakeless.emitter.target_settings import (
    c_std_block,
    compile_option_lines,
    define_lines,
    effective_profile,
    effective_warnings,
    extension_blocks,
    ipo_block,
    link_option_lines,
    post_build_block,
    property_block,
    qt_resource_block,
)
from cmakeless.emitter.tests_emitter import framework_includes, registration_block
from cmakeless.emitter.toolchain_emitter import emit_toolchain
from cmakeless.emitter.when_emitter import guarded, render_if_condition
from cmakeless.model.languages import languages_for
from cmakeless.model.nodes import (
    BUILD_TYPE_BY_OPTIMIZE,
    CommandModel,
    CompiledModel,
    CompileOptionsModel,
    CustomTargetModel,
    DependencyModel,
    ExecutableModel,
    LibraryKind,
    LibraryModel,
    LinkKind,
    LinkModel,
    LinkOptionsModel,
    ModuleKind,
    ModuleModel,
    OptionModel,
    OptionType,
    ProjectModel,
    PythonModuleModel,
    TestModel,
)

# add_library() keywords by library kind; header-only libraries take their
# own INTERFACE path and never reach this table.
_LIBRARY_KEYWORD_BY_KIND: dict[LibraryKind, str] = {
    LibraryKind.STATIC: "STATIC",
    LibraryKind.SHARED: "SHARED",
    LibraryKind.OBJECT: "OBJECT",
    LibraryKind.PLUGIN: "MODULE",
}

# The Apple platforms a framework link is valid on; everywhere else it
# renders to nothing, so a cross-platform description needs no guard.
_APPLE_PLATFORMS = "$<PLATFORM_ID:Darwin,iOS,tvOS,watchOS,visionOS>"

# The policy floor set around each fetched dependency, so packages that still
# declare cmake_minimum_required() below 3.5 configure under CMake 4.
_LEGACY_POLICY_FLOOR = "3.5"


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


def emit_target_section(model: ProjectModel, name: str, *, tool_version: str) -> str | None:
    """Generate exactly the CMake one target contributes, for 'cmakeless explain'.

    Args:
        model: The frozen project that owns the target.
        name: The target name.
        tool_version: The cmakeless version, as for emit_cmakelists().

    Returns:
        The target's section text, or None when this node has no such target.
    """
    return _CMakeListsVisitor(model, tool_version).target_section(name)


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
        if toolchain.file is None or toolchain.variables:
            files[Path("cmake") / "toolchains" / f"{toolchain.name}.cmake"] = emit_toolchain(
                toolchain, tool_version=tool_version, source_script=model.source_script
            )
    if model.installs:
        files[Path("cmake") / f"{model.name}Config.cmake.in"] = _config_template(model.name)
        if model.export.pkg_config:
            template = Path("cmake") / f"{model.name}{PKG_CONFIG_TEMPLATE_SUFFIX}"
            files[template] = pkg_config_template(model)
        if model.signing is not None:
            files[Path("cmake") / SIGNING_SCRIPT_NAME] = signing_script(model)
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
        self._languages = languages_for(
            source
            for target in model.all_targets()
            for source in (*target.sources, *target.cxx_modules)
        )

    def emit(self) -> str:
        """Walk the project and assemble the full file.

        Returns:
            The complete CMakeLists.txt text, newline-terminated.
        """
        sections = [
            self._header(),
            self._preamble(),
            self._reflection_preamble(),
            *self._toolchain_checks(),
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
        sections.extend(self._platform_packages())
        sections.extend(
            self._visit_dependency(dependency)
            for dependency in sorted(self._model.dependencies, key=lambda dep: dep.name)
        )
        sections.extend(self._subproject_sections())
        sections.extend(self._command_sections())
        sections.extend(self._target_sections())
        sections.extend(self._custom_target_sections())
        sections.extend(install_sections(self._model))
        sections.extend(cpack_sections(self._model))
        return "\n\n".join(sections) + "\n"

    def target_section(self, name: str) -> str | None:
        """Emit the section of one target, found by name across every kind.

        Args:
            name: The target name.

        Returns:
            The section text, or None when no target of this node has it.
        """
        visitors = (
            (self._model.libraries, self._visit_library),
            (self._model.executables, self._visit_executable),
            (self._model.python_modules, self._visit_python_module),
            (self._model.tests, self._visit_test),
            (self._model.fuzz_targets, self._visit_fuzz_target),
        )
        for targets, visit in visitors:
            for target in targets:
                if target.name == name:
                    return visit(target)  # type: ignore[arg-type]
        return None

    def _toolchain_checks(self) -> list[str]:
        """Emit the one-time checks some flag lines and properties depend on.

        Returns:
            The syntax preamble, plus CheckPIESupported and CheckIPOSupported
            when a profile asks for PIE or link-time optimization; empty for
            a project that needs none, so its output is unchanged.
        """
        targets = self._model.all_targets()
        profiles = [effective_profile(target, self._model) for target in targets]
        sections: list[str] = []
        if self._needs_syntax_preamble():
            x86 = any(needs_x86_detection(profile) for profile in profiles)
            sections.append(syntax_preamble(x86=x86))
        if any(profile is not None and profile.position_independent for profile in profiles):
            sections.append(
                "# Link executables as PIE where the toolchain supports it.\n"
                "include(CheckPIESupported)\n"
                "check_pie_supported()"
            )
        if any(profile is not None and profile.ipo_release for profile in profiles):
            sections.append(
                "include(CheckIPOSupported)\n"
                "check_ipo_supported(RESULT CMAKELESS_IPO_SUPPORTED OUTPUT CMAKELESS_IPO_OUTPUT)"
            )
        sections.extend(instrumentation_section(self._model))
        return sections

    def _needs_syntax_preamble(self) -> bool:
        """Tell whether any flag line in this file refers to the syntax variables.

        Returns:
            True when a warning preset, sanitizer, CPU target, profile, or
            instrumentation is active anywhere in this project node.
        """
        if preset_sanitizer_union(self._model) or self._model.instrumentation:
            return True
        for target in self._model.all_targets():
            compiles = not (
                isinstance(target, LibraryModel) and target.kind is LibraryKind.HEADER_ONLY
            )
            settings = (
                effective_warnings(target, self._model) != "default",
                bool(target.sanitize),
                target.properties.cpu is not None,
                effective_profile(target, self._model) is not None,
                target.properties.map_file,
                target.properties.linker_script is not None,
            )
            if compiles and any(settings):
                return True
        return False

    def _platform_packages(self) -> list[str]:
        """Find the platform packages typed links rely on: Threads and Qt.

        Returns:
            One find_package() section per package in use, in a fixed order.
        """
        sections: list[str] = []
        targets = self._model.all_targets()
        if any(link.kind is LinkKind.THREADS for target in targets for link in target.links):
            sections.append(
                "# The platform thread library: pthread on POSIX, nothing extra on Windows.\n"
                "find_package(Threads REQUIRED)"
            )
        components_by_major: dict[int, set[str]] = {}
        for target in targets:
            if target.properties.qt is not None:
                qt = target.properties.qt
                components_by_major.setdefault(qt.major, set()).update(qt.components)
        sections.extend(
            f"find_package(Qt{major} REQUIRED COMPONENTS {' '.join(sorted(components))})"
            for major, components in sorted(components_by_major.items())
        )
        return sections

    def _subproject_sections(self) -> list[str]:
        """Emit every add_subdirectory(), guarded by its configure-time condition.

        Returns:
            One section per subproject, sorted by directory.
        """
        sections: list[str] = []
        for node in sorted(self._model.subprojects, key=lambda node: node.directory.as_posix()):
            call = f"add_subdirectory({node.directory.as_posix()})"
            if node.when is None:
                sections.append(call)
            else:
                sections.append(f"if{render_if_condition(node.when)}\n    {call}\nendif()")
        return sections

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
        sections.extend(
            self._visit_fuzz_target(target)
            for target in sorted(self._model.fuzz_targets, key=lambda target: target.name)
        )
        sections.extend(framework_includes(self._model))
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

    def _command_line(self, argv: Iterable[str], *, depends: tuple[Path, ...]) -> str:
        """Render an argument vector as one quoted, parser-safe COMMAND line.

        Every argument is quoted individually, so a Windows path full of
        backslashes, a directory with a space in it, or an argument
        containing a quote survives CMake's parser intact and still arrives
        at the tool as exactly one argument.

        Args:
            argv: The command's arguments, as the user wrote them.
            depends: The command's declared dependencies, for anchoring.

        Returns:
            The space-separated, individually quoted argument list.
        """
        anchored = (self._anchor_command_token(token, depends=depends) for token in argv)
        return " ".join(quote_argument(token) for token in anchored)

    def _visit_command(self, command: CommandModel) -> str:
        """Emit one build-time step as add_custom_command(OUTPUT ...).

        Args:
            command: The command to emit.

        Returns:
            The command's complete section text.
        """
        argv = self._command_line(command.command, depends=command.depends)
        lines = ["add_custom_command(", "    OUTPUT"]
        lines.extend(f"        {output.as_posix()}" for output in command.outputs)
        lines.append("    COMMAND " + argv)
        if command.depends:
            depends = " ".join(depend.as_posix() for depend in sorted(command.depends))
            lines.append(f"    DEPENDS {depends}")
        if command.comment is not None:
            lines.append(f"    COMMENT {quote_argument(command.comment)}")
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
        argv = self._command_line(target.command, depends=target.depends)
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
        if any(
            library.kind in (LibraryKind.SHARED, LibraryKind.PLUGIN)
            for library in self._model.libraries
        ):
            includes.append("include(GenerateExportHeader)")
        if self._model.dependencies and self._model.package_manager == "auto":
            includes.append("include(FetchContent)")
        if self._model.installs or self._model.install_files:
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
            f"cmake_minimum_required(VERSION {self._required_cmake_version()})\n"
            f"\n"
            f"project({self._model.name}\n"
            f"    VERSION {self._model.version}\n"
            f"    LANGUAGES {' '.join(self._languages)}\n"
            f")"
        )

    def _required_cmake_version(self) -> str:
        """Pick the CMake version floor this particular project needs.

        Raised only for a project that declares C++20 module interfaces or
        exports a CPS file, which need a newer CMake than everything else the
        emitter writes; a project that uses neither keeps the lower floor.

        Returns:
            The version string for cmake_minimum_required.
        """
        if self._model.export.cps and self._model.installs:
            return CPS_MINIMUM_VERSION
        if any(target.cxx_modules for target in self._model.all_targets()):
            return CXX_MODULES_MINIMUM_VERSION
        return CMAKE_MINIMUM_VERSION

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
        sections.extend(self._position_independent_code())
        return sections

    def _position_independent_code(self) -> list[str]:
        """Build everything position-independent when the project links a shared object.

        This is the one directory-level variable the emitter sets on purpose.
        Our own targets already get the POSITION_INDEPENDENT_CODE property
        set on them individually, but a dependency built through
        FetchContent is a subproject we do not own and cannot set properties
        on. Without this, a static dependency compiles without -fPIC and
        then fails to link into a shared library or Python module on
        platforms where that matters, which is every ELF platform.

        Returns:
            One section when the project builds something shared, so a
            project of plain static libraries and executables is unchanged.
        """
        builds_shared = bool(self._model.python_modules) or any(
            library.kind in (LibraryKind.SHARED, LibraryKind.PLUGIN)
            for library in self._model.libraries
        )
        if not builds_shared:
            return []
        return [
            "# This project links a shared object, so everything it links into\n"
            "# one, including dependencies built as subprojects, must be\n"
            "# position-independent.\n"
            "set(CMAKE_POSITION_INDEPENDENT_CODE ON)"
        ]

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
        assert dependency.link_targets, "validation guarantees imported targets"
        fetch = self._fetch_lines(dependency)
        if self._model.supply_chain == "strict" and dependency.name not in self._model.allow_system:
            return (
                f"# {dependency.name} {dependency.version}: pinned source fetch only "
                f'(supply_chain="strict").\n'
                f"if(NOT TARGET {dependency.link_targets[0]})\n"
                f"{fetch}\n"
                f"endif()"
            )
        return (
            f"# {dependency.name} {dependency.version}: system package when "
            f"available, pinned source fetch otherwise.\n"
            f"find_package({name} {dependency.version} QUIET"
            f"{_components_suffix(dependency)})\n"
            f"if(NOT {name}_FOUND AND NOT TARGET {dependency.link_targets[0]})\n"
            f"{fetch}\n"
            f"endif()"
        )

    def _fetch_lines(self, dependency: DependencyModel) -> str:
        """Write the FetchContent declaration for one pinned dependency.

        SYSTEM keeps a dependency's own headers from tripping this project's
        warning flags. The policy floor exists because CMake 4 refuses any
        cmake_minimum_required() below 3.5, which many older packages still
        declare; it only raises floors below 3.5, and CMake 3 ignores it.

        Args:
            dependency: The resolved dependency, fetch pin included.

        Returns:
            The indented declare-and-make-available lines.
        """
        assert dependency.url is not None, "the auto strategy must pin a URL"
        assert dependency.sha256 is not None, "the auto strategy must pin a hash"
        return (
            f"    FetchContent_Declare({dependency.name}\n"
            f"        URL {dependency.url}\n"
            f"        URL_HASH SHA256={dependency.sha256}\n"
            f"        SYSTEM\n"
            f"    )\n"
            f"    set(CMAKE_POLICY_VERSION_MINIMUM {_LEGACY_POLICY_FLOOR})\n"
            f"    FetchContent_MakeAvailable({dependency.name})\n"
            f"    unset(CMAKE_POLICY_VERSION_MINIMUM)"
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
        blocks.extend(self._input_blocks(target, "PRIVATE"))
        private_include_dirs = self._private_include_dirs_block(target, "PRIVATE")
        if private_include_dirs is not None:
            blocks.append(private_include_dirs)
        blocks.append(
            f"target_compile_features({target.name} PRIVATE cxx_std_{self._cpp_std_for(target)})"
        )
        blocks.extend(self._settings_blocks(target, "PRIVATE"))
        return "\n\n".join(blocks)

    def _visit_fuzz_target(self, target: ExecutableModel) -> str:
        """Emit one libFuzzer target, left out of the default build.

        GCC ships no libFuzzer, so a fuzz target would fail to link there;
        excluding it from "all" keeps every normal build green, and
        'cmakeless fuzz' builds it by name.

        Args:
            target: The fuzz target to emit.

        Returns:
            The target's complete section text.
        """
        return (
            f"{self._visit_executable(target)}\n\n"
            f"set_target_properties({target.name} PROPERTIES EXCLUDE_FROM_ALL ON)"
        )

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
        blocks.extend(self._input_blocks(target, "PRIVATE"))
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
        blocks = [f"add_library({target.name} {_LIBRARY_KEYWORD_BY_KIND[target.kind]})"]
        blocks.extend(self._input_blocks(target, "PRIVATE"))
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
        if target.kind in (LibraryKind.SHARED, LibraryKind.PLUGIN):
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
        blocks.extend(self._input_blocks(target, "PRIVATE"))
        private_include_dirs = self._private_include_dirs_block(target, "PRIVATE")
        if private_include_dirs is not None:
            blocks.append(private_include_dirs)
        blocks.append(
            f"target_compile_features({target.name} PRIVATE cxx_std_{self._cpp_std_for(target)})"
        )
        blocks.extend(self._settings_blocks(target, "PRIVATE"))
        if self._links_shared_library(target):
            blocks.append(self._runtime_dll_copy_block(target))
        blocks.append(registration_block(target))
        return "\n\n".join(blocks)

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
            if library.kind in (LibraryKind.SHARED, LibraryKind.PLUGIN):
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

    def _input_blocks(self, target: CompiledModel, visibility: str) -> list[str]:
        """Write the blocks declaring everything a target compiles.

        Args:
            target: The target whose inputs to declare.
            visibility: The CMake visibility keyword for ordinary sources;
                module interfaces always get their own, since consumers
                import them.

        Returns:
            The source block, the module interface block, or both, in the
            order CMake reads most naturally.
        """
        candidates = (
            self._sources_block(target, visibility),
            self._cxx_modules_block(target, self._cxx_modules_visibility(target)),
        )
        return [block for block in candidates if block is not None]

    def _sources_block(self, target: CompiledModel, visibility: str) -> str | None:
        """Write a target_sources command with sorted sources.

        Args:
            target: The target whose sources to list.
            visibility: The CMake visibility keyword to use.

        Returns:
            The command text, or None for a target built only from module
            interfaces.
        """
        if not target.sources:
            return None
        lines = [f"target_sources({target.name} {visibility}"]
        lines.extend(f"    {source.as_posix()}" for source in sorted(target.sources))
        lines.append(")")
        return "\n".join(lines)

    def _cxx_modules_block(self, target: CompiledModel, visibility: str) -> str | None:
        """Write the target_sources command declaring C++20 module interfaces.

        Module interfaces live in their own FILE_SET so CMake scans them and
        orders compilation by the import graph, which a plain source list
        does not do.

        Args:
            target: The target whose module interfaces to list.
            visibility: The CMake visibility keyword to use.

        Returns:
            The command text, or None when the target declares no modules.
        """
        if not target.cxx_modules:
            return None
        lines = [f"target_sources({target.name} {visibility}", "    FILE_SET CXX_MODULES FILES"]
        lines.extend(f"        {module.as_posix()}" for module in sorted(target.cxx_modules))
        lines.append(")")
        return "\n".join(lines)

    def _cxx_modules_visibility(self, target: CompiledModel) -> str:
        """Pick the visibility a target's module interfaces are declared with.

        Args:
            target: The target declaring module interfaces.

        Returns:
            PUBLIC for a library, whose consumers must be able to import the
            module, and PRIVATE for anything nothing links against.
        """
        return "PUBLIC" if isinstance(target, LibraryModel) else "PRIVATE"

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

    def _link_options_block(
        self, target: CompiledModel, visibility: str, *, extra: bool
    ) -> str | None:
        """Write a target_link_options command, if any link options apply.

        Args:
            target: The target whose link options to list.
            visibility: The CMake visibility keyword to use.
            extra: True to include the CPU, profile, map-file, and
                linker-script lines alongside the user's own options.

        Returns:
            The command text, or None when the target has no link options.
        """
        lines = link_option_lines(target, self._model, self._languages) if extra else []
        lines.extend(self._link_option_line(options) for options in target.link_options)
        if not lines:
            return None
        return _command_block("target_link_options", target.name, visibility, lines)

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

    def _lint_block(self, target: CompiledModel) -> str | None:
        """Write the CXX_CLANG_TIDY/CXX_INCLUDE_WHAT_YOU_USE target properties.

        A target's own lint() call always wins; otherwise the project's
        project.lint() setting applies, mirroring how _cpp_std_for()
        resolves a target's own cpp_std against the project's.

        Args:
            target: The target whose lint settings to resolve and emit.

        Returns:
            The set_target_properties command text, or None when neither
            tool resolves to a non-empty command for this target.
        """
        clang_tidy = (
            target.clang_tidy if target.clang_tidy is not None else self._model.lint_clang_tidy
        )
        iwyu = target.iwyu if target.iwyu is not None else self._model.lint_iwyu
        properties: list[str] = []
        if clang_tidy:
            properties.append(f'CXX_CLANG_TIDY "{";".join(clang_tidy)}"')
        if iwyu:
            properties.append(f'CXX_INCLUDE_WHAT_YOU_USE "{";".join(iwyu)}"')
        if self._model.lint_cppcheck:
            properties.append(f'CXX_CPPCHECK "{";".join(self._model.lint_cppcheck)}"')
        if not properties:
            return None
        lines = [f"set_target_properties({target.name} PROPERTIES"]
        lines.extend(f"    {property_line}" for property_line in properties)
        lines.append(")")
        return "\n".join(lines)

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
            warnings: Whether compile-affecting settings apply (they do not
                for INTERFACE targets, which compile nothing).

        Returns:
            Zero or more command blocks, in skeleton order.
        """
        blocks: list[str] = []
        defines = self._defines_block(target, visibility, profile=warnings)
        if defines is not None:
            blocks.append(defines)
        compile_options = self._compile_options_block(target, visibility, extra=warnings)
        if compile_options is not None:
            blocks.append(compile_options)
        blocks.extend(
            block
            for block in (
                self._link_options_block(target, visibility, extra=warnings),
                self._pch_block(target, visibility),
                self._unity_block(target),
                c_std_block(target, self._model, visibility) if warnings else None,
                qt_resource_block(target),
            )
            if block is not None
        )
        if warnings:
            blocks.extend(self._warned_blocks(target, visibility))
        blocks.extend(self._property_blocks(target, warnings=warnings))
        if target.links:
            blocks.append(self._links_block(target))
        blocks.extend(extension_blocks(target))
        if target.raw_cmake:
            blocks.append(self._raw_cmake_block(target))
        return blocks

    def _compile_options_block(
        self, target: CompiledModel, visibility: str, *, extra: bool
    ) -> str | None:
        """Write a target_compile_options command, if any compile options apply.

        Args:
            target: The target whose compile options to list.
            visibility: The CMake visibility keyword to use.
            extra: True to include the warning, CPU, profile, and
                instrumentation lines ahead of the user's own options.

        Returns:
            The command text, or None when nothing applies.
        """
        lines = compile_option_lines(target, self._model, self._languages) if extra else []
        lines.extend(self._compile_option_line(options) for options in target.compile_options)
        if not lines:
            return None
        return _command_block("target_compile_options", target.name, visibility, lines)

    def _property_blocks(self, target: CompiledModel, *, warnings: bool) -> list[str]:
        """Emit the property, link-time-optimization, and post-build blocks.

        Args:
            target: The compiled target.
            warnings: False for INTERFACE targets, which have no properties
                of their own to set.

        Returns:
            Zero to three blocks.
        """
        if not warnings:
            return []
        candidates = (
            property_block(target, self._model),
            ipo_block(target, self._model),
            post_build_block(target),
        )
        return [block for block in candidates if block is not None]

    def _warned_blocks(self, target: CompiledModel, visibility: str) -> list[str]:
        """Emit the settings that do not apply to warning-free INTERFACE targets.

        Args:
            target: The target whose sanitizer and lint settings to emit.
            visibility: The CMake visibility keyword to use.

        Returns:
            The sanitizer blocks, then the lint block if either resolves to
            a non-empty command.
        """
        blocks = list(self._sanitize_blocks(target, visibility))
        lint_block = self._lint_block(target)
        if lint_block is not None:
            blocks.append(lint_block)
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
        static_compile, static_link = static_sanitize_lines(target.sanitize, self._languages)
        preset_compile, preset_link = preset_sanitize_lines(
            preset_sanitizer_union(self._model), self._languages
        )
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

    def _defines_block(
        self, target: CompiledModel, visibility: str, *, profile: bool
    ) -> str | None:
        """Write a target_compile_definitions command with sorted defines.

        Args:
            target: The target whose defines to list.
            visibility: The CMake visibility keyword to use.
            profile: True to append the target's profile definitions.

        Returns:
            The command text, or None when there is nothing to define.
        """
        lines = []
        for define in sorted(target.defines, key=lambda define: define.name):
            token = define.name if define.value is None else f"{define.name}={define.value}"
            lines.append(guarded(token, define.when))
        if profile:
            lines.extend(define_lines(target, self._model))
        if not lines:
            return None
        return _command_block("target_compile_definitions", target.name, visibility, lines)

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
        public = sorted(_link_item(link) for link in target.links if link.public)
        private = sorted(_link_item(link) for link in target.links if not link.public)
        is_interface = isinstance(target, LibraryModel) and target.kind is LibraryKind.HEADER_ONLY
        lines = [f"target_link_libraries({target.name}"]
        if is_interface:
            lines.extend(f"    INTERFACE {name}" for name in sorted({*public, *private}))
        else:
            lines.extend(f"    PUBLIC {name}" for name in public)
            lines.extend(f"    PRIVATE {name}" for name in private)
        lines.append(")")
        return "\n".join(lines)


def _command_block(command: str, target: str, visibility: str, lines: list[str]) -> str:
    """Render one target_* command with one item per indented line.

    Args:
        command: The CMake command name, for example target_compile_options.
        target: The target name.
        visibility: The visibility keyword.
        lines: The items, already rendered.

    Returns:
        The command text.
    """
    body = "\n".join(f"    {line}" for line in lines)
    return f"{command}({target} {visibility}\n{body}\n)"


def _link_item(link: LinkModel) -> str:
    """Render one link edge as a target_link_libraries item.

    Args:
        link: The link edge.

    Returns:
        The item, an Apple framework wrapped so it is a no-op elsewhere, and
        any When guard applied last.
    """
    item = link.target
    if link.kind is LinkKind.FRAMEWORK:
        item = f"$<{_APPLE_PLATFORMS}:$<LINK_LIBRARY:FRAMEWORK,{link.target}>>"
    return guarded(item, link.when)


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
