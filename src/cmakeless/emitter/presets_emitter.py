# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

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
    if preset.inherits is not None:
        rendered["inherits"] = preset.inherits
    if preset.env:
        rendered["environment"] = dict(preset.env)
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
    for name, value in preset.options:
        variables[name] = _stringify_option_value(value)
    return variables


def _stringify_option_value(value: bool | int | str) -> str:
    """Render a preset option override as a CMake cache-variable string.

    Args:
        value: The override value.

    Returns:
        "ON"/"OFF" for a bool, else the value's plain string form.
    """
    if isinstance(value, bool):
        return "ON" if value else "OFF"
    return str(value)


def _toolchain_file(toolchain: ToolchainModel) -> str:
    """Resolve a toolchain to the file path its presets configure with.

    Args:
        toolchain: The referenced toolchain.

    Returns:
        A wrapped file's own path (absolute paths as-is, relative ones
        anchored at ${sourceDir}) when it has no extra variables; otherwise
        the generated cmake/toolchains/ file (plain generated toolchains,
        and wrapped ones that needed variables seeded before their include()).
    """
    if toolchain.file is not None and not toolchain.variables:
        if toolchain.file.is_absolute():
            return toolchain.file.as_posix()
        return f"${{sourceDir}}/{toolchain.file.as_posix()}"
    return f"${{sourceDir}}/cmake/toolchains/{toolchain.name}.cmake"
