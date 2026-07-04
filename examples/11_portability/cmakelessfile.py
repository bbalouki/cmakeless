# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""The portability release: the curated Toolchain gallery, lint, and diagnostics.

Registering a cross toolchain never requires its SDK to be installed; only
building *with* one (via an active --preset) does, so arm_none_eabi() and
ios() are registered unconditionally below. android()/emscripten() need a
real, already-installed SDK to even locate their wrapped toolchain file, so
those two are gated behind the environment variables their own SDKs set,
exactly like a user would do in a real cmakelessfile.py.

    $ python cmakelessfile.py                # builds for the host, as always
    $ cmakeless build --preset arm-none-eabi # only if arm-none-eabi-g++ is on PATH
    $ cmakeless doctor                       # check cmake/generator/ccache/network
    $ cmakeless lock                         # resolve and pin fmt
    $ cmakeless sbom --format spdx           # a bill of materials from cmakeless.lock
    $ cmakeless vendor                       # download fmt for a --offline build
    $ cmakeless build --offline              # resolves fmt from the vendored copy
"""

import os
import shutil

from cmakeless import Preset, Project, Toolchain

project = Project("portable_app", version="1.0.0", cpp_std=20, warnings="strict")

app = project.add_executable("portable_app", sources=["src/main.cpp"])
app.depends("fmt/10.2.1")

project.add_toolchain(Toolchain.arm_none_eabi(cpu="cortex-m4"))
project.add_preset(Preset("arm-none-eabi", toolchain="arm-none-eabi"))
project.add_toolchain(Toolchain.ios(platform="OS64"))
project.add_preset(Preset("ios-device", toolchain="ios-os64"))

if "EMSDK" in os.environ:
    project.add_toolchain(Toolchain.emscripten())
    project.add_preset(Preset("wasm", toolchain="emscripten"))

if ndk := os.environ.get("ANDROID_NDK_HOME"):
    project.add_toolchain(Toolchain.android(ndk=ndk, abi="arm64-v8a"))
    project.add_preset(Preset("android-arm64", toolchain="android-arm64-v8a"))

if shutil.which("clang-tidy"):
    # Bare clang_tidy=True defers entirely to clang-tidy's own defaults
    # (a .clang-tidy file, or none); passing checks explicitly here keeps
    # this example buildable on a machine with no such file checked in.
    project.lint(clang_tidy=["clang-tidy", "-checks=-*,modernize-*,readability-*"])

project.build()
