# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Target vocabulary: private include directories, cpp_std, and link_options."""

from __future__ import annotations

from pathlib import Path

import pytest

from cmakeless import ConfigurationError, Project
from cmakeless.api.when import When
from cmakeless.model.nodes import WhenKind


@pytest.fixture
def vocab_project(project_dir: Path) -> Project:
    """A project on disk with an internal source dir and an include dir."""
    (project_dir / "src" / "internal").mkdir()
    (project_dir / "include").mkdir()
    (project_dir / "src" / "engine.cpp").write_text("", encoding="utf-8")
    return Project("demo", root=project_dir)


def test_include_dirs_freezes_into_the_model(vocab_project: Project) -> None:
    """Include dirs freezes into the model."""
    app = vocab_project.add_executable("app", sources=["src/main.cpp"])
    app.include_dirs("src/internal")
    model = vocab_project.freeze()
    assert model.executables[0].private_include_dirs == (Path("src/internal"),)


def test_missing_include_dir_rejected(vocab_project: Project) -> None:
    """A private include directory that does not exist is rejected."""
    app = vocab_project.add_executable("app", sources=["src/main.cpp"])
    app.include_dirs("src/missing")
    with pytest.raises(ConfigurationError, match="does not exist"):
        vocab_project.freeze()


def test_cpp_std_override_freezes_into_the_model(vocab_project: Project) -> None:
    """A per-target cpp_std attribute freezes into the model."""
    app = vocab_project.add_executable("app", sources=["src/main.cpp"])
    app.cpp_std = 23
    model = vocab_project.freeze()
    assert model.cpp_std == 17
    assert model.executables[0].cpp_std == 23


def test_target_without_cpp_std_override_freezes_to_none(vocab_project: Project) -> None:
    """A target that never sets cpp_std freezes to None (use the project's)."""
    vocab_project.add_executable("app", sources=["src/main.cpp"])
    model = vocab_project.freeze()
    assert model.executables[0].cpp_std is None


def test_unknown_cpp_std_override_rejected(vocab_project: Project) -> None:
    """An unknown per-target cpp_std override is rejected at freeze time."""
    app = vocab_project.add_executable("app", sources=["src/main.cpp"])
    app.cpp_std = 42
    with pytest.raises(ConfigurationError, match="Unknown C\\+\\+ standard"):
        vocab_project.freeze()


def test_header_only_library_rejects_include_dirs(vocab_project: Project) -> None:
    """A header-only library cannot have private include directories."""
    headers = vocab_project.add_library("hdrs", public_headers="include/", kind="header_only")
    headers.include_dirs("src/internal")
    with pytest.raises(ConfigurationError, match="cannot have private include directories"):
        vocab_project.freeze()


def test_header_only_library_rejects_cpp_std_override(vocab_project: Project) -> None:
    """A header-only library cannot override cpp_std."""
    headers = vocab_project.add_library("hdrs", public_headers="include/", kind="header_only")
    headers.cpp_std = 23
    with pytest.raises(ConfigurationError, match="cannot override cpp_std"):
        vocab_project.freeze()


def test_link_options_freezes_with_no_guard(vocab_project: Project) -> None:
    """Link options freezes with no guard."""
    app = vocab_project.add_executable("app", sources=["src/main.cpp"])
    app.link_options("-Wl,--as-needed")
    model = vocab_project.freeze()
    (link_options,) = model.executables[0].link_options
    assert link_options.flags == ("-Wl,--as-needed",)
    assert link_options.when is None


def test_link_options_accepts_a_when_condition(vocab_project: Project) -> None:
    """Link options accepts a When condition."""
    app = vocab_project.add_executable("app", sources=["src/main.cpp"])
    app.link_options("/SUBSYSTEM:WINDOWS", when=When.compiler("msvc"))
    model = vocab_project.freeze()
    (link_options,) = model.executables[0].link_options
    assert link_options.when is not None
    assert link_options.when.kind is WhenKind.COMPILER
    assert link_options.when.names == ("MSVC",)


def test_link_options_accepts_the_legacy_compiler_string(vocab_project: Project) -> None:
    """Link options accepts the legacy '|'-separated compiler string too."""
    app = vocab_project.add_executable("app", sources=["src/main.cpp"])
    app.link_options("-static-libgcc", when="gcc")
    model = vocab_project.freeze()
    (link_options,) = model.executables[0].link_options
    assert link_options.when is not None
    assert link_options.when.names == ("GNU",)


def test_define_accepts_a_when_condition(vocab_project: Project) -> None:
    """Define accepts a When condition."""
    gui = vocab_project.option("MYLIB_BUILD_GUI", default=True)
    app = vocab_project.add_executable("app", sources=["src/main.cpp"])
    app.define("HAS_GUI", when=When.option(gui))
    model = vocab_project.freeze()
    define = model.executables[0].defines[0]
    assert define.when is not None
    assert define.when.kind is WhenKind.OPTION
    assert define.when.option_name == "MYLIB_BUILD_GUI"


def test_pch_freezes_into_the_model(vocab_project: Project) -> None:
    """Pch freezes into the model."""
    (vocab_project.root / "src" / "internal" / "pch.hpp").write_text("", encoding="utf-8")
    app = vocab_project.add_executable("app", sources=["src/main.cpp"])
    app.pch = ["<vector>", "src/internal/pch.hpp"]
    model = vocab_project.freeze()
    assert model.executables[0].pch_headers == ("<vector>", "src/internal/pch.hpp")


def test_missing_project_relative_pch_header_rejected(vocab_project: Project) -> None:
    """A missing project-relative pch header is rejected; system headers are not checked."""
    app = vocab_project.add_executable("app", sources=["src/main.cpp"])
    app.pch = ["src/missing_pch.hpp"]
    with pytest.raises(ConfigurationError, match="does not exist"):
        vocab_project.freeze()


def test_system_pch_header_is_never_checked_for_existence(vocab_project: Project) -> None:
    """A system pch header in angle brackets is never checked for existence."""
    app = vocab_project.add_executable("app", sources=["src/main.cpp"])
    app.pch = ["<does_not_exist_anywhere.hpp>"]
    vocab_project.freeze()


def test_unity_freezes_into_the_model(vocab_project: Project) -> None:
    """Unity freezes into the model."""
    app = vocab_project.add_executable("app", sources=["src/main.cpp"])
    app.unity = True
    model = vocab_project.freeze()
    assert model.executables[0].unity is True


def test_header_only_library_rejects_pch(vocab_project: Project) -> None:
    """A header-only library cannot use precompiled headers."""
    headers = vocab_project.add_library("hdrs", public_headers="include/", kind="header_only")
    headers.pch = ["<vector>"]
    with pytest.raises(ConfigurationError, match="cannot use precompiled headers"):
        vocab_project.freeze()


def test_header_only_library_rejects_unity(vocab_project: Project) -> None:
    """A header-only library cannot use unity builds."""
    headers = vocab_project.add_library("hdrs", public_headers="include/", kind="header_only")
    headers.unity = True
    with pytest.raises(ConfigurationError, match="cannot use precompiled headers or unity builds"):
        vocab_project.freeze()
