"""The editor member of the workspace, built against the shared lockfile."""

from cmakeless import Project

project = Project("editor", version="0.3.0", cpp_std=20)
project.add_executable("editor", sources=["src/main.cpp"])
project.build()
