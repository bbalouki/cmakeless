"""CTest registration: framework discovery modules and per-test properties."""

from __future__ import annotations

from cmakeless.model.nodes import ProjectModel, TestModel
from cmakeless.model.properties import TestPropertiesModel

# Per-framework discovery-module setup, emitted once per framework in use.
# The guards make one file serve both worlds: an installed package provides
# the module on the module path, a source fetch keeps it in its own tree.
INTEGRATION_BY_FRAMEWORK = {
    "catch2": (
        "# Catch2's per-case discovery module (extras/ when fetched from source).\n"
        "if(catch2_SOURCE_DIR)\n"
        "    list(APPEND CMAKE_MODULE_PATH ${catch2_SOURCE_DIR}/extras)\n"
        "endif()\n"
        "include(Catch)"
    ),
    "gtest": "include(GoogleTest)",
    "doctest": (
        "# doctest's per-case discovery module (scripts/cmake when fetched from source).\n"
        "if(doctest_SOURCE_DIR)\n"
        "    include(${doctest_SOURCE_DIR}/scripts/cmake/doctest.cmake)\n"
        "else()\n"
        "    include(doctest)\n"
        "endif()"
    ),
}

# The per-case discovery command per framework.
_DISCOVERY_COMMAND_BY_FRAMEWORK = {
    "catch2": "catch_discover_tests",
    "gtest": "gtest_discover_tests",
    "doctest": "doctest_discover_tests",
}


def framework_includes(model: ProjectModel) -> list[str]:
    """Emit the discovery-module includes for every framework in use.

    Args:
        model: The frozen project node.

    Returns:
        One include block per framework, sorted by framework name.
    """
    frameworks = sorted({test.framework for test in model.tests} - {"none"})
    return [INTEGRATION_BY_FRAMEWORK[framework] for framework in frameworks]


def registration_block(test: TestModel) -> str:
    """Register one test target's cases with CTest, properties included.

    Args:
        test: The test target.

    Returns:
        The discovery call, or add_test plus set_tests_properties for a
        framework-less test.
    """
    properties = test.test_properties
    if test.framework == "none":
        return _plain_registration(test, properties)
    command = _DISCOVERY_COMMAND_BY_FRAMEWORK[test.framework]
    pairs = _property_pairs(properties, escape_lists=True)
    if properties.working_directory is None and not pairs:
        return f"{command}({test.name})"
    lines = [f"{command}({test.name}"]
    if properties.working_directory is not None:
        lines.append(f"    WORKING_DIRECTORY {_working_directory(properties)}")
    if pairs:
        lines.append("    PROPERTIES")
        lines.extend(f"        {name} {value}" for name, value in pairs)
    lines.append(")")
    return "\n".join(lines)


def _plain_registration(test: TestModel, properties: TestPropertiesModel) -> str:
    """Register a framework-less test, whose exit code is the verdict.

    Args:
        test: The test target.
        properties: Its CTest properties.

    Returns:
        The add_test call, plus set_tests_properties when any are set.
    """
    directory = (
        f" WORKING_DIRECTORY {_working_directory(properties)}"
        if properties.working_directory is not None
        else ""
    )
    text = f"add_test(NAME {test.name} COMMAND {test.name}{directory})"
    pairs = _property_pairs(properties, escape_lists=False)
    if not pairs:
        return text
    lines = [text, f"set_tests_properties({test.name} PROPERTIES"]
    lines.extend(f"    {name} {value}" for name, value in pairs)
    lines.append(")")
    return "\n".join(lines)


def _working_directory(properties: TestPropertiesModel) -> str:
    """Anchor a test's working directory at the project source tree.

    Args:
        properties: The test's CTest properties, with a working directory.

    Returns:
        The quoted absolute directory expression.
    """
    assert properties.working_directory is not None, "callers check first"
    return f'"${{CMAKE_CURRENT_SOURCE_DIR}}/{properties.working_directory.as_posix()}"'


def _property_pairs(
    properties: TestPropertiesModel, *, escape_lists: bool
) -> list[tuple[str, str]]:
    """Translate test properties into (CTest property, value) pairs.

    Discovery functions forward PROPERTIES as one flat list, so a list value
    needs its separators escaped to survive as one property value there.

    Args:
        properties: The test's CTest properties.
        escape_lists: True when the pairs go through a discovery function.

    Returns:
        The pairs, in a fixed order.
    """
    separator = "\\\\;" if escape_lists else ";"
    pairs: list[tuple[str, str]] = []
    if properties.timeout is not None:
        pairs.append(("TIMEOUT", str(properties.timeout)))
    for name, values in (
        ("LABELS", properties.labels),
        ("ENVIRONMENT", tuple(f"{key}={value}" for key, value in properties.env)),
        ("FIXTURES_SETUP", properties.fixtures_setup),
        ("FIXTURES_CLEANUP", properties.fixtures_cleanup),
        ("FIXTURES_REQUIRED", properties.fixtures_required),
    ):
        if values:
            pairs.append((name, f'"{separator.join(values)}"'))
    if properties.serial:
        pairs.append(("RUN_SERIAL", "ON"))
    if properties.will_fail:
        pairs.append(("WILL_FAIL", "ON"))
    return pairs
