# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""A parent project composing a self-contained subproject (its own cmakelessfile.py)."""

from cmakeless import Project

project = Project("workshop", version="1.0.0", cpp_std=20)

app = project.add_executable("workshop", sources=["src/main.cpp"])

# The asset packer is a self-contained tool with its own build description;
# the parent just mounts it. Both binaries land in one build tree.
project.add_subproject("tools/asset_packer")

project.build()
