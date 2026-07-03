"""The add_test() builder: frameworks, links, and freeze output."""

from __future__ import annotations

from pathlib import Path

import pytest

from cmakeless import ConfigurationError, Project

TEST_CPP = "int main() { return 0; }\n"


@pytest.fixture
def test_project(project_dir: Path) -> Project:
    """A project with one library and one on-disk test source."""
    (project_dir / "tests").mkdir()
    (project_dir / "tests" / "engine_test.cpp").write_text(TEST_CPP, encoding="utf-8")
    (project_dir / "include").mkdir()
    project = Project("demo", cpp_std=20, root=project_dir)
    project.add_library("engine", sources=["src/main.cpp"])
    return project


def test_add_test_registers_the_framework_dependency(test_project: Project) -> None:
    """Add test registers the framework dependency."""
    test_project.add_test("engine_tests", sources=["tests/*.cpp"], framework="catch2")
    assert [dep.name for dep in test_project.dependencies] == ["catch2"]


def test_add_test_links_the_framework_target(test_project: Project) -> None:
    """Add test links the framework target."""
    test_project.add_test("engine_tests", sources=["tests/*.cpp"], framework="catch2")
    model = test_project.freeze()
    (test,) = model.tests
    assert test.framework == "catch2"
    assert any(link.target == "Catch2::Catch2WithMain" and link.external for link in test.links)


def test_gtest_uses_the_googletest_package(test_project: Project) -> None:
    """Gtest uses the googletest package."""
    test_project.add_test("engine_tests", sources=["tests/*.cpp"], framework="gtest")
    model = test_project.freeze()
    assert [dep.name for dep in model.dependencies] == ["googletest"]
    (test,) = model.tests
    assert any(link.target == "GTest::gtest_main" for link in test.links)


def test_default_framework_is_gtest(test_project: Project) -> None:
    """The default test framework is googletest when none is given."""
    test = test_project.add_test("engine_tests", sources=["tests/*.cpp"])
    model = test_project.freeze()
    assert test.framework == "gtest"
    assert model.tests[0].framework == "gtest"
    assert [dep.name for dep in model.dependencies] == ["googletest"]


def test_framework_none_adds_no_dependency(test_project: Project) -> None:
    """Framework none adds no dependency."""
    test_project.add_test("smoke", sources=["tests/*.cpp"], framework="none")
    model = test_project.freeze()
    assert model.dependencies == ()
    assert model.tests[0].framework == "none"


def test_unknown_framework_fails_at_the_call_site(test_project: Project) -> None:
    """Unknown framework fails at the call site."""
    with pytest.raises(ConfigurationError, match="cppunit"):
        test_project.add_test("engine_tests", sources=["tests/*.cpp"], framework="cppunit")  # type: ignore[arg-type]


def test_tests_link_project_libraries(test_project: Project) -> None:
    """Tests link project libraries."""
    engine = test_project._libraries[0]
    tests = test_project.add_test("engine_tests", sources=["tests/*.cpp"], framework="none")
    tests.link(engine)
    model = test_project.freeze()
    assert model.tests[0].links[0].target == "engine"


def test_test_names_collide_with_target_names(test_project: Project) -> None:
    """Test names collide with target names."""
    test_project.add_test("engine", sources=["tests/*.cpp"], framework="none")
    with pytest.raises(ConfigurationError, match="Duplicate target name"):
        test_project.freeze()


def test_sanitize_attribute_freezes_sorted(test_project: Project) -> None:
    """Sanitize attribute freezes sorted."""
    tests = test_project.add_test("engine_tests", sources=["tests/*.cpp"], framework="none")
    tests.sanitize = ["undefined", "address", "undefined"]
    model = test_project.freeze()
    assert model.tests[0].sanitize == ("address", "undefined")
