# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""The install() and package() declarations and their validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from cmakeless import ConfigurationError, Project


@pytest.fixture
def project(project_dir: Path) -> Project:
    """A project with a library and an executable to ship."""
    (project_dir / "include").mkdir()
    built = Project("demo", cpp_std=20, root=project_dir)
    built.add_library("engine", sources=["src/main.cpp"], public_headers="include/")
    built.add_executable("app", sources=["src/main.cpp"])
    return built


def test_install_rules_freeze_with_headers_flag(project: Project) -> None:
    """Install rules freeze with headers flag."""
    project.install(project._libraries[0], headers=True)
    project.install(project._executables[0])
    model = project.freeze()
    assert [(rule.target, rule.headers) for rule in model.installs] == [
        ("engine", True),
        ("app", False),
    ]


def test_install_rejects_non_target_arguments(project: Project) -> None:
    """Install rejects non target arguments."""
    with pytest.raises(ConfigurationError, match="add_executable"):
        project.install("engine")  # type: ignore[arg-type]


def test_installing_a_target_twice_is_rejected(project: Project) -> None:
    """Installing a target twice is rejected."""
    project.install(project._executables[0])
    project.install(project._executables[0])
    with pytest.raises(ConfigurationError, match="installed twice"):
        project.freeze()


def test_installing_a_test_target_is_rejected(project: Project) -> None:
    """Installing a test target is rejected."""
    (project.root / "tests").mkdir()
    (project.root / "tests" / "t.cpp").write_text("int main() { return 0; }\n", encoding="utf-8")
    tests = project.add_test("engine_tests", sources=["tests/t.cpp"], framework="none")
    project._installs.append((tests.name, False))
    with pytest.raises(ConfigurationError, match="development tools"):
        project.freeze()


def test_package_needs_install_rules(project: Project) -> None:
    """Package needs install rules."""
    project.package(formats=["zip"])
    with pytest.raises(ConfigurationError, match="nothing to package"):
        project.freeze()


def test_unknown_package_format_is_rejected(project: Project) -> None:
    """Unknown package format is rejected."""
    project.install(project._executables[0])
    project.package(formats=["msi"])
    with pytest.raises(ConfigurationError, match="msi"):
        project.freeze()


def test_package_formats_freeze_as_given(project: Project) -> None:
    """Package formats freeze as given."""
    project.install(project._executables[0])
    project.package(formats=["zip", "tgz"])
    model = project.freeze()
    assert model.package_formats == ("zip", "tgz")
