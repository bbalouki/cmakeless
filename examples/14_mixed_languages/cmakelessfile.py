"""Mixed C and C++ with typed system links: embedded HAL code meets a threaded app.

The C file is detected from its suffix, so the generated project() enables
C next to C++ without being told. Threads and the math library are typed
link targets rather than raw CMake.
"""

from cmakeless import Project, System, When

project = Project("mixed", version="1.0.0", cpp_std=20, c_std=11, warnings="max")
project.warnings_as_errors = True

sensor = project.add_library("sensor", sources=["src/sensor.c"], public_headers="src/")
sensor.link(System.library("m"), when=When.platform("linux"))

app = project.add_executable("mixed", sources=["src/main.cpp"])
app.link(sensor)
app.link(System.threads())

project.build()
