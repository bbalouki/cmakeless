"""Project templates for 'cmakeless init --template <name>'.

Every template builds, tests, and passes 'cmakeless doctor' on its first run,
with CI already wired. Installed plugins add their own through the
"cmakeless.templates" entry-point group: a zero-argument callable returning
a mapping of relative path to file text, where $name is the project name.
"""

from __future__ import annotations

import importlib.metadata
from collections.abc import Mapping
from pathlib import Path
from string import Template

from cmakeless.api.extensions import TEMPLATE_ENTRY_POINT_GROUP
from cmakeless.errors import ConfigurationError

_GITIGNORE = """\
build/
CMakeLists.txt
CMakePresets.json
compile_commands.json
__pycache__/
"""

_CLANG_FORMAT = """\
BasedOnStyle: LLVM
IndentWidth: 4
ColumnLimit: 100
"""

_CLANG_TIDY = """\
Checks: "bugprone-*,modernize-*,performance-*,readability-*,-readability-magic-numbers"
WarningsAsErrors: ""
"""

_CI = """\
name: build
on: [push, pull_request]
permissions:
  contents: read
jobs:
  build:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
    runs-on: $${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: pip install cmakeless ninja
      - uses: ilammy/msvc-dev-cmd@v1
        if: runner.os == 'Windows'
      - run: cmakeless test
"""

_COMMON: dict[str, str] = {
    ".gitignore": _GITIGNORE,
    ".clang-format": _CLANG_FORMAT,
    ".clang-tidy": _CLANG_TIDY,
    ".github/workflows/build.yml": _CI,
}

_MAIN = """\
#include <cstdlib>
#include <iostream>

auto main() -> int
{
    std::cout << "Hello from $name!\\n";
    return EXIT_SUCCESS;
}
"""

_APP: dict[str, str] = {
    "cmakelessfile.py": """\
from cmakeless import Project

project = Project("$name", version="0.1.0", cpp_std=20, warnings="strict")
project.add_executable("$name", sources=["src/main.cpp"])
project.build()
""",
    "src/main.cpp": _MAIN,
}

_LIBRARY: dict[str, str] = {
    "cmakelessfile.py": """\
from cmakeless import Project

project = Project("$name", version="1.0.0", cpp_std=20, warnings="max")

lib = project.add_library(
    "$name",
    sources=["src/*.cpp"],
    public_headers="include/",
    kind="shared",
    version="1.0.0",
    soversion="1",
)
lib.visibility = "hidden"

tests = project.add_test("${name}_tests", sources=["tests/*.cpp"], timeout=60)
tests.link(lib)

project.install(lib, headers=True, component="dev", rpath="relative")
project.export(cmake=True, pkg_config=True)
project.package(formats=["zip", "tgz"], description="The $name library")
project.build()
""",
    "include/$name/$name.hpp": """\
#pragma once

#include "${name}_export.h"

namespace $name {

/// Adds two integers; the smallest possible public API to start from.
${NAME}_EXPORT auto add(int left, int right) -> int;

}  // namespace $name
""",
    "src/$name.cpp": """\
#include "$name/$name.hpp"

namespace $name {

auto add(int left, int right) -> int { return left + right; }

}  // namespace $name
""",
    "tests/${name}_test.cpp": """\
#include <gtest/gtest.h>

#include "$name/$name.hpp"

TEST(Add, AddsTwoIntegers) { EXPECT_EQ($name::add(2, 3), 5); }
""",
}

_GAME: dict[str, str] = {
    "cmakelessfile.py": """\
from cmakeless import Preset, Profile, Project

project = Project("$name", version="0.1.0", cpp_std=23, warnings="strict")

engine = project.add_library("engine", sources=["src/engine/*.cpp"], public_headers="include/")
engine.unity = True

game = project.add_executable("$name", sources=["src/main.cpp"])
game.link(engine)
# Set game.gui = True once a windowing library supplies the platform entry point.

project.add_preset(Preset("debug", optimize="debug", sanitize=["address"]))
project.add_preset(Preset("shipping", optimize="release", lto=True))
game.profile = Profile.low_latency()
project.install(game, runtime_dependencies=True)
project.package(formats=["zip"])
project.build()
""",
    "include/engine/world.hpp": """\
#pragma once

namespace engine {

/// Advances the simulation by one fixed step and returns the new tick count.
auto step(int tick) -> int;

}  // namespace engine
""",
    "src/engine/world.cpp": """\
#include "engine/world.hpp"

namespace engine {

auto step(int tick) -> int { return tick + 1; }

}  // namespace engine
""",
    "src/main.cpp": """\
#include <cstdlib>
#include <iostream>

#include "engine/world.hpp"

auto main() -> int
{
    int tick = 0;
    for (int frame = 0; frame < 3; ++frame) {
        tick = engine::step(tick);
    }
    std::cout << "$name ran " << tick << " ticks\\n";
    return EXIT_SUCCESS;
}
""",
}

_EMBEDDED: dict[str, str] = {
    "cmakelessfile.py": """\
from cmakeless import Preset, Profile, Project, Toolchain

project = Project("$name", version="0.1.0", cpp_std=20, c_std=11, profile=Profile.embedded())

firmware = project.add_executable("$name", sources=["src/main.cpp", "src/hal.c"])

# The host build runs the logic on this machine; 'cmakeless build --preset device'
# cross-compiles for the board once arm-none-eabi-gcc is installed.
project.add_toolchain(Toolchain.arm_none_eabi(cpu="cortex-m4"))
project.add_preset(Preset("device", optimize="minsize", toolchain="arm-none-eabi"))
project.build()
""",
    "src/hal.c": """\
int hal_read_sensor(void) { return 42; }
""",
    "src/main.cpp": """\
extern "C" int hal_read_sensor(void);

auto main() -> int
{
    return hal_read_sensor() == 42 ? 0 : 1;
}
""",
}

_PYTHON_EXT: dict[str, str] = {
    "cmakelessfile.py": """\
from cmakeless import Project

project = Project("$name", version="0.1.0", cpp_std=20)
project.add_python_module("$name", sources=["src/bindings.cpp"], binding="nanobind")
project.build()
""",
    "src/bindings.cpp": """\
#include <nanobind/nanobind.h>

NB_MODULE($name, module)
{
    module.def("add", [](int left, int right) { return left + right; });
}
""",
    "test_$name.py": """\
import $name


def test_add() -> None:
    assert $name.add(2, 3) == 5
""",
}

_LOW_LATENCY: dict[str, str] = {
    "cmakelessfile.py": """\
from cmakeless import Profile, Project

project = Project(
    "$name",
    version="0.1.0",
    cpp_std=23,
    warnings="max",
    profile=Profile.low_latency() | Profile.hardened(),
)
project.warnings_as_errors = True

engine = project.add_executable("$name", sources=["src/main.cpp"])
# Pin the instruction set the fleet actually runs, never -march=native:
# from cmakeless import Cpu; engine.cpu = Cpu.x86_64(level="v3")
project.build()
""",
    "src/main.cpp": _MAIN,
}

TEMPLATES: dict[str, dict[str, str]] = {
    "app": _APP,
    "library": _LIBRARY,
    "game": _GAME,
    "embedded": _EMBEDDED,
    "python-ext": _PYTHON_EXT,
    "low-latency": _LOW_LATENCY,
}


def available_templates() -> dict[str, str]:
    """Name every template, built in or plugin supplied.

    Returns:
        Template name to its origin ("built-in" or the plugin's distribution).
    """
    names = dict.fromkeys(TEMPLATES, "built-in")
    for entry_point in importlib.metadata.entry_points(group=TEMPLATE_ENTRY_POINT_GROUP):
        dist = entry_point.dist.name if entry_point.dist is not None else "plugin"
        names.setdefault(entry_point.name, dist)
    return names


def render_template(template: str, name: str) -> dict[str, str]:
    """Produce one template's files for a project name.

    Args:
        template: The template name.
        name: The project name, substituted for $name (and $NAME, upper case).

    Returns:
        Relative path to file text, CI and editor configuration included.

    Raises:
        ConfigurationError: When no template has that name.
    """
    files = _template_files(template)
    values = {"name": name, "NAME": name.upper()}
    rendered = {**_COMMON, **files}
    return {
        Template(path).substitute(values): Template(text).substitute(values)
        for path, text in rendered.items()
    }


def _template_files(template: str) -> Mapping[str, str]:
    """Find a template's raw files: built in first, then installed plugins.

    Args:
        template: The template name.

    Returns:
        Relative path to file text, before substitution.

    Raises:
        ConfigurationError: When no template has that name.
    """
    if template in TEMPLATES:
        return TEMPLATES[template]
    for entry_point in importlib.metadata.entry_points(group=TEMPLATE_ENTRY_POINT_GROUP):
        if entry_point.name == template:
            files: Mapping[str, str] = entry_point.load()()
            return files
    known = ", ".join(sorted(available_templates()))
    raise ConfigurationError(f"Unknown template {template!r}. Pick one of: {known}.")


def write_template(directory: Path, files: Mapping[str, str]) -> list[Path]:
    """Write rendered template files, never overwriting an existing file.

    Args:
        directory: Where to scaffold.
        files: Relative path to file text.

    Returns:
        The files written.
    """
    written: list[Path] = []
    for relative, text in sorted(files.items()):
        path = directory / relative
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        written.append(path)
    return written
