# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""CMake File API: the configured build as structured Python objects.

Before configure the driver writes a query for three File API object kinds;
after configure CMake leaves a JSON reply the driver reads into TargetInfo
(codemodel) and CMakeInfo (cache, toolchains) objects, so project.targets_info()
and project.cmake_info() return the configured build without scraping text.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cmakeless._constants import CMAKELESS_SYSTEM_NAME_VAR, CMAKELESS_SYSTEM_PROCESSOR_VAR

# The File API lives under the build tree; a named client keeps our query
# and its reply namespaced away from any other tool's.
_QUERY_CLIENT = "client-cmakeless"
_API_DIR = Path(".cmake") / "api" / "v1"

# Every File API object kind cmake_info()/targets_info() together need,
# requested unconditionally in one query: the cost is negligible, and it
# avoids needing to know upfront which of the two verbs a project will call.
_REQUESTS: tuple[dict[str, Any], ...] = (
    {"kind": "codemodel", "version": 2},
    {"kind": "cache", "version": 2},
    {"kind": "toolchains", "version": 1},
)


@dataclass(frozen=True, slots=True)
class TargetInfo:
    """One target from the configured build, as CMake reported it.

    Attributes:
        name: The target name.
        type: The CMake target type ("EXECUTABLE", "STATIC_LIBRARY",
            "SHARED_LIBRARY", "MODULE_LIBRARY", "INTERFACE_LIBRARY", ...).
        artifacts: Build-relative paths of the files the target produces.
        sources: Source-relative paths of the target's source files.
        dependencies: Names of the other targets this one depends on.
    """

    name: str
    type: str
    artifacts: tuple[Path, ...] = ()
    sources: tuple[Path, ...] = ()
    dependencies: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class CompilerInfo:
    """One language's resolved compiler, as CMake's File API reported it.

    Attributes:
        language: The CMake language name ("CXX", "C", ...).
        compiler_id: The compiler identifier (for example "GNU", "Clang",
            "MSVC"), or "" when CMake could not determine one.
        compiler_version: The compiler's version string, or "" when unknown.
    """

    language: str
    compiler_id: str = ""
    compiler_version: str = ""


@dataclass(frozen=True, slots=True)
class CMakeInfo:
    """The resolved generator, compilers, system, and cache after configure.

    Attributes:
        generator: The CMake generator name (for example "Ninja"), or "" when
            no reply exists yet.
        multi_config: True for a multi-config generator (Visual Studio,
            Xcode, Ninja Multi-Config).
        system_name: CMAKE_SYSTEM_NAME as CMake resolved it (for example
            "Windows", "Linux", "Darwin").
        system_processor: CMAKE_SYSTEM_PROCESSOR as CMake resolved it.
        compilers: One CompilerInfo per language CMake configured.
        options: Every other cache entry, (name, value) pairs, value always
            a raw string as this layer reports it; Project.cmake_info()
            filters this to its own declared project.option()s and coerces
            each value to its declared bool/int/str type, since the driver
            layer does not know about option types. The field itself is
            typed as the coerced union so cmake_info() can hand back a
            CMakeInfo with either shape.
    """

    generator: str
    multi_config: bool
    system_name: str
    system_processor: str
    compilers: tuple[CompilerInfo, ...] = ()
    options: tuple[tuple[str, bool | int | str], ...] = ()


def write_query(build_dir: Path) -> None:
    """Write the File API query CMake answers during configure.

    Args:
        build_dir: The build directory configure will run into.
    """
    query_dir = build_dir / _API_DIR / "query" / _QUERY_CLIENT
    query_dir.mkdir(parents=True, exist_ok=True)
    query = {"requests": list(_REQUESTS)}
    (query_dir / "query.json").write_text(json.dumps(query, indent=2) + "\n", encoding="utf-8")


def read_reply(build_dir: Path) -> tuple[TargetInfo, ...]:
    """Read the codemodel reply CMake left after configure.

    Args:
        build_dir: The build directory that was configured.

    Returns:
        One TargetInfo per target in the first configuration, sorted by
        name; empty when no reply exists (configure never ran).
    """
    reply_dir = build_dir / _API_DIR / "reply"
    index = _load_index(reply_dir)
    codemodel = None if index is None else _load_reply_object(reply_dir, index, kind="codemodel")
    if codemodel is None:
        return ()
    configurations: list[dict[str, Any]] = codemodel.get("configurations") or [{}]
    configuration = configurations[0]
    # Interface, alias, and imported targets carry no build rules, so
    # codemodel v2 lists them separately from compiled ones; both name a
    # real target consumers can link against.
    targets: list[dict[str, str]] = [
        *configuration.get("targets", []),
        *configuration.get("abstractTargets", []),
    ]
    infos = [_read_target(reply_dir, entry) for entry in targets]
    return tuple(sorted(infos, key=lambda info: info.name))


def read_cmake_info(build_dir: Path) -> CMakeInfo:
    """Read the resolved generator, compilers, system, and cache entries.

    Configure must have run first (it writes the query CMake answers).

    Args:
        build_dir: The build directory that was configured.

    Returns:
        The resolved CMakeInfo; blank/empty fields when no reply exists.
    """
    reply_dir = build_dir / _API_DIR / "reply"
    index = _load_index(reply_dir)
    if index is None:
        return CMakeInfo(generator="", multi_config=False, system_name="", system_processor="")
    generator_info = index.get("cmake", {}).get("generator", {})
    cache = _load_reply_object(reply_dir, index, kind="cache")
    entries = {entry["name"]: entry["value"] for entry in (cache or {}).get("entries", [])}
    toolchains = _load_reply_object(reply_dir, index, kind="toolchains")
    compilers = tuple(
        CompilerInfo(
            language=toolchain.get("language", ""),
            compiler_id=toolchain.get("compiler", {}).get("id", ""),
            compiler_version=toolchain.get("compiler", {}).get("version", ""),
        )
        for toolchain in (toolchains or {}).get("toolchains", [])
    )
    options = tuple(
        sorted(
            (name, value)
            for name, value in entries.items()
            if name not in (CMAKELESS_SYSTEM_NAME_VAR, CMAKELESS_SYSTEM_PROCESSOR_VAR)
        )
    )
    return CMakeInfo(
        generator=generator_info.get("name", ""),
        multi_config=bool(generator_info.get("multiConfig", False)),
        system_name=entries.get(CMAKELESS_SYSTEM_NAME_VAR, ""),
        system_processor=entries.get(CMAKELESS_SYSTEM_PROCESSOR_VAR, ""),
        compilers=compilers,
        options=options,
    )


def _load_index(reply_dir: Path) -> dict[str, Any] | None:
    """Load the newest File API index file.

    Args:
        reply_dir: The File API reply directory.

    Returns:
        The parsed index mapping, or None when no reply exists.
    """
    indexes = sorted(reply_dir.glob("index-*.json"))
    if not indexes:
        return None
    result: dict[str, Any] = json.loads(indexes[-1].read_text(encoding="utf-8"))
    return result


def _load_reply_object(
    reply_dir: Path, index: dict[str, Any], *, kind: str
) -> dict[str, Any] | None:
    """Load one response object CMake answered our query with.

    Args:
        reply_dir: The File API reply directory.
        index: The parsed index file (see _load_index).
        kind: The File API object kind to find ("codemodel", "cache", or
            "toolchains").

    Returns:
        The parsed object, or None when CMake did not answer this kind (an
        older CMake, or the object errored).
    """
    client = index.get("reply", {}).get(_QUERY_CLIENT, {})
    responses = client.get("query.json", {}).get("responses", [])
    for response in responses:
        if response.get("kind") != kind or "jsonFile" not in response:
            continue
        result: dict[str, Any] = json.loads(
            (reply_dir / response["jsonFile"]).read_text(encoding="utf-8")
        )
        return result
    return None


def _read_target(reply_dir: Path, entry: dict[str, str]) -> TargetInfo:
    """Load one target's detail file into a TargetInfo.

    Args:
        reply_dir: The File API reply directory.
        entry: The codemodel's target entry (name and jsonFile).

    Returns:
        The target's structured information.
    """
    target: dict[str, Any] = json.loads((reply_dir / entry["jsonFile"]).read_text(encoding="utf-8"))
    artifacts = tuple(Path(item["path"]) for item in target.get("artifacts", []))
    sources = tuple(Path(item["path"]) for item in target.get("sources", []))
    dependencies = tuple(str(item["id"]).split("::@")[0] for item in target.get("dependencies", []))
    return TargetInfo(
        name=target["name"],
        type=target.get("type", "UNKNOWN"),
        artifacts=artifacts,
        sources=sources,
        dependencies=dependencies,
    )
