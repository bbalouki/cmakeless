"""Everything that turns "it builds" into "it ships".

Presets give IDEs and the CLI named configurations with their own build
trees; install() and package() replace the most copy-pasted hundred lines
in the CMake ecosystem.

    $ cmakeless build --preset debug      # sanitized development build
    $ cmakeless build --preset release    # optimized, LTO
    $ cmakeless install --prefix dist     # headers, library, Config.cmake
    $ cmakeless package                   # ship_demo-1.0.0-*.zip via CPack
"""

from cmakeless import Preset, Project

project = Project("ship_demo", version="1.0.0", cpp_std=20, warnings="strict")

project.add_preset(Preset("debug", optimize="none", sanitize=["address"]))
project.add_preset(Preset("release", optimize="release", lto=True))

engine = project.add_library(
    "engine",
    sources=["src/engine/*.cpp"],
    public_headers="include/",
)

app = project.add_executable("ship_demo", sources=["src/main.cpp"])
app.link(engine)

# Other CMake users can now find_package(ship_demo) the installed library.
project.install(engine, headers=True)
project.install(app)
project.package(formats=["zip"])

project.build()
