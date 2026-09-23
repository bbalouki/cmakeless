"""Shared literals with no internal dependencies, safe for any module to import."""

BUILD_SCRIPT_NAME = "cmakelessfile.py"

# The floor emitted in cmake_minimum_required() and checked by 'cmakeless
# doctor'; shared because the driver layer must not import from the emitter
# layer (layers depend only on the layer directly below them).
CMAKE_MINIMUM_VERSION = "3.25"

# The floor a project that declares C++20 module interfaces needs instead:
# target_sources(... FILE_SET CXX_MODULES ...) became a supported, non-
# experimental interface in CMake 3.28. Raised per project, never globally,
# so a project that declares no modules keeps emitting the lower floor.
CXX_MODULES_MINIMUM_VERSION = "3.28"

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
