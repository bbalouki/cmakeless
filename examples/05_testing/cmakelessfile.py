# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Testing as a first-class verb: Catch2 arrives and registers itself.

add_test() fetches the framework like any dependency (pinned in
cmakeless.lock), links it, and registers every test case with CTest.

    $ cmakeless test                      # build, then run the suite
    $ cmakeless test --sanitize=address   # same, under AddressSanitizer
"""

from cmakeless import Project

project = Project("testing_demo", version="1.0.0", cpp_std=20, warnings="strict")

engine = project.add_library(
    "engine",
    sources=["src/engine/*.cpp"],
    public_headers="include/",
)

tests = project.add_test(
    "engine_tests",
    sources=["tests/*.cpp"],
    framework="catch2",
)
tests.link(engine)

project.build()
