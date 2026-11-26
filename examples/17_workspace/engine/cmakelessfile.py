"""The engine member of the workspace, built against the shared lockfile."""

from cmakeless import Project

project = Project("engine", version="1.0.0", cpp_std=20)
project.add_executable("engine", sources=["src/main.cpp"])
project.build()
