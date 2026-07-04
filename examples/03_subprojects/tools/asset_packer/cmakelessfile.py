# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""A self-contained subproject: build it alone, or let a parent mount it."""

from cmakeless import Project

project = Project("asset_packer", version="0.2.0", cpp_std=20)
project.add_executable("asset_packer", sources=["main.cpp"])
project.build()
