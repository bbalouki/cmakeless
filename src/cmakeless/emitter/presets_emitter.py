"""Model to CMakePresets.json: named configurations IDEs pick up natively.

Each PresetModel becomes a configure/build/test preset triple. The configure
preset owns the out-of-source build directory (build/<name>) and the cache
variables; sanitizers ride through the CMAKELESS_SANITIZE cache variable the
CMakeLists emitter translates into per-compiler flags.
"""

from __future__ import annotations

import json

from cmakeless.model.nodes import (
    BUILD_TYPE_BY_OPTIMIZE,
    PresetModel,
    ProjectModel,
    ToolchainModel,
)

# CMakePresets.json schema version 6 is the newest CMake 3.25 understands.
PRESETS_SCHEMA_VERSION = 6


def emit_presets(model: ProjectModel) -> str:
    """Generate the complete CMakePresets.json for one project node.

    Args:
        model: The frozen project whose presets to emit.

    Returns:
        The full JSON text, newline-terminated and deterministic (keys are
        written in a fixed order, presets in declaration order).
    """
    toolchains_by_name = {toolchain.name: toolchain for toolchain in model.toolchains}
    document = {
        "version": PRESETS_SCHEMA_VERSION,
        "configurePresets": [
            _configure_preset(preset, toolchains_by_name) for preset in model.presets
        ],
        "buildPresets": [
            {"name": preset.name, "configurePreset": preset.name} for preset in model.presets
        ],
        "testPresets": [
            {
                "name": preset.name,
                "configurePreset": preset.name,
                "output": {"outputOnFailure": True},
            }
            for preset in model.presets
        ],
    }
    return json.dumps(document, indent=2) + "\n"


def _configure_preset(
    preset: PresetModel, toolchains_by_name: dict[str, ToolchainModel]
) -> dict[str, object]:
    """Render one configure preset.

    Args:
        preset: The preset to render.
        toolchains_by_name: The project's registered toolchains, so a
            toolchain reference resolves to its file path.

    Returns:
        The configure preset as a JSON-ready mapping.
    """
    rendered: dict[str, object] = {
        "name": preset.name,
        "displayName": preset.name,
        "binaryDir": f"${{sourceDir}}/build/{preset.name}",
        "cacheVariables": _cache_variables(preset),
    }
    if preset.toolchain is not None:
        rendered["toolchainFile"] = _toolchain_file(toolchains_by_name[preset.toolchain])
    return rendered


def _cache_variables(preset: PresetModel) -> dict[str, str]:
    """Translate a preset's settings into CMake cache variables.

    Args:
        preset: The preset to translate.

    Returns:
        Cache variables in a fixed key order.
    """
    variables = {"CMAKE_BUILD_TYPE": BUILD_TYPE_BY_OPTIMIZE[preset.optimize]}
    if preset.lto:
        variables["CMAKE_INTERPROCEDURAL_OPTIMIZATION"] = "ON"
    if preset.sanitize:
        variables["CMAKELESS_SANITIZE"] = ";".join(preset.sanitize)
    return variables


def _toolchain_file(toolchain: ToolchainModel) -> str:
    """Resolve a toolchain to the file path its presets configure with.

    Args:
        toolchain: The referenced toolchain.

    Returns:
        The path, anchored at ${sourceDir}; generated toolchains live
        under cmake/toolchains/.
    """
    if toolchain.file is not None:
        return f"${{sourceDir}}/{toolchain.file.as_posix()}"
    return f"${{sourceDir}}/cmake/toolchains/{toolchain.name}.cmake"
