"""Python and C++ interop: a real C++ extension you can import.

add_python_module() fetches the binding backend (pybind11 by default), builds
the extension against the invoking interpreter's development headers, and after
'cmakeless build' copies the module into this very environment, so it imports
immediately. The C++ here is a small 2D geometry type, Vec2, exposed with
operators, properties, docstrings, and C++ to Python exception translation.

    $ cmakeless build            # or: python cmakelessfile.py
    $ python test_geometry.py    # import geometry; geometry.Vec2(3, 4).length() == 5
"""

from cmakeless import Project

project = Project("geometry_demo", version="1.0.0", cpp_std=17)

# pybind11 is the default binding backend; pass binding="nanobind" to switch.
project.add_python_module("geometry", sources=["src/geometry.cpp"])

project.build()
