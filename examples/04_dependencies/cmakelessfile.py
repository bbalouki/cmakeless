"""One line per external package: fmt arrives with no CMake written.

The default strategy tries the system package first and falls back to a
source fetch pinned by URL and SHA256; every resolution is recorded in
cmakeless.lock so CI and teammates get the identical dependency tree.
"""

from cmakeless import Project

project = Project("format_demo", version="1.0.0", cpp_std=20, warnings="strict")

app = project.add_executable("format_demo", sources=["src/main.cpp"])
app.depends("fmt/10.2.1")

project.build()
