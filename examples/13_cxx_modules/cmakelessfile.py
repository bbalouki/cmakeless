"""C++20 modules: a library whose whole interface is module interface units.

No headers, no include directories, no include guards. The library declares
its module interfaces with modules=[...], the executable imports them by
name, and CMake scans the sources to work out the compile order by itself.

Because this project declares modules, the generated CMakeLists.txt asks for
CMake 3.28 rather than the usual 3.25 floor; a project that declares none is
completely unaffected. Run 'cmakeless doctor' to check this machine first:
modules need CMake 3.28+ and a Ninja or Visual Studio generator.

    $ cmakeless doctor    # is this machine ready for modules?
    $ cmakeless build
"""

from cmakeless import Project

project = Project("modules_demo", version="1.0.0", cpp_std=23, warnings="strict")

# A module-only library: no sources= at all, because a module interface unit
# is both the interface and the implementation.
geometry = project.add_library(
    "geometry",
    modules=["src/geometry.cppm", "src/units.cppm"],
)

app = project.add_executable("modules_demo", sources=["src/main.cpp"])
app.link(geometry)

project.build()
