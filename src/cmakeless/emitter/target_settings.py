"""Per-target settings beyond sources and links: properties, profiles, CPUs.

Every function here is a pure function of one target and its project, so
the visitor composes them without growing a method per setting.
"""

from __future__ import annotations

from collections.abc import Sequence

from cmakeless.emitter.flags import (
    cpu_lines,
    linker_script_line,
    map_file_lines,
    profile_compile_lines,
    profile_define_lines,
    profile_link_lines,
    warning_lines,
)
from cmakeless.emitter.instrumentation import (
    instrumentation_compile_lines,
    instrumentation_link_lines,
)
from cmakeless.emitter.quoting import quote_argument
from cmakeless.model.languages import language_of
from cmakeless.model.nodes import (
    CompiledModel,
    ExecutableModel,
    LibraryKind,
    LibraryModel,
    ProjectModel,
)
from cmakeless.model.properties import ProfileModel

# MSVC_RUNTIME_LIBRARY values; the Debug suffix keeps debug and release
# objects from mixing runtimes, the classic LNK2038 mismatch.
_MSVC_RUNTIME_BY_NAME: dict[str, str] = {
    "static": "MultiThreaded$<$<CONFIG:Debug>:Debug>",
    "dynamic": "MultiThreaded$<$<CONFIG:Debug>:Debug>DLL",
}


def effective_profile(target: CompiledModel, model: ProjectModel) -> ProfileModel | None:
    """The profile a target builds with: its own, else the project's.

    Args:
        target: The compiled target.
        model: The project that owns it.

    Returns:
        The profile, or None when neither sets one.
    """
    return target.properties.profile if target.properties.profile is not None else model.profile


def effective_warnings(target: CompiledModel, model: ProjectModel) -> str:
    """The warning preset a target builds with: its own, else the project's.

    Args:
        target: The compiled target.
        model: The project that owns it.

    Returns:
        The preset name.
    """
    return target.properties.warnings or model.warnings


def compile_option_lines(
    target: CompiledModel, model: ProjectModel, languages: Sequence[str]
) -> list[str]:
    """Collect the warning, CPU, and profile compile flags for one target.

    Args:
        target: The compiled target.
        model: The project that owns it.
        languages: The languages enabled in the project node.

    Returns:
        Flag lines in a fixed order: warnings, CPU, profile, then the run's
        instrumentation.
    """
    lines = warning_lines(effective_warnings(target, model), languages)
    if target.properties.cpu is not None:
        lines.extend(cpu_lines(target.properties.cpu, languages)[0])
    profile = effective_profile(target, model)
    if profile is not None:
        lines.extend(profile_compile_lines(profile, languages))
    lines.extend(instrumentation_compile_lines(model, languages))
    return lines


def link_option_lines(
    target: CompiledModel, model: ProjectModel, languages: Sequence[str]
) -> list[str]:
    """Collect the CPU, profile, map-file, and linker-script link flags.

    Args:
        target: The compiled target.
        model: The project that owns it.
        languages: The languages enabled in the project node.

    Returns:
        Link flag lines; empty for a target that is never linked itself.
    """
    if not links_itself(target):
        return []
    lines: list[str] = []
    if target.properties.cpu is not None:
        lines.extend(cpu_lines(target.properties.cpu, languages)[1])
    profile = effective_profile(target, model)
    if profile is not None:
        lines.extend(profile_link_lines(profile))
    if target.properties.map_file or (profile is not None and profile.map_file):
        lines.extend(map_file_lines(target.name))
    script = target.properties.linker_script
    if script is not None:
        lines.append(linker_script_line(f"${{CMAKE_CURRENT_SOURCE_DIR}}/{script.as_posix()}"))
    lines.extend(instrumentation_link_lines(model))
    return lines


def define_lines(target: CompiledModel, model: ProjectModel) -> list[str]:
    """Collect the preprocessor definitions a target's profile contributes.

    Args:
        target: The compiled target.
        model: The project that owns it.

    Returns:
        Guarded definition tokens; empty without a profile.
    """
    profile = effective_profile(target, model)
    return profile_define_lines(profile) if profile is not None else []


def links_itself(target: CompiledModel) -> bool:
    """Tell whether a target has its own link step.

    Args:
        target: The compiled target.

    Returns:
        False for static, object, and header-only libraries, which are
        archived or merged into consumers rather than linked.
    """
    if isinstance(target, LibraryModel):
        return target.kind in (LibraryKind.SHARED, LibraryKind.PLUGIN)
    return True


def property_block(target: CompiledModel, model: ProjectModel) -> str | None:
    """Write every simple target property as one set_target_properties call.

    Args:
        target: The compiled target.
        model: The project that owns it.

    Returns:
        The command text, or None when the target sets no such property.
    """
    pairs = _property_pairs(target, model)
    if not pairs:
        return None
    lines = [f"set_target_properties({target.name} PROPERTIES"]
    lines.extend(f"    {name} {value}" for name, value in pairs)
    lines.append(")")
    return "\n".join(lines)


def _property_pairs(target: CompiledModel, model: ProjectModel) -> list[tuple[str, str]]:
    """Collect (property, value) pairs in a fixed, documented order.

    Args:
        target: The compiled target.
        model: The project that owns it.

    Returns:
        Property names with already-quoted values.
    """
    properties = target.properties
    pairs = _output_pairs(target)
    if properties.visibility is not None:
        pairs.extend(
            (
                ("CXX_VISIBILITY_PRESET", properties.visibility),
                ("C_VISIBILITY_PRESET", properties.visibility),
                ("VISIBILITY_INLINES_HIDDEN", "ON" if properties.visibility == "hidden" else "OFF"),
            )
        )
    if properties.gui and isinstance(target, ExecutableModel):
        pairs.extend((("WIN32_EXECUTABLE", "ON"), ("MACOSX_BUNDLE", "ON")))
    if properties.msvc_runtime is not None:
        pairs.append(
            ("MSVC_RUNTIME_LIBRARY", f'"{_MSVC_RUNTIME_BY_NAME[properties.msvc_runtime]}"')
        )
    if properties.cuda_architectures:
        pairs.append(("CUDA_ARCHITECTURES", f'"{";".join(properties.cuda_architectures)}"'))
    pairs.extend(_toolchain_pairs(target, model))
    if properties.qt is not None:
        pairs.extend((("AUTOMOC", "ON"), ("AUTOUIC", "ON"), ("AUTORCC", "ON")))
    if properties.linker_script is not None:
        script = f"${{CMAKE_CURRENT_SOURCE_DIR}}/{properties.linker_script.as_posix()}"
        pairs.append(("LINK_DEPENDS", f'"{script}"'))
    return pairs


def _output_pairs(target: CompiledModel) -> list[tuple[str, str]]:
    """Collect the output-name and ABI-version properties.

    Args:
        target: The compiled target.

    Returns:
        OUTPUT_NAME, VERSION, and SOVERSION pairs, when set.
    """
    properties = target.properties
    pairs: list[tuple[str, str]] = []
    if properties.output_name is not None:
        pairs.append(("OUTPUT_NAME", f'"{properties.output_name}"'))
    if properties.version is not None:
        pairs.append(("VERSION", properties.version))
    if properties.soversion is not None:
        pairs.append(("SOVERSION", properties.soversion))
    return pairs


def _toolchain_pairs(target: CompiledModel, model: ProjectModel) -> list[tuple[str, str]]:
    """Collect the warnings-as-errors and PIE properties.

    Args:
        target: The compiled target.
        model: The project that owns it.

    Returns:
        COMPILE_WARNING_AS_ERROR and POSITION_INDEPENDENT_CODE pairs.
    """
    profile = effective_profile(target, model)
    werror = target.properties.warnings_as_errors
    if werror is None:
        werror = model.warnings_as_errors or (profile is not None and profile.warnings_as_errors)
    pairs: list[tuple[str, str]] = []
    if werror and not _is_header_only(target):
        pairs.append(("COMPILE_WARNING_AS_ERROR", "ON"))
    pie = profile is not None and profile.position_independent
    if pie and isinstance(target, ExecutableModel):
        pairs.append(("POSITION_INDEPENDENT_CODE", "ON"))
    return pairs


def ipo_block(target: CompiledModel, model: ProjectModel) -> str | None:
    """Enable link-time optimization for optimized configs, when supported.

    Args:
        target: The compiled target.
        model: The project that owns it.

    Returns:
        The guarded property block, or None without an IPO profile.
    """
    profile = effective_profile(target, model)
    if profile is None or not profile.ipo_release or _is_header_only(target):
        return None
    return (
        f"if(CMAKELESS_IPO_SUPPORTED)\n"
        f"    set_target_properties({target.name} PROPERTIES\n"
        f"        INTERPROCEDURAL_OPTIMIZATION_RELEASE ON\n"
        f"        INTERPROCEDURAL_OPTIMIZATION_RELWITHDEBINFO ON\n"
        f"        INTERPROCEDURAL_OPTIMIZATION_MINSIZEREL ON\n"
        f"    )\n"
        f"endif()"
    )


def c_std_block(target: CompiledModel, model: ProjectModel, visibility: str) -> str | None:
    """Declare the C standard for a target that compiles C sources.

    Args:
        target: The compiled target.
        model: The project that owns it.
        visibility: The visibility keyword the target's features use.

    Returns:
        The compile-features command, or None when the target has no C
        source or no C standard is set.
    """
    standard = target.properties.c_std if target.properties.c_std is not None else model.c_std
    if standard is None or not any(language_of(source) == "C" for source in target.sources):
        return None
    return f"target_compile_features({target.name} {visibility} c_std_{standard})"


def post_build_block(target: CompiledModel) -> str | None:
    """Run argument vectors after the target links, never through a shell.

    Args:
        target: The compiled target.

    Returns:
        The add_custom_command(TARGET ... POST_BUILD) text, or None.
    """
    if not target.properties.post_build:
        return None
    lines = [f"add_custom_command(TARGET {target.name} POST_BUILD"]
    for argv in target.properties.post_build:
        lines.append("    COMMAND " + " ".join(quote_argument(token) for token in argv))
    lines.extend(("    VERBATIM", ")"))
    return "\n".join(lines)


def extension_blocks(target: CompiledModel) -> list[str]:
    """Emit each plugin extension's snippet, fenced with its origin.

    Args:
        target: The compiled target.

    Returns:
        One fenced block per extension, in the order they were applied.
    """
    return [
        f"# extension {use.name} {use.version} for target '{target.name}':\n{use.snippet}"
        for use in target.properties.extensions
    ]


def qt_resource_block(target: CompiledModel) -> str | None:
    """List a Qt target's .qrc files so AUTORCC compiles them in.

    Args:
        target: The compiled target.

    Returns:
        The target_sources command, or None without resources.
    """
    qt = target.properties.qt
    if qt is None or not qt.resources:
        return None
    lines = [f"target_sources({target.name} PRIVATE"]
    lines.extend(f"    {resource.as_posix()}" for resource in sorted(qt.resources))
    lines.append(")")
    return "\n".join(lines)


def _is_header_only(target: CompiledModel) -> bool:
    """Tell whether a target is an INTERFACE library that compiles nothing.

    Args:
        target: The compiled target.

    Returns:
        True for header-only libraries.
    """
    return isinstance(target, LibraryModel) and target.kind is LibraryKind.HEADER_ONLY
