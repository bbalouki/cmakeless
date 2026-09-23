"""A self-contained subproject: build it alone, or let a parent mount it."""

from cmakeless import Project

project = Project("asset_packer", version="0.2.0", cpp_std=20)
project.add_executable("asset_packer", sources=["main.cpp"])
project.build()
