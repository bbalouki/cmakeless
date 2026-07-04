# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Shared literals with no internal dependencies, safe for any module to import."""

BUILD_SCRIPT_NAME = "cmakelessfile.py"

# The default find_package(Python ...) floor for add_python_module() targets
# that do not pass python_version=. Keep in sync with pyproject.toml's own
# requires-python floor: CMakeless itself needs at least this version to run.
MIN_PYTHON_VERSION = "3.12"

# Cache variables the emitter always promotes CMAKE_SYSTEM_NAME/PROCESSOR
# into (see cmake_emitter's reflection preamble), because the File API's
# cache object does not reliably carry the originals for a native (non-cross)
# build; cmake_info() reads these two back through that same cache object.
# Shared between the emitter and driver layers, which never import each
# other directly, so the literal lives here instead of being duplicated.
CMAKELESS_SYSTEM_NAME_VAR = "CMAKELESS_SYSTEM_NAME"
CMAKELESS_SYSTEM_PROCESSOR_VAR = "CMAKELESS_SYSTEM_PROCESSOR"
