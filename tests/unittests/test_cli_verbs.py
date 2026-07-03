"""The CLI verbs that execute cmakelessfile.py: configure, clean, lock, and init."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cmakeless.cli import main

BUILD_PY = """\
from cmakeless import Project

project = Project("demo", cpp_std=20)
project.add_executable("demo", sources=["src/main.cpp"])
project.build()
"""

DEPENDENT_BUILD_PY = """\
from cmakeless import Project

project = Project("demo", cpp_std=20)
app = project.add_executable("demo", sources=["src/main.cpp"])
app.depends("fmt/10.2.1")
project.build()
"""


@pytest.fixture
def demo_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A buildable demo project in a temporary working directory."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.cpp").write_text(
        "auto main() -> int { return 0; }\n", encoding="utf-8"
    )
    (tmp_path / "cmakelessfile.py").write_text(BUILD_PY, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_clean_removes_build_directory(demo_project: Path) -> None:
    """Clean removes build directory."""
    build_dir = demo_project / "build"
    build_dir.mkdir()
    (build_dir / "junk.txt").write_text("junk", encoding="utf-8")
    assert main(["clean"]) == 0
    assert not build_dir.exists()


def test_clean_on_clean_tree_is_fine(demo_project: Path) -> None:
    """Clean on clean tree is fine."""
    assert main(["clean"]) == 0


def test_lock_writes_the_lockfile(demo_project: Path) -> None:
    """Lock writes the lockfile."""
    # fmt/10.2.1 carries a curated registry pin, so locking needs no network.
    (demo_project / "cmakelessfile.py").write_text(DEPENDENT_BUILD_PY, encoding="utf-8")
    assert main(["lock"]) == 0
    lock = json.loads((demo_project / "cmakeless.lock").read_text(encoding="utf-8"))
    assert lock["packages"]["fmt"]["version"] == "10.2.1"
    assert lock["packages"]["fmt"]["sha256"]


def test_lock_without_dependencies_writes_nothing(
    demo_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Lock without dependencies writes nothing."""
    assert main(["lock"]) == 0
    assert not (demo_project / "cmakeless.lock").exists()
    assert "No dependencies" in capsys.readouterr().out


PROBE_BUILD_PY = """\
from pathlib import Path

from cmakeless.api import _context

Path("verb.txt").write_text(_context.active_verb(), encoding="utf-8")
Path("preset.txt").write_text(str(_context.active_preset()), encoding="utf-8")
Path("sanitize.txt").write_text(",".join(_context.active_sanitize()), encoding="utf-8")
"""


@pytest.fixture
def probe_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A cmakelessfile.py that records the overrides the CLI activated."""
    (tmp_path / "cmakelessfile.py").write_text(PROBE_BUILD_PY, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize("verb", ["test", "install", "package"])
def test_new_verbs_reach_the_build_script(probe_project: Path, verb: str) -> None:
    """New verbs reach the build script."""
    assert main([verb]) == 0
    assert (probe_project / "verb.txt").read_text(encoding="utf-8") == verb


def test_preset_option_reaches_the_build_script(probe_project: Path) -> None:
    """Preset option reaches the build script."""
    assert main(["build", "--preset", "release"]) == 0
    assert (probe_project / "preset.txt").read_text(encoding="utf-8") == "release"


def test_sanitize_option_is_split_on_commas(probe_project: Path) -> None:
    """Sanitize option is split on commas."""
    assert main(["test", "--sanitize", "address, undefined"]) == 0
    assert (probe_project / "sanitize.txt").read_text(encoding="utf-8") == "address,undefined"


def test_unknown_preset_fails_with_guidance(
    demo_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Unknown preset fails with guidance."""
    assert main(["configure", "--preset", "nope"]) == 1
    assert "add_preset" in capsys.readouterr().err


def test_unknown_sanitizer_fails_at_freeze_time(
    demo_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Unknown sanitizer fails at freeze time."""
    assert main(["test", "--sanitize", "bogus"]) == 1
    assert "bogus" in capsys.readouterr().err


def test_init_scaffolds_a_buildable_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Init scaffolds a buildable layout."""
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--name", "shiny"]) == 0
    build_py = (tmp_path / "cmakelessfile.py").read_text(encoding="utf-8")
    assert 'Project("shiny"' in build_py
    assert (tmp_path / "src" / "main.cpp").is_file()
    assert "build/" in (tmp_path / ".gitignore").read_text(encoding="utf-8")


def test_init_refuses_to_overwrite(demo_project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Init refuses to overwrite."""
    assert main(["init"]) == 1
    assert "refusing" in capsys.readouterr().err


def test_init_default_name_comes_from_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Init default name comes from directory."""
    project_dir = tmp_path / "my-tool"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    assert main(["init"]) == 0
    assert 'Project("my-tool"' in (project_dir / "cmakelessfile.py").read_text(encoding="utf-8")
