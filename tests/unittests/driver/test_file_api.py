# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""The CMake File API reader: query writing and reply parsing."""

from __future__ import annotations

import json
from pathlib import Path

from cmakeless.driver.file_api import TargetInfo, read_reply, write_query


def _write_reply(build_dir: Path, targets: list[dict[str, object]]) -> None:
    """Write a minimal codemodel reply describing the given targets.

    Args:
        build_dir: The build directory to populate.
        targets: The per-target detail objects to store.
    """
    reply = build_dir / ".cmake" / "api" / "v1" / "reply"
    reply.mkdir(parents=True)
    entries = []
    for target in targets:
        file_name = f"target-{target['name']}.json"
        (reply / file_name).write_text(json.dumps(target), encoding="utf-8")
        entries.append({"name": target["name"], "jsonFile": file_name})
    codemodel = {"kind": "codemodel", "configurations": [{"name": "", "targets": entries}]}
    (reply / "codemodel-v2-a.json").write_text(json.dumps(codemodel), encoding="utf-8")
    responses = [{"kind": "codemodel", "jsonFile": "codemodel-v2-a.json"}]
    index = {"reply": {"client-cmakeless": {"query.json": {"responses": responses}}}}
    (reply / "index-1.json").write_text(json.dumps(index), encoding="utf-8")


def test_write_query_creates_the_codemodel_request(tmp_path: Path) -> None:
    """Write query creates the codemodel request."""
    write_query(tmp_path)
    query = tmp_path / ".cmake" / "api" / "v1" / "query" / "client-cmakeless" / "query.json"
    assert query.is_file()
    assert json.loads(query.read_text(encoding="utf-8"))["requests"][0]["kind"] == "codemodel"


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
