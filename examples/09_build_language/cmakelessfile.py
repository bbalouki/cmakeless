"""Custom build steps, project options, and When conditions in one project.

Shows the "language unlock" surface: a code-generation step feeding a
target's sources, a declared option gating a preprocessor define, and a
When condition keyed off the active build configuration.
"""

from cmakeless import Project, When

project = Project("build_language_demo", version="1.0.0", cpp_std=20)

verbose = project.option(
    "BUILD_LANGUAGE_VERBOSE", default=False, help="Print extra startup diagnostics"
)

version_source = project.add_command(
    output=["generated/version.cpp"],
    command=[
        "python",
        "tools/gen_version.py",
        "--out",
        "generated/version.cpp",
        "--version",
        "1.0.0",
    ],
    depends=["tools/gen_version.py"],
    comment="Generating version.cpp",
)

app = project.add_executable("build_language_demo", sources=["src/main.cpp"])
app.add_sources(version_source)  # wires the dependency edge; no add_dependencies() needed
app.include_dirs("src")  # so generated/version.cpp can #include "version.hpp"
app.define("BUILD_LANGUAGE_VERBOSE", when=When.option(verbose))
app.define("BUILD_LANGUAGE_RELEASE_BUILD", when=When.config("Release"))

project.build()
