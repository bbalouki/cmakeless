"""The Phase 1 CLI verbs: configure, clean, and init."""

from __future__ import annotations

from pathlib import Path

import pytest

from cmakeless.cli import main

BUILD_PY = """\
from cmakeless import Project

project = Project("demo", cpp_std=20)
project.add_executable("demo", sources=["src/main.cpp"])
project.build()
"""


@pytest.fixture
def demo_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.cpp").write_text(
        "auto main() -> int { return 0; }\n", encoding="utf-8"
    )
    (tmp_path / "build.py").write_text(BUILD_PY, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_clean_removes_build_directory(demo_project: Path) -> None:
    build_dir = demo_project / "build"
    build_dir.mkdir()
    (build_dir / "junk.txt").write_text("junk", encoding="utf-8")
    assert main(["clean"]) == 0
    assert not build_dir.exists()


def test_clean_on_clean_tree_is_fine(demo_project: Path) -> None:
    assert main(["clean"]) == 0


def test_init_scaffolds_a_buildable_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--name", "shiny"]) == 0
    build_py = (tmp_path / "build.py").read_text(encoding="utf-8")
    assert 'Project("shiny"' in build_py
    assert (tmp_path / "src" / "main.cpp").is_file()
    assert "build/" in (tmp_path / ".gitignore").read_text(encoding="utf-8")


def test_init_refuses_to_overwrite(demo_project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["init"]) == 1
    assert "refusing" in capsys.readouterr().err


def test_init_default_name_comes_from_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_dir = tmp_path / "my-tool"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    assert main(["init"]) == 0
    assert 'Project("my-tool"' in (project_dir / "build.py").read_text(encoding="utf-8")
