"""Python and C++ interop: a C++ extension you can import.

add_python_module() fetches the binding backend, builds the extension against
the invoking interpreter's development headers, and after 'cmakeless build'
copies the module into this very environment, so it imports immediately.

    $ cmakeless build          # or: python build.py
    $ python test_mymath.py    # import mymath; mymath.add(2, 3) == 5
"""

from cmakeless import Project

project = Project("mymath_demo", version="1.0.0", cpp_std=17)

# nanobind is the default backend; this example uses pybind11 because its
# release archive fetches cleanly through FetchContent without git submodules.
project.add_python_module("mymath", sources=["src/mymath.cpp"], binding="pybind11")

project.build()
