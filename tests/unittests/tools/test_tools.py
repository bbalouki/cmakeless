"""Templates, the CMake importer, workspaces, and the explain, diff, and audit verbs."""

from __future__ import annotations

import ast
import shutil
from pathlib import Path

import pytest

from cmakeless import ConfigurationError, Project
from cmakeless.api import _context
from cmakeless.api.workflows import run_workflow
from cmakeless.api.workspace import Workspace
from cmakeless.cli import main
from cmakeless.deps.lockfile import LockedPackage, read_lockfile, write_lockfile
from cmakeless.driver.file_api import TargetDetail
from cmakeless.tools.importer import check_import, collapse_globs, compare_targets, import_project
from cmakeless.tools.templates import TEMPLATES, available_templates, render_template

requires_cmake = pytest.mark.skipif(shutil.which("cmake") is None, reason="cmake is not on PATH")


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_every_template_renders_valid_python_and_ci(template: str) -> None:
    """Each template's description parses, and CI ships with it."""
    files = render_template(template, "demo")
    ast.parse(files["cmakelessfile.py"])
    assert ".github/workflows/build.yml" in files
    assert "$name" not in "".join(files)


def test_unknown_templates_list_the_known_ones() -> None:
    """A typo in --template names every option."""
    with pytest.raises(ConfigurationError, match="library"):
        render_template("libary", "demo")
    assert available_templates()["game"] == "built-in"


def test_init_with_a_template_scaffolds_and_refuses_to_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """'cmakeless init --template library' writes the library layout once."""
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--template", "library", "--name", "mathx"]) == 0
    assert (tmp_path / "include" / "mathx" / "mathx.hpp").is_file()
    assert main(["init"]) == 1


def test_globs_collapse_only_when_they_match_exactly(tmp_path: Path) -> None:
    """A glob replaces a list only when it would select exactly those files."""
    (tmp_path / "src").mkdir()
    for name in ("a.cpp", "b.cpp", "extra.cpp", "c.c"):
        (tmp_path / "src" / name).write_text("", encoding="utf-8")
    every = [Path("src/a.cpp"), Path("src/b.cpp"), Path("src/extra.cpp")]
    assert collapse_globs(every, tmp_path) == ["src/*.cpp"]
    assert collapse_globs(every[:2], tmp_path) == ["src/a.cpp", "src/b.cpp"]


def test_compare_targets_reports_every_kind_of_drift() -> None:
    """Missing, extra, retyped, and re-sourced targets are all reported."""
    before = [
        TargetDetail("a", "EXECUTABLE", (Path("a.cpp"),)),
        TargetDetail("b", "STATIC_LIBRARY"),
    ]
    after = [TargetDetail("a", "SHARED_LIBRARY", (Path("z.cpp"),)), TargetDetail("c", "EXECUTABLE")]
    differences = compare_targets(before, after)
    assert "missing target 'b'" in differences
    assert "extra target 'c'" in differences
    assert any("type EXECUTABLE became SHARED_LIBRARY" in line for line in differences)
    assert any("sources differ" in line for line in differences)


@requires_cmake
def test_importing_a_real_cmake_project_round_trips(tmp_path: Path) -> None:
    """A two-target CMake project imports, and --check finds no difference."""
    (tmp_path / "src").mkdir()
    (tmp_path / "include").mkdir()
    (tmp_path / "include" / "core.hpp").write_text("int core();\n", encoding="utf-8")
    (tmp_path / "src" / "core.cpp").write_text(
        '#include "core.hpp"\nint core() { return 1; }\n', encoding="utf-8"
    )
    (tmp_path / "src" / "main.cpp").write_text(
        '#include "core.hpp"\nint main() { return core() - 1; }\n', encoding="utf-8"
    )
    (tmp_path / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.25)\n"
        "project(legacy VERSION 2.0.0 LANGUAGES CXX)\n"
        "add_library(core STATIC src/core.cpp)\n"
        "target_include_directories(core PUBLIC include)\n"
        "target_compile_definitions(core PUBLIC CORE_LEVEL=2)\n"
        "add_executable(app src/main.cpp)\n"
        "target_link_libraries(app PRIVATE core)\n",
        encoding="utf-8",
    )
    result = import_project(tmp_path)
    assert result.targets == 2
    assert "core.define('CORE_LEVEL', '2')" in result.script
    assert "app.link(core)" in result.script
    assert "Project('legacy', version='2.0.0'" in result.script
    assert check_import(tmp_path, result.script) == []


def test_workspace_selection_by_member_and_by_change(tmp_path: Path) -> None:
    """--project picks one member; a shared lockfile change affects all."""
    for member in ("engine", "tools/editor"):
        (tmp_path / member).mkdir(parents=True)
        (tmp_path / member / "cmakelessfile.py").write_text("", encoding="utf-8")
    workspace = Workspace(root=tmp_path)
    workspace.add("engine")
    workspace.add("tools/editor")
    assert workspace.select(project="editor") == [Path("tools/editor")]
    with pytest.raises(ConfigurationError, match="No workspace member"):
        workspace.select(project="nope")
    workspace._changed_files = lambda _ref: {"engine/src/a.cpp"}  # type: ignore[method-assign]
    assert workspace.select(affected_since="main") == [Path("engine")]
    workspace._changed_files = lambda _ref: {"cmakeless.lock"}  # type: ignore[method-assign]
    assert len(workspace.select(affected_since="main")) == 2


def test_workspace_members_need_a_description(tmp_path: Path) -> None:
    """A member directory without cmakelessfile.py is refused immediately."""
    with pytest.raises(ConfigurationError, match=r"has no cmakelessfile.py"):
        Workspace(root=tmp_path).add("missing")


def test_explain_names_the_declaring_line_and_visibility(
    project_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """explain shows the origin, why each link is private, and the CMake."""
    project = Project("demo", root=project_dir, cpp_std=20)
    lib = project.add_library("core", sources=["src/main.cpp"])
    app = project.add_executable("app", sources=["src/main.cpp"])
    app.link(lib)
    with _context.run_options_override(_context.RunOptions(subject="app")):
        run_workflow(project, "explain")
    out = capsys.readouterr().out
    assert "target 'app'" in out
    assert "core is PRIVATE" in out
    assert "add_executable(app)" in out


def test_diff_reports_stale_generated_files(
    project_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """diff with --exit-code fails CI when the committed file is stale."""
    project = Project("demo", root=project_dir, cpp_std=20)
    project.add_executable("app", sources=["src/main.cpp"])
    (project_dir / "CMakeLists.txt").write_text("stale\n", encoding="utf-8")
    with (
        _context.run_options_override(_context.RunOptions(exit_code=True)),
        pytest.raises(SystemExit),
    ):
        run_workflow(project, "diff")
    assert "-stale" in capsys.readouterr().out


def test_audit_flags_and_approves_trust_on_first_use(
    project_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """audit flags a tofu pin, and --approve records the review."""
    project = Project("demo", root=project_dir, cpp_std=20)
    package = LockedPackage(
        name="pkg", version="1.0", backend="auto", cmake_name="pkg", targets=("pkg::pkg",),
        url="https://example.test/p.tar.gz", sha256="0" * 64, pin_source="tofu",
    )  # fmt: skip
    write_lockfile(project.lock_path, {"pkg": package})
    run_workflow(project, "audit")
    assert "trust-on-first-use" in capsys.readouterr().out
    with _context.run_options_override(_context.RunOptions(approve=("pkg",))):
        run_workflow(project, "audit")
    assert read_lockfile(project.lock_path).packages["pkg"].pin_source == "reviewed"
