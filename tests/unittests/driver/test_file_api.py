# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""The CMake File API reader: query writing and reply parsing."""

from __future__ import annotations

import json
from pathlib import Path

from cmakeless.driver.file_api import (
    CMakeInfo,
    CompilerInfo,
    TargetInfo,
    read_cmake_info,
    read_reply,
    write_query,
)

_QUERY_KINDS = {"codemodel", "cache", "toolchains"}


def _target_entry(reply: Path, target: dict[str, object]) -> dict[str, object]:
    """Write one target's detail file and return its codemodel entry."""
    file_name = f"target-{target['name']}.json"
    (reply / file_name).write_text(json.dumps(target), encoding="utf-8")
    return {"name": target["name"], "jsonFile": file_name}


def _write_object(
    reply: Path, responses: list[dict[str, object]], *, kind: str, body: dict[str, object]
) -> None:
    """Write one File API reply object and record its response entry."""
    file_name = f"{kind}-a.json"
    (reply / file_name).write_text(json.dumps({"kind": kind, **body}), encoding="utf-8")
    responses.append({"kind": kind, "jsonFile": file_name})


def _write_reply(
    build_dir: Path,
    targets: list[dict[str, object]],
    *,
    abstract_targets: list[dict[str, object]] | None = None,
    cache_entries: list[dict[str, object]] | None = None,
    toolchains: list[dict[str, object]] | None = None,
    generator_name: str = "Ninja",
    multi_config: bool = False,
) -> None:
    """Write a minimal File API reply describing the given targets, cache, and toolchains.

    Args:
        build_dir: The build directory to populate.
        targets: The per-target detail objects to store as compiled targets.
        abstract_targets: Per-target detail objects to store as abstract
            targets (interface/alias/imported), or None for none.
        cache_entries: Cache entries for the "cache" object, or None to omit
            that object from the reply entirely.
        toolchains: Toolchain entries for the "toolchains" object, or None
            to omit that object from the reply entirely.
        generator_name: The index file's reported generator name.
        multi_config: The index file's reported multi-config flag.
    """
    reply = build_dir / ".cmake" / "api" / "v1" / "reply"
    reply.mkdir(parents=True, exist_ok=True)
    entries = [_target_entry(reply, target) for target in targets]
    abstract_entries = [_target_entry(reply, target) for target in abstract_targets or []]
    responses: list[dict[str, object]] = []
    configuration = {"name": "", "targets": entries, "abstractTargets": abstract_entries}
    _write_object(reply, responses, kind="codemodel", body={"configurations": [configuration]})
    if cache_entries is not None:
        _write_object(reply, responses, kind="cache", body={"entries": cache_entries})
    if toolchains is not None:
        _write_object(reply, responses, kind="toolchains", body={"toolchains": toolchains})
    index = {
        "cmake": {"generator": {"name": generator_name, "multiConfig": multi_config}},
        "reply": {"client-cmakeless": {"query.json": {"responses": responses}}},
    }
    (reply / "index-1.json").write_text(json.dumps(index), encoding="utf-8")


def test_write_query_requests_codemodel_cache_and_toolchains(tmp_path: Path) -> None:
    """Write query requests codemodel, cache, and toolchains in one query."""
    write_query(tmp_path)
    query = tmp_path / ".cmake" / "api" / "v1" / "query" / "client-cmakeless" / "query.json"
    assert query.is_file()
    requests = json.loads(query.read_text(encoding="utf-8"))["requests"]
    assert {request["kind"] for request in requests} == _QUERY_KINDS
    assert requests[0]["kind"] == "codemodel"


def test_read_reply_returns_targets_sorted_by_name(tmp_path: Path) -> None:
    """Read reply returns targets sorted by name."""
    _write_reply(
        tmp_path,
        [
            {"name": "zeta", "type": "EXECUTABLE", "artifacts": [{"path": "zeta"}]},
            {"name": "alpha", "type": "STATIC_LIBRARY", "sources": [{"path": "src/a.cpp"}]},
        ],
    )
    infos = read_reply(tmp_path)
    assert [info.name for info in infos] == ["alpha", "zeta"]
    assert infos[0] == TargetInfo(name="alpha", type="STATIC_LIBRARY", sources=(Path("src/a.cpp"),))
    assert infos[1].artifacts == (Path("zeta"),)


def test_read_reply_extracts_dependency_target_names(tmp_path: Path) -> None:
    """Read reply extracts dependency target names."""
    _write_reply(
        tmp_path,
        [{"name": "app", "type": "EXECUTABLE", "dependencies": [{"id": "engine::@a1b2"}]}],
    )
    (info,) = read_reply(tmp_path)
    assert info.dependencies == ("engine",)


def test_read_reply_without_a_reply_returns_empty(tmp_path: Path) -> None:
    """Read reply without a reply returns empty."""
    assert read_reply(tmp_path) == ()


def test_read_reply_includes_abstract_targets(tmp_path: Path) -> None:
    """Read reply includes abstract targets: interface, alias, and imported.

    Regression test: codemodel v2 lists targets with no build rules (an
    INTERFACE library, for example) under "abstractTargets", separate from
    "targets"; project.include()'s best-effort target discovery depends on
    both being read.
    """
    _write_reply(
        tmp_path,
        [{"name": "app", "type": "EXECUTABLE"}],
        abstract_targets=[{"name": "reflected_iface", "type": "INTERFACE_LIBRARY"}],
    )
    infos = read_reply(tmp_path)
    assert [info.name for info in infos] == ["app", "reflected_iface"]


def test_read_cmake_info_reads_generator_and_multi_config(tmp_path: Path) -> None:
    """Read cmake info reads generator and multi config from the index file."""
    _write_reply(tmp_path, [], generator_name="Ninja Multi-Config", multi_config=True)
    info = read_cmake_info(tmp_path)
    assert info.generator == "Ninja Multi-Config"
    assert info.multi_config is True


def test_read_cmake_info_reads_compilers_from_toolchains(tmp_path: Path) -> None:
    """Read cmake info reads compilers from toolchains."""
    _write_reply(
        tmp_path,
        [],
        toolchains=[
            {"language": "CXX", "compiler": {"id": "GNU", "version": "13.2.0"}},
            {"language": "C", "compiler": {"id": "GNU", "version": "13.2.0"}},
        ],
    )
    info = read_cmake_info(tmp_path)
    assert info.compilers == (
        CompilerInfo(language="CXX", compiler_id="GNU", compiler_version="13.2.0"),
        CompilerInfo(language="C", compiler_id="GNU", compiler_version="13.2.0"),
    )


def test_read_cmake_info_reads_system_name_and_processor_from_internal_cache(
    tmp_path: Path,
) -> None:
    """Read cmake info reads system name/processor from the CMAKELESS_SYSTEM_* cache entries."""
    _write_reply(
        tmp_path,
        [],
        cache_entries=[
            {"name": "CMAKELESS_SYSTEM_NAME", "value": "Linux", "type": "INTERNAL"},
            {"name": "CMAKELESS_SYSTEM_PROCESSOR", "value": "x86_64", "type": "INTERNAL"},
        ],
    )
    info = read_cmake_info(tmp_path)
    assert info.system_name == "Linux"
    assert info.system_processor == "x86_64"


def test_read_cmake_info_excludes_internal_vars_but_keeps_other_cache_entries(
    tmp_path: Path,
) -> None:
    """Read cmake info excludes the internal system vars from options but keeps the rest."""
    _write_reply(
        tmp_path,
        [],
        cache_entries=[
            {"name": "CMAKELESS_SYSTEM_NAME", "value": "Linux", "type": "INTERNAL"},
            {"name": "MYLIB_BUILD_GUI", "value": "ON", "type": "BOOL"},
        ],
    )
    info = read_cmake_info(tmp_path)
    assert info.options == (("MYLIB_BUILD_GUI", "ON"),)


def test_read_cmake_info_without_a_reply_returns_blank_info(tmp_path: Path) -> None:
    """Read cmake info without a reply returns blank info, not an error."""
    assert read_cmake_info(tmp_path) == CMakeInfo(
        generator="", multi_config=False, system_name="", system_processor=""
    )
