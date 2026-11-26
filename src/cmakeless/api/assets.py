"""Shader and asset pipelines, expressed as ordinary custom build steps.

Every shader becomes one add_command() step, so a change to one .hlsl file
rebuilds only that shader, and the dependency graph stays validated in
Python exactly like any other generated file.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path, PurePosixPath

from cmakeless.errors import ConfigurationError

# Each compiler's argument vector, given (source, output, profile), and the
# extension of what it writes.
type ShaderArgv = Callable[[str, str, str | None], list[str]]

_SPIRV = ".spv"


def _dxc(source: str, output: str, profile: str | None) -> list[str]:
    """Build a DirectX Shader Compiler invocation.

    Args:
        source: The shader source.
        output: The compiled object to write.
        profile: The target profile, for example "ps_6_6".

    Returns:
        The argument vector.
    """
    assert profile is not None, "validated by shader_steps()"
    return ["dxc", "-T", profile, "-E", "main", "-Fo", output, source]


def _glslc(source: str, output: str, profile: str | None) -> list[str]:
    """Build a glslc (shaderc) invocation; the stage comes from the extension.

    Args:
        source: The shader source.
        output: The SPIR-V module to write.
        profile: An optional --target-env, for example "vulkan1.3".

    Returns:
        The argument vector.
    """
    target = [f"--target-env={profile}"] if profile is not None else []
    return ["glslc", *target, source, "-o", output]


def _glslang(source: str, output: str, profile: str | None) -> list[str]:
    """Build a glslangValidator invocation.

    Args:
        source: The shader source.
        output: The SPIR-V module to write.
        profile: An optional --target-env.

    Returns:
        The argument vector.
    """
    target = ["--target-env", profile] if profile is not None else []
    return ["glslangValidator", "-V", *target, source, "-o", output]


def _slangc(source: str, output: str, profile: str | None) -> list[str]:
    """Build a slangc invocation targeting SPIR-V.

    Args:
        source: The shader source.
        output: The SPIR-V module to write.
        profile: An optional -profile, for example "glsl_460".

    Returns:
        The argument vector.
    """
    selected = ["-profile", profile] if profile is not None else []
    return ["slangc", source, *selected, "-target", "spirv", "-o", output]


SHADER_COMPILERS: dict[str, tuple[ShaderArgv, str]] = {
    "dxc": (_dxc, ".cso"),
    "glslc": (_glslc, _SPIRV),
    "glslangValidator": (_glslang, _SPIRV),
    "slangc": (_slangc, _SPIRV),
}


def shader_steps(
    sources: Sequence[Path], *, compiler: str, profile: str | None, output: str
) -> list[tuple[str, list[str], str]]:
    """Plan one compile step per shader source.

    Args:
        sources: Project-relative shader sources, globs already expanded.
        compiler: "dxc", "glslc", "glslangValidator", or "slangc".
        profile: The compiler's target profile; required for dxc.
        output: The project-relative directory compiled shaders land in.

    Returns:
        (output file, argument vector, source) triples, sorted by source.

    Raises:
        ConfigurationError: When the compiler is unknown, dxc has no
            profile, or nothing matched.
    """
    if compiler not in SHADER_COMPILERS:
        known = ", ".join(repr(name) for name in sorted(SHADER_COMPILERS))
        raise ConfigurationError(f"Unknown shader compiler {compiler!r}. Pick one of: {known}.")
    if compiler == "dxc" and profile is None:
        raise ConfigurationError(
            'add_shaders(compiler="dxc") needs a profile, for example profile="ps_6_6".'
        )
    if not sources:
        raise ConfigurationError("add_shaders() matched no shader sources; check the pattern.")
    build_argv, extension = SHADER_COMPILERS[compiler]
    steps = []
    for source in sorted(sources):
        compiled = PurePosixPath(output) / (source.name + extension)
        steps.append(
            (
                str(compiled),
                build_argv(source.as_posix(), str(compiled), profile),
                source.as_posix(),
            )
        )
    return steps
