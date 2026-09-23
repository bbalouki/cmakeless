"""WhenModel to CMake generator expressions.

Only the compile-level rendering (define/compile_options/link_options) is
implemented so far; a structural if()-block renderer for link()/
add_subproject() is a deliberate follow-up (see ROADMAP.md), since those call
sites need new model fields and validation this batch does not add.
"""

from __future__ import annotations

from cmakeless.model.nodes import WhenKind, WhenModel


def render_generator_expression(when: WhenModel) -> str:
    """Render a WhenModel as a CMake boolean generator expression.

    Args:
        when: The condition to render; every field is already validated
            and canonical (CMake compiler/platform ids, not friendly names).

    Returns:
        A bare boolean generator expression, for example
        "$<CXX_COMPILER_ID:GNU,Clang>" or "$<AND:$<PLATFORM_ID:Windows>,
        $<BOOL:${GUI}>>"; callers wrap this in "$<condition:value>" via
        guarded().
    """
    if when.kind is WhenKind.PLATFORM:
        return f"$<PLATFORM_ID:{','.join(when.names)}>"
    if when.kind is WhenKind.COMPILER:
        return f"$<CXX_COMPILER_ID:{','.join(when.names)}>"
    if when.kind is WhenKind.CONFIG:
        return f"$<CONFIG:{','.join(when.names)}>"
    if when.kind is WhenKind.OPTION:
        return _render_option(when)
    if when.kind is WhenKind.NOT:
        return f"$<NOT:{render_generator_expression(when.operands[0])}>"
    combinator = "AND" if when.kind is WhenKind.AND else "OR"
    inner = ",".join(render_generator_expression(operand) for operand in when.operands)
    return f"$<{combinator}:{inner}>"


def _render_option(when: WhenModel) -> str:
    """Render an OPTION leaf as a generator expression on its cache variable.

    Args:
        when: The OPTION-kind condition to render.

    Returns:
        A $<BOOL:...>, $<NOT:$<BOOL:...>>, $<EQUAL:...>, or $<STREQUAL:...>
        expression, depending on the option's declared type.
    """
    assert when.option_name is not None, "OPTION leaves always carry a name"
    variable = f"${{{when.option_name}}}"
    if isinstance(when.option_equals, bool):
        condition = f"$<BOOL:{variable}>"
        return condition if when.option_equals else f"$<NOT:{condition}>"
    if isinstance(when.option_equals, int):
        return f"$<EQUAL:{variable},{when.option_equals}>"
    return f"$<STREQUAL:{variable},{when.option_equals}>"


def guarded(value: str, when: WhenModel | None) -> str:
    """Wrap a single compile/link/definition token in its When guard, if any.

    Args:
        value: The bare token (a flag list or a NAME=VALUE define).
        when: The guard, or None for an unconditional token.

    Returns:
        ``value`` unchanged when ``when`` is None, else
        "$<condition:value>".
    """
    if when is None:
        return value
    return f"$<{render_generator_expression(when)}:{value}>"
