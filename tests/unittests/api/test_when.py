"""The When condition object: factories, validation, and composition."""

from __future__ import annotations

import pytest

from cmakeless import ConfigurationError
from cmakeless.api.options import Option
from cmakeless.api.when import When
from cmakeless.model.nodes import WhenKind


def make_option(name: str = "GUI", *, default: bool = True) -> Option:
    """A standalone Option, not registered with any project."""
    return Option(name, default=default, script="cmakelessfile.py")


def test_platform_condition_resolves_canonical_ids() -> None:
    """Platform condition resolves canonical ids."""
    when = When.platform("windows", "linux")
    model = when._freeze()
    assert model.kind is WhenKind.PLATFORM
    assert model.names == ("Windows", "Linux")


def test_unknown_platform_rejected() -> None:
    """Unknown platform rejected."""
    with pytest.raises(ConfigurationError, match="Unknown platform 'freebsd'"):
        When.platform("freebsd")


def test_compiler_condition_expands_clang_to_both_ids() -> None:
    """Compiler condition expands clang to both LLVM Clang and Apple Clang."""
    model = When.compiler("clang")._freeze()
    assert model.kind is WhenKind.COMPILER
    assert model.names == ("Clang", "AppleClang")


def test_unknown_compiler_rejected() -> None:
    """Unknown compiler rejected."""
    with pytest.raises(ConfigurationError, match="Unknown compiler 'icc'"):
        When.compiler("icc")


def test_config_condition_accepts_known_cmake_configs() -> None:
    """Config condition accepts known cmake configs."""
    model = When.config("Debug", "RelWithDebInfo")._freeze()
    assert model.kind is WhenKind.CONFIG
    assert model.names == ("Debug", "RelWithDebInfo")


def test_unknown_config_rejected() -> None:
    """Unknown config rejected."""
    with pytest.raises(ConfigurationError, match="Unknown build configuration 'Beta'"):
        When.config("Beta")


def test_option_condition_defaults_to_true() -> None:
    """Option condition defaults to true."""
    option = make_option()
    model = When.option(option)._freeze()
    assert model.kind is WhenKind.OPTION
    assert model.option_name == "GUI"
    assert model.option_equals is True


def test_option_condition_accepts_a_bare_name() -> None:
    """Option condition accepts a bare name, not just an Option handle."""
    model = When.option("GUI", equals=False)._freeze()
    assert model.option_name == "GUI"
    assert model.option_equals is False


def test_and_combines_two_conditions() -> None:
    """And combines two conditions."""
    combined = When.platform("windows") & When.compiler("msvc")
    model = combined._freeze()
    assert model.kind is WhenKind.AND
    assert len(model.operands) == 2


def test_or_combines_two_conditions() -> None:
    """Or combines two conditions."""
    combined = When.compiler("gcc") | When.compiler("clang")
    assert combined._freeze().kind is WhenKind.OR


def test_invert_negates_a_condition() -> None:
    """Invert negates a condition."""
    negated = ~When.config("Debug")
    model = negated._freeze()
    assert model.kind is WhenKind.NOT
    assert model.operands[0].kind is WhenKind.CONFIG


def test_bare_option_used_as_and_operand_is_sugar_for_when_option() -> None:
    """A bare Option used as an & operand is sugar for When.option(option)."""
    gui = make_option("GUI")
    combined = When.platform("windows") & gui
    model = combined._freeze()
    assert model.operands[1].kind is WhenKind.OPTION
    assert model.operands[1].option_name == "GUI"
