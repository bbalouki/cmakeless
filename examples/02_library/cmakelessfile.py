# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""A static library with public headers, linked into an executable.

Shows glob sources, strict warnings, preprocessor defines, a private
(non-exported) include directory, and a guarded linker flag.
"""

from cmakeless import Project

project = Project("mygame", version="1.0.0", cpp_std=23, warnings="strict")

engine = project.add_library(
    "engine",
    sources=["src/engine/*.cpp"],
    public_headers="include/",
    kind="static",
)
engine.define("GAME_MAX_PLAYERS", 8)
engine.include_dirs("src/engine/internal")  # private: never exposed to consumers

app = project.add_executable("mygame", sources=["src/main.cpp"])
app.link(engine)
app.link_options("-Wl,--as-needed", when="gcc")  # a GNU ld flag, not universal across clang

project.build()
