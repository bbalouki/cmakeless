# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""WhenModel: a frozen, composable boolean-condition tree."""

from __future__ import annotations

from cmakeless.model.nodes import WhenKind, WhenModel


def test_leaf_nodes_are_equal_by_value() -> None:
    """Leaf nodes are equal by value."""
    first = WhenModel(kind=WhenKind.PLATFORM, names=("Windows",))
    second = WhenModel(kind=WhenKind.PLATFORM, names=("Windows",))
    assert first == second


def test_leaf_nodes_are_hashable() -> None:
    """Leaf nodes are hashable, so they can nest inside other frozen dataclasses."""
    node = WhenModel(kind=WhenKind.COMPILER, names=("GNU", "Clang"))
    assert hash(node) == hash(WhenModel(kind=WhenKind.COMPILER, names=("GNU", "Clang")))


def test_option_leaf_carries_name_and_equality_value() -> None:
    """Option leaf carries name and equality value."""
    node = WhenModel(kind=WhenKind.OPTION, option_name="GUI", option_equals=False)
    assert node.option_name == "GUI"
    assert node.option_equals is False


def test_combinator_nodes_nest_operands() -> None:
    """Combinator nodes nest operands, and the whole tree is hashable."""
    left = WhenModel(kind=WhenKind.PLATFORM, names=("Windows",))
    right = WhenModel(kind=WhenKind.OPTION, option_name="GUI")
    combined = WhenModel(kind=WhenKind.AND, operands=(left, right))
    assert combined.operands == (left, right)
    assert hash(combined) == hash(WhenModel(kind=WhenKind.AND, operands=(left, right)))


def test_not_node_wraps_a_single_operand() -> None:
    """Not node wraps a single operand."""
    inner = WhenModel(kind=WhenKind.CONFIG, names=("Debug",))
    negated = WhenModel(kind=WhenKind.NOT, operands=(inner,))
    assert negated.operands == (inner,)
