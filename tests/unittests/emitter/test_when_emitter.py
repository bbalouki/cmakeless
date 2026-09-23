"""WhenModel to CMake generator expressions, independent of any target."""

from __future__ import annotations

from cmakeless.emitter.when_emitter import guarded, render_generator_expression
from cmakeless.model.nodes import WhenKind, WhenModel


def test_platform_renders_platform_id() -> None:
    """Platform renders platform id."""
    when = WhenModel(kind=WhenKind.PLATFORM, names=("Windows",))
    assert render_generator_expression(when) == "$<PLATFORM_ID:Windows>"


def test_compiler_renders_cxx_compiler_id() -> None:
    """Compiler renders cxx compiler id."""
    when = WhenModel(kind=WhenKind.COMPILER, names=("GNU", "Clang"))
    assert render_generator_expression(when) == "$<CXX_COMPILER_ID:GNU,Clang>"


def test_config_renders_config_expression() -> None:
    """Config renders config expression."""
    when = WhenModel(kind=WhenKind.CONFIG, names=("Debug",))
    assert render_generator_expression(when) == "$<CONFIG:Debug>"


def test_option_true_renders_bool() -> None:
    """Option true renders bool."""
    when = WhenModel(kind=WhenKind.OPTION, option_name="GUI", option_equals=True)
    assert render_generator_expression(when) == "$<BOOL:${GUI}>"


def test_option_false_renders_negated_bool() -> None:
    """Option false renders negated bool."""
    when = WhenModel(kind=WhenKind.OPTION, option_name="GUI", option_equals=False)
    assert render_generator_expression(when) == "$<NOT:$<BOOL:${GUI}>>"


def test_option_int_renders_equal() -> None:
    """Option int renders equal."""
    when = WhenModel(kind=WhenKind.OPTION, option_name="JOBS", option_equals=4)
    assert render_generator_expression(when) == "$<EQUAL:${JOBS},4>"


def test_option_string_renders_strequal() -> None:
    """Option string renders strequal."""
    when = WhenModel(kind=WhenKind.OPTION, option_name="BACKEND", option_equals="vulkan")
    assert render_generator_expression(when) == "$<STREQUAL:${BACKEND},vulkan>"


def test_not_wraps_the_operand() -> None:
    """Not wraps the operand."""
    inner = WhenModel(kind=WhenKind.CONFIG, names=("Debug",))
    when = WhenModel(kind=WhenKind.NOT, operands=(inner,))
    assert render_generator_expression(when) == "$<NOT:$<CONFIG:Debug>>"


def test_and_joins_operands() -> None:
    """And joins operands."""
    left = WhenModel(kind=WhenKind.PLATFORM, names=("Windows",))
    right = WhenModel(kind=WhenKind.OPTION, option_name="GUI")
    when = WhenModel(kind=WhenKind.AND, operands=(left, right))
    assert render_generator_expression(when) == "$<AND:$<PLATFORM_ID:Windows>,$<BOOL:${GUI}>>"


def test_or_joins_operands() -> None:
    """Or joins operands."""
    left = WhenModel(kind=WhenKind.COMPILER, names=("GNU",))
    right = WhenModel(kind=WhenKind.COMPILER, names=("Clang",))
    when = WhenModel(kind=WhenKind.OR, operands=(left, right))
    assert (
        render_generator_expression(when) == "$<OR:$<CXX_COMPILER_ID:GNU>,$<CXX_COMPILER_ID:Clang>>"
    )


def test_nested_combinators_render_recursively() -> None:
    """Nested combinators render recursively."""
    platform = WhenModel(kind=WhenKind.PLATFORM, names=("Windows",))
    option = WhenModel(kind=WhenKind.OPTION, option_name="GUI")
    negated_option = WhenModel(kind=WhenKind.NOT, operands=(option,))
    when = WhenModel(kind=WhenKind.AND, operands=(platform, negated_option))
    assert (
        render_generator_expression(when) == "$<AND:$<PLATFORM_ID:Windows>,$<NOT:$<BOOL:${GUI}>>>"
    )


def test_guarded_returns_value_unchanged_without_a_condition() -> None:
    """Guarded returns value unchanged without a condition."""
    assert guarded("-march=native", None) == "-march=native"


def test_guarded_wraps_the_value_in_the_rendered_condition() -> None:
    """Guarded wraps the value in the rendered condition."""
    when = WhenModel(kind=WhenKind.COMPILER, names=("GNU", "Clang"))
    assert guarded("-march=native", when) == "$<$<CXX_COMPILER_ID:GNU,Clang>:-march=native>"
