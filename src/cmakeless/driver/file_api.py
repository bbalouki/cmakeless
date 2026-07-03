"""CMake File API: the configured build as structured Python objects.

Before configure the driver writes a codemodel-v2 query; after configure
CMake leaves a JSON reply the driver reads into TargetInfo objects, so
project.targets_info() returns the configured build without scraping text.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# The File API lives under the build tree; a named client keeps our query
# and its reply namespaced away from any other tool's.
_QUERY_CLIENT = "client-cmakeless"
_API_DIR = Path(".cmake") / "api" / "v1"


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


def write_query(build_dir: Path) -> None:
    """Write the codemodel-v2 query CMake answers during configure.

    Args:
        build_dir: The build directory configure will run into.
    """
    query_dir = build_dir / _API_DIR / "query" / _QUERY_CLIENT
    query_dir.mkdir(parents=True, exist_ok=True)
    query = {"requests": [{"kind": "codemodel", "version": 2}]}
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
    codemodel = _load_codemodel(reply_dir)
    if codemodel is None:
        return ()
    configurations: list[dict[str, Any]] = codemodel.get("configurations") or [{}]
    targets: list[dict[str, str]] = configurations[0].get("targets", [])
    infos = [_read_target(reply_dir, entry) for entry in targets]
    return tuple(sorted(infos, key=lambda info: info.name))


def _load_codemodel(reply_dir: Path) -> dict[str, Any] | None:
    """Load the codemodel object the newest index points at.

    Args:
        reply_dir: The File API reply directory.

    Returns:
        The parsed codemodel mapping, or None when absent.
    """
    indexes = sorted(reply_dir.glob("index-*.json"))
    if not indexes:
        return None
    index: dict[str, Any] = json.loads(indexes[-1].read_text(encoding="utf-8"))
    client = index.get("reply", {}).get(_QUERY_CLIENT, {})
    responses = client.get("query.json", {}).get("responses", [])
    for response in responses:
        if response.get("kind") == "codemodel":
            model: dict[str, Any] = json.loads(
                (reply_dir / response["jsonFile"]).read_text(encoding="utf-8")
            )
            return model
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
