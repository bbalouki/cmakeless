"""A static library with public headers, linked into an executable.

Shows glob sources, strict warnings, and preprocessor defines.
"""

from cmakeless import Project

project = Project("mygame", version="1.0.0", cpp_std=23, warnings="strict")

engine = project.add_library(
    "engine",
    sources=["src/engine/*.cpp"],
    public_headers="include/",
    kind="static",
)
engine.define("GAME_MAX_PLAYERS", 8)

app = project.add_executable("mygame", sources=["src/main.cpp"])
app.link(engine)

project.build()
