# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""The capstone: one cmakelessfile.py that exercises the whole surface at once.

A single library, built once, is shipped four ways from the same description:

  * a C++ static library (stats) with public headers and a private fmt dep,
  * a command-line tool (stats_cli) that links it,
  * a GoogleTest suite (the default framework) that tests it,
  * a pybind11 Python module (pystats, the default binding) that exposes it,

plus release/debug presets, install with an export set, CPack packaging, and a
live Observer that prints each pipeline step. Every one of these is one call.

    $ cmakeless build                     # library + CLI + module, debug tree
    $ cmakeless test                      # GoogleTest suite via CTest
    $ cmakeless build --preset release    # optimized, LTO, its own build tree
    $ cmakeless install --prefix dist     # headers + library + Config.cmake
    $ cmakeless package                   # a distributable archive via CPack
    $ python test_pystats.py              # import pystats; use the C++ from Python

targets_info() returns the configured build as Python objects read from CMake's
File API; hold the project and call it in place of build():

    for target in project.targets_info():
        print(target.name, target.type, target.artifacts)
"""

from cmakeless import Preset, Project, StepFinished, StepStarted

FMT = "fmt/10.2.1"


class StepPrinter:
    """A minimal Observer: report each configure/build/test step as it runs."""

    def on_event(self, event: object) -> None:
        """Print a line when a pipeline step starts and finishes."""
        if isinstance(event, StepStarted):
            print(f"[capstone] -> {event.step}")
        elif isinstance(event, StepFinished):
            print(f"[capstone] <- {event.step} ({event.exit_code})")


project = Project("stats", version="1.0.0", cpp_std=20, warnings="strict")
project.add_observer(StepPrinter())

# Two named configurations, emitted into CMakePresets.json for IDEs and the CLI.
project.add_preset(Preset("debug", optimize="none", sanitize=["address"]))
project.add_preset(Preset("release", optimize="release", lto=True))

# The library. fmt is a private implementation detail (used only in series.cpp),
# so consumers link stats without inheriting fmt.
stats = project.add_library("stats", sources=["src/series.cpp"], public_headers="include/")
stats.depends(FMT)

# A CLI over the library; it prints with fmt directly, so it depends on fmt too.
cli = project.add_executable("stats_cli", sources=["src/main.cpp"])
cli.link(stats)
cli.depends(FMT)

# The test suite. framework defaults to GoogleTest; cmakeless fetches and links it.
tests = project.add_test("stats_tests", sources=["tests/*.cpp"])
tests.link(stats)

# The Python module. binding defaults to pybind11; it lands importable after build.
module = project.add_python_module("pystats", sources=["src/bindings.cpp"])
module.link(stats)

# Ship it: the library with its headers and an export set, plus the CLI.
project.install(stats, headers=True)
project.install(cli)
project.package(formats=["zip"])

project.build()
