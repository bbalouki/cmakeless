# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Custom build steps: Command and CustomTarget through the public API."""

from __future__ import annotations

from pathlib import Path

import pytest

from cmakeless import ConfigurationError, Project


@pytest.fixture
def build_project(project_dir: Path) -> Project:
    """A minimal buildable project with a real script dependency on disk."""
    (project_dir / "tools").mkdir()
    (project_dir / "tools" / "gen_version.py").write_text("", encoding="utf-8")
    return Project("demo", root=project_dir)


def test_add_command_returns_a_handle_with_outputs(build_project: Project) -> None:
    """Add command returns a handle with outputs."""
    command = build_project.add_command(
        output=["generated/version.cpp"],
        command=["python", "tools/gen_version.py"],
        depends=["tools/gen_version.py"],
        comment="Generating version.cpp",
    )
    assert command.outputs == ("generated/version.cpp",)


def test_add_command_freezes_into_the_model(build_project: Project) -> None:
    """Add command freezes into the model."""
    build_project.add_command(
        output=["generated/version.cpp"],
        command=["python", "tools/gen_version.py"],
        depends=["tools/gen_version.py"],
    )
    model = build_project.freeze()
    (command,) = model.commands
    assert command.outputs == (Path("generated/version.cpp"),)
    assert command.command == ("python", "tools/gen_version.py")
    assert command.depends == (Path("tools/gen_version.py"),)


def test_add_command_requires_an_output(build_project: Project) -> None:
    """Add command requires an output."""
    with pytest.raises(ConfigurationError, match="output"):
        build_project.add_command(output=[], command=["python", "tools/gen_version.py"])


def test_add_command_requires_a_command(build_project: Project) -> None:
    """Add command requires a command."""
    with pytest.raises(ConfigurationError, match="command"):
        build_project.add_command(output=["generated/version.cpp"], command=[])


def test_add_sources_accepts_a_command_handle(build_project: Project) -> None:
    """Add sources accepts a command handle, wiring the generated source in."""
    gen = build_project.add_command(
        output=["generated/version.cpp"], command=["python", "tools/gen_version.py"]
    )
    app = build_project.add_executable("app", sources=["src/main.cpp"])
    app.add_sources(gen)
    model = build_project.freeze()
    assert Path("generated/version.cpp") in model.executables[0].sources


def test_generated_source_skips_the_existence_check(build_project: Project) -> None:
    """A generated source never needs to exist on disk at freeze time."""
    gen = build_project.add_command(
        output=["generated/version.cpp"], command=["python", "tools/gen_version.py"]
    )
    app = build_project.add_executable("app", sources=["src/main.cpp"])
    app.add_sources(gen)
    build_project.freeze()  # must not raise even though the file was never created


def test_add_custom_target_returns_a_handle(build_project: Project) -> None:
    """Add custom target returns a handle."""
    target = build_project.add_custom_target("lint", command=["ruff", "check", "."])
    assert target.name == "lint"


def test_add_custom_target_requires_a_command(build_project: Project) -> None:
    """Add custom target requires a command."""
    with pytest.raises(ConfigurationError, match="command"):
        build_project.add_custom_target("lint", command=[])


def test_custom_target_depends_accepts_a_command_handle(build_project: Project) -> None:
    """Custom target depends accepts a command handle, flattening to its outputs."""
    manifest = build_project.add_command(
        output=["assets/manifest.json"], command=["python", "tools/gen_version.py"]
    )
    build_project.add_custom_target(
        "cook-assets", command=["python", "cook.py"], depends=[manifest]
    )
    model = build_project.freeze()
    (custom_target,) = model.custom_targets
    assert custom_target.depends == (Path("assets/manifest.json"),)


def test_custom_target_name_collides_with_a_regular_target_rejected(
    build_project: Project,
) -> None:
    """A custom target name colliding with a regular target is rejected."""
    build_project.add_executable("app", sources=["src/main.cpp"])
    build_project.add_custom_target("app", command=["echo", "hi"])
    with pytest.raises(ConfigurationError, match="Duplicate target name"):
        build_project.freeze()


def test_command_output_must_be_relative(build_project: Project) -> None:
    """Command output must be relative."""
    build_project.add_command(output=["/etc/evil.cpp"], command=["python", "gen.py"])
    with pytest.raises(ConfigurationError, match="relative path"):
        build_project.freeze()


def test_command_depends_on_nonexistent_file_rejected(build_project: Project) -> None:
    """Command depends on nonexistent file rejected."""
    build_project.add_command(
        output=["generated/version.cpp"],
        command=["python", "gen.py"],
        depends=["tools/missing.py"],
    )
    with pytest.raises(ConfigurationError, match="does not exist"):
        build_project.freeze()


def test_command_depends_on_another_commands_output_is_exempt(build_project: Project) -> None:
    """A command's depends= on another command's output needs no file on disk."""
    manifest = build_project.add_command(
        output=["assets/manifest.json"], command=["python", "tools/gen_version.py"]
    )
    build_project.add_command(
        output=["cooked/done.marker"], command=["python", "cook.py"], depends=[manifest]
    )
    build_project.freeze()  # must not raise


def test_unused_command_output_prints_a_soft_warning(
    build_project: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    """An add_command() output nothing consumes prints a warning, not an error."""
    build_project.add_command(
        output=["generated/orphan.txt"], command=["python", "tools/gen_version.py"]
    )
    build_project.freeze()  # must not raise
    assert "not consumed" in capsys.readouterr().out


def test_consumed_command_output_prints_no_warning(
    build_project: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    """A consumed add_command() output prints no warning."""
    gen = build_project.add_command(
        output=["generated/version.cpp"], command=["python", "tools/gen_version.py"]
    )
    app = build_project.add_executable("app", sources=["src/main.cpp"])
    app.add_sources(gen)
    build_project.freeze()
    assert "not consumed" not in capsys.readouterr().out
