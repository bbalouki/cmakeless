"""WhenModel to CMake syntax: generator expressions and if() conditions.

Settings that CMake evaluates per configuration (flags, defines, link items)
render as generator expressions. Structure that must be decided at configure
time (whether a subdirectory exists at all) renders as an if() condition,
which is why a build-configuration test is rejected there: a multi-config
generator has no single configuration while it configures.
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


def render_if_condition(when: WhenModel) -> str:
    """Render a WhenModel as the argument list of a CMake if() command.

    Args:
        when: The condition to render; validation guarantees it contains no
            CONFIG leaf, which has no configure-time meaning.

    Returns:
        A parenthesized if() condition, for example
        '(CMAKE_SYSTEM_NAME STREQUAL "Linux")'.
    """
    if when.kind is WhenKind.PLATFORM:
        # $<PLATFORM_ID:...> reports CMAKE_SYSTEM_NAME, so the stored names compare as-is.
        return _any_equal("CMAKE_SYSTEM_NAME", list(when.names))
    if when.kind is WhenKind.COMPILER:
        return _any_equal("CMAKE_CXX_COMPILER_ID", list(when.names))
    if when.kind is WhenKind.OPTION:
        return _render_if_option(when)
    if when.kind is WhenKind.NOT:
        return f"(NOT {render_if_condition(when.operands[0])})"
    assert when.kind in (WhenKind.AND, WhenKind.OR), "CONFIG never reaches if() rendering"
    joiner = " AND " if when.kind is WhenKind.AND else " OR "
    return "(" + joiner.join(render_if_condition(operand) for operand in when.operands) + ")"


def _any_equal(variable: str, values: list[str]) -> str:
    """Render "variable equals any of these values" as an if() condition.

    Args:
        variable: The CMake variable to compare.
        values: The accepted values.

    Returns:
        The parenthesized OR of STREQUAL tests.
    """
    tests = [f'{variable} STREQUAL "{value}"' for value in values]
    return "(" + " OR ".join(tests) + ")"


def _render_if_option(when: WhenModel) -> str:
    """Render an OPTION leaf as an if() condition on its cache variable.

    Args:
        when: The OPTION-kind condition to render.

    Returns:
        The parenthesized test, matching the option's declared type.
    """
    assert when.option_name is not None, "OPTION leaves always carry a name"
    if isinstance(when.option_equals, bool):
        test = when.option_name if when.option_equals else f"NOT {when.option_name}"
        return f"({test})"
    if isinstance(when.option_equals, int):
        return f"({when.option_name} EQUAL {when.option_equals})"
    return f'({when.option_name} STREQUAL "{when.option_equals}")'
