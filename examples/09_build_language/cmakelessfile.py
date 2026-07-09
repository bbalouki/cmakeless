# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Custom build steps, project options, When conditions, and presets, together.

Shows the full "language unlock" surface: a code-generation step feeding a
target's sources, an always-run asset-cooking step, a declared option gating
a preprocessor define, When conditions keyed off the build configuration,
the target platform, and the compiler, a precompiled header and a unity
build, and a release/ci preset pair that overrides an option and sets an
environment variable.

    $ cmakeless build                # default (no-preset) build
    $ cmakeless build --preset ci    # BUILD_LANGUAGE_VERBOSE forced on, CI=1
"""

from cmakeless import Preset, Project, When

project = Project("build_language_demo", version="1.0.0", cpp_std=20)

verbose = project.option(
    "BUILD_LANGUAGE_VERBOSE", default=False, help="Print extra startup diagnostics"
)

project.add_preset(Preset("release", optimize="release", options={"BUILD_LANGUAGE_VERBOSE": False}))
project.add_preset(
    Preset(
        "ci",
        inherits="release",
        options={"BUILD_LANGUAGE_VERBOSE": True},
        env={"CI": "1"},
    )
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

# An always-run target: no OUTPUT, so it reruns every build (asset cooking,
# lint, docs). A real project would resize/pack images here.
project.add_custom_target(
    "cook-assets",
    command=["python", "tools/cook_assets.py", "assets/manifest.txt"],
    depends=["tools/cook_assets.py", "assets/manifest.txt"],
)

app = project.add_executable("build_language_demo", sources=["src/main.cpp"])
app.add_sources(version_source)  # wires the dependency edge; no add_dependencies() needed
app.include_dirs("src")  # so generated/version.cpp can #include "version.hpp"
app.pch = ["<cstdlib>", "<iostream>"]
app.unity = True
app.define("BUILD_LANGUAGE_VERBOSE", when=When.option(verbose))
app.define("BUILD_LANGUAGE_RELEASE_BUILD", when=When.config("Release"))
app.define("BUILD_LANGUAGE_WINDOWS", when=When.platform("windows"))
app.link_options("-Wl,--as-needed", when=When.compiler("gcc"))  # a GNU ld flag, skipped elsewhere

project.build()
