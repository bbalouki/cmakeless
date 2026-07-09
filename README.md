# CMakeless

[![CI](https://github.com/bbalouki/cmakeless/actions/workflows/ci.yml/badge.svg)](https://github.com/bbalouki/cmakeless/actions/workflows/ci.yml)
[![CodeFactor](https://www.codefactor.io/repository/github/bbalouki/cmakeless/badge)](https://www.codefactor.io/repository/github/bbalouki/cmakeless)
[![codecov](https://codecov.io/github/bbalouki/cmakeless/graph/badge.svg?token=BZ4416XX4I)](https://codecov.io/github/bbalouki/cmakeless)
[![PyPI - Status](https://img.shields.io/pypi/status/cmakeless)](https://pypi.org/project/cmakeless/)
[![PyPI Downloads](https://static.pepy.tech/badge/cmakeless)](https://pepy.tech/projects/cmakeless)
[![PyPI version](https://img.shields.io/pypi/v/cmakeless.svg)](https://pypi.org/project/cmakeless/)
[![Python versions](https://img.shields.io/pypi/pyversions/cmakeless.svg)](https://pypi.org/project/cmakeless/)
[![CMake](https://img.shields.io/badge/CMake-3.25+-blue.svg)](https://cmake.org/)
[![C++20](https://img.shields.io/badge/C++-20-blue.svg)](https://isocpp.org/std/the-standard)
[![Typed](https://img.shields.io/badge/typing-strict-brightgreen.svg)](https://peps.python.org/pep-0561/)
[![License: MPL 2.0](https://img.shields.io/badge/License-MPL_2.0-brightgreen.svg)](LICENSE)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-grey?logo=Linkedin&logoColor=white)](https://www.linkedin.com/in/bertin-balouki-s-15b17a1a6)

**Write your C++ build in real Python. CMakeless generates clean, modern `CMakeLists.txt` from it and drives CMake for you, so you get the entire CMake ecosystem, every generator, every toolchain, every IDE, without ever writing the CMake language by hand again.**

> **CMakeless is not a build system.** It never compiles anything, never schedules a single object file, never talks to a compiler directly. CMake and Ninja (or Make, or MSBuild) still do every bit of that work, exactly as they always have. CMakeless's entire job is smaller and more honest than "build system": it is a Python author for CMake's own language, nothing more, nothing less. If you deleted CMakeless tomorrow, your generated `CMakeLists.txt` would keep building. That is not an accident; it is the whole design.

```python
# cmakelessfile.py
from cmakeless import Project

project = Project("hello", version="1.0.0", cpp_std=20)
project.add_executable("hello", sources=["src/main.cpp"])
project.build()
```

```console
$ cmakeless build
```

No `cmake_minimum_required`, no `PARENT_SCOPE`, no semicolon-lists, no guessing whether a variable needs quotes. Make a mistake and you get a Python exception with a real message and a real stack trace, at the moment you made it, not a cryptic configure-time failure three modules deep in someone else's `.cmake` file.

> If you have ever committed a build fix with the message `fix build` and been afraid to touch that file again, keep reading.

---

## Table of contents

- [Why CMakeless exists](#why-cmakeless-exists)
- [The design philosophy](#the-design-philosophy-replace-the-language-keep-the-engine)
- [Why Python, specifically](#why-python-specifically)
- [Install](#install)
- [A concrete, end-to-end workflow](#a-concrete-end-to-end-workflow)
- [Feature tour](#feature-tour)
- [Where CMakeless fits in the ecosystem](#where-cmakeless-fits-in-the-c-build-ecosystem)
- [What CMakeless will not do](#what-cmakeless-will-not-do)
- [FAQ](#faq)
- [Requirements](#requirements)
- [Learn more](#learn-more)

---

## Why CMakeless exists

Every engineering organization that ships C++ has a build file nobody wants to own. It was written years ago, by someone who has since moved on or moved teams, against a CMake version that has since been superseded twice. It works, in the sense that it produces a binary, and it is untouchable, in the sense that everyone who reads it decides the risk of understanding it exceeds the risk of leaving it alone. That file is now a permanent tax on every future change to the project: not because C++ is hard, and not because the underlying problem (compile these files, link them, find these dependencies) is hard, but because the *language* the instructions are written in actively resists being read, changed, or trusted.

This is not a rare, unlucky project. It is close to universal, and it is close to invisible, precisely because nobody files a bug against "the build is annoying." They just quietly route around it: they copy a `CMakeLists.txt` from another repository instead of writing one, they avoid touching the parts they do not understand, they let one person become the build's unofficial priesthood. Multiply the hours lost to that avoidance across every C++ team on earth, and you are looking at one of the largest, least-tracked drains on engineering time in the industry, hidden precisely because everyone assumes it is just how build systems are.

It does not have to be. CMake, the engine, is not the problem: it configures builds for every compiler, every platform, and every IDE that matters, and the entire C++ ecosystem, vcpkg, Conan, CLion, Visual Studio, thousands of libraries, already agreed to speak it. The problem is narrower and more fixable than "CMake is bad": it is that CMake's own scripting language, the thing you actually type, was never designed as a language for humans to hold complex logic in their heads. Strings stand in for lists, booleans, and everything else. Scope leaks upward only through `PARENT_SCOPE` and leaks nowhere else. A function cannot return a value; it can only mutate a magically-named variable in its caller's frame. None of this is a hot take. It has been the consistent, decade-long complaint of everyone who has had to write it, and the complaint has never been "CMake does the wrong thing." It has always been "CMake makes me say the right thing in the wrong language."

**CMakeless exists to give that language back to you, in a form you already trust.**

## The design philosophy: replace the language, keep the engine

Every prior attempt to fix this pain, Meson, xmake, premake, Bazel, made the same bet: replace CMake entirely, engine and all. They are capable tools, and every one of them asks you to walk away from the largest build ecosystem in C++, the vcpkg and Conan registries, the IDEs with native CMake support, the countless libraries whose only supported build path is a `CMakeLists.txt`. That is an enormous price, which is exactly why, after a decade of genuinely good alternatives, CMake still runs most of the C++ world. People are not choosing CMake's language. They are choosing not to pay that price.

CMakeless takes the other bet, the one nobody else was making:

> **CMake is not the enemy. Writing CMake is.**

The name is the whole idea, spelled out: the way *serverless* computing does not mean the servers vanished, it means you stopped thinking about them, *CMakeless* does not mean CMake vanished. It means you stop authoring it directly. The engine stays exactly where it was, doing exactly what it already does well. What changes is the language you use to tell it what to do, and the moment at which your mistakes get caught.

Four commitments follow from that bet, and they are the ones this project is judged against:

1. **A tiny API you can hold in your head.** `Project`, `Executable`, `Library`, `Test`, `PythonModule`, `Preset`, `Toolchain`, and a handful of supporting types. If using CMakeless requires the documentation open in a permanent browser tab the way raw CMake does, the project has failed at its one job.
2. **Fail early, fail in Python.** Every mistake that can be caught before CMake ever runs, a typo in a C++ standard, a missing source file, a dependency cycle, is caught in Python, with a real stack trace pointing at your own `cmakelessfile.py`, not three layers into a `.cmake` include chain.
3. **Boring, readable output.** The generated `CMakeLists.txt` is modern, target-centric, deterministic, and clean enough to commit and hand to a stranger. Walking away from CMakeless later must be a boring afternoon of deleting one file, never a migration project.
4. **Delegate, never reimplement.** CMake configures, generates, and builds. CMakeless is a frontend that describes intent; it is not, and will never become, a competing build system. (See the callout above; it is worth saying twice.)

## Why Python, specifically

Because for a C++ team, Python is not a new dependency to justify. It is already there.

- **Your team already knows it.** Python is the de facto second language of nearly every C++ organization: it already runs the test scripts, the code generators, the CI glue, the release tooling. Choosing Python as the build description language adds nothing new to learn; it reuses knowledge your team already paid for.
- **A real language beats a bespoke one, every time.** A YAML dialect or a hand-rolled DSL would need its own conditionals, its own loops, its own way to read an environment variable, reinvented badly and forever incompletely. Python already has all of that, debugged by a language community two decades larger than any build tool's userbase will ever be. `cmakelessfile.py` is not a new format to learn: it is a plain Python script that happens to import `cmakeless`.
- **The interop story writes itself.** pybind11 and nanobind already made Python bindings a routine part of serious C++ projects. When the tool building your C++ is already running inside the interpreter that will import it, `project.add_python_module("core")` stops being a page of hand-written glue and becomes one call, because there is no boundary left to cross.
- **Real tooling, for free.** Autocomplete on every method. Type checking on every argument, because CMakeless ships `py.typed` and is checked with mypy in strict mode. A debugger you can actually attach, with `breakpoint()` working exactly where you put it. Unit tests for your own build logic, if it grows complex enough to deserve them. None of this exists for the CMake language, and none of it ever will, because CMake's language was never built to support it.
- **Built for where Python is actually going.** Free-threaded Python (PEP 703, non-experimental since 3.14) removes the GIL as a ceiling on I/O-heavy work, and dependency resolution and multi-preset configuration are exactly that: many independent, mostly-waiting operations. CMakeless is built to exploit that without asking you to think about threads at all; see [benchmarks](docs/benchmarks.md) for measured numbers, not a marketing claim.

To be precise about what this is not: scikit-build-core and meson-python solve the mirror-image problem, using CMake or Meson to package a Python extension for distribution. CMakeless is for building C++ projects, full stop; when a C++ project happens to also ship Python bindings, that is one more thing CMakeless generates for you, not the point of the tool. Python here is the pen you write with. It was never meant to be the product.

---

## Install

```console
$ pip install cmakeless
```

Requirements: Python 3.12+ and CMake 3.25+ on `PATH` (CMake is needed only to actually build; generating `CMakeLists.txt` works without it, one narrow exception noted in the [FAQ](#faq)).

Scaffold a new project in one command:

```console
$ cmakeless init
```

---

## A concrete, end-to-end workflow

Here is what a real project looks like as it grows, from a single file to a shippable, tested, Python-importable library. Every step is a few lines of `cmakelessfile.py`, and every verb is one `cmakeless` command.

### 1. Start with an executable and a library

```python
# cmakelessfile.py
from cmakeless import Project

project = Project("mygame", version="1.0.0", cpp_std=23, warnings="strict")

engine = project.add_library(
    "engine",
    sources=["src/engine/*.cpp"],   # globs expand in Python and are validated
    public_headers="include/",
    kind="static",                  # "static" | "shared" | "header_only"
)

app = project.add_executable("mygame", sources=["src/main.cpp"])
app.link(engine)                    # visibility inferred; no PUBLIC/PRIVATE guessing

project.build()
```

```console
$ cmakeless build
```

### 2. Add a dependency in one line

```python
app.depends("fmt/10.2.1")           # find_package first, else FetchContent, pinned in cmakeless.lock
```

CMakeless remembers that the target is `fmt::fmt`, not `fmt`, writes a lockfile so CI and teammates get byte-identical trees, and can generate a `vcpkg.json` or `conanfile.txt` if you opt into a package manager.

### 3. Test as a first-class verb (GoogleTest by default)

```python
tests = project.add_test("engine_tests", sources=["tests/*.cpp"])   # framework="gtest" by default
tests.link(engine)
```

```console
$ cmakeless test                       # fetches GoogleTest, registers every case with CTest, runs them
$ cmakeless test --sanitize=address    # the same suite in a sanitized build tree
```

Prefer Catch2 or doctest? Pass `framework="catch2"` or `framework="doctest"`.

### 4. Ship Python bindings (pybind11 by default)

```python
bindings = project.add_python_module("mygame_core", sources=["src/bindings.cpp"])  # binding="pybind11"
bindings.link(engine)
```

```console
$ cmakeless build
$ python -c "import mygame_core; print(mygame_core.__doc__)"
```

CMakeless locates the invoking interpreter's development headers, fetches pybind11 (or nanobind, with `binding="nanobind"`, which also gets `.pyi` stubs), builds the extension, and copies it into your current environment, so `import` just works. **This is the flagship of the whole idea.**

The generated `find_package(Python ...)` floor defaults to CMakeless's own supported Python version, not whichever interpreter happens to run `cmakeless`, so the same `cmakelessfile.py` always emits the same `CMakeLists.txt`, on any machine. Pass `python_version="3.13"` to `add_python_module(...)` to raise it.

### 5. Configurations, install, and package

```python
from cmakeless import Preset

project.add_preset(Preset("debug", optimize="none", sanitize=["address"]))
project.add_preset(Preset("release", optimize="release", lto=True))
project.add_preset(Preset("ci", inherits="release", options={"MYGAME_BUILD_TOOLS": False}))

project.install(engine, headers=True)   # export set + Config.cmake, so others can find_package(mygame)
project.install(app)
project.package(formats=["zip", "deb"]) # CPack
```

```console
$ cmakeless build --preset release      # from a generated CMakePresets.json, its own build tree
$ cmakeless install --prefix dist       # GNUInstallDirs-correct layout
$ cmakeless package                      # CPack archives
```

Prefer a project-wide default without presets? Set them right on the project:

```python
project.optimize = "release"
project.lto = True
```

### 6. Commit the output, walk away any time

`compile_commands.json` always lands at the project root (clangd, clang-tidy, and every editor just work), and `ccache`/`sccache` is wired in automatically when found. The generated `CMakeLists.txt` is honest, standalone CMake: commit it, open it in CLion or Visual Studio, or delete CMakeless entirely. Your build keeps working either way, because `cmakeless build` and `python cmakelessfile.py` both do nothing more than emit that file and hand it to CMake; the file was always the real artifact.

---

## Feature tour

| You write (Python)                                                             | We handle (the CMake ritual you skip)                                                               |
| ------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------- |
| `project.add_library(..., kind="shared")`                                      | `add_library`, PIC, `__declspec(dllexport)` export headers, visibility                              |
| `app.link(engine)` / `lib.link(dep, public=True)`                              | the correct `PUBLIC`/`PRIVATE`/`INTERFACE` keyword, every time                                      |
| `app.depends("fmt/10.2.1")`                                                    | `find_package`-then-`FetchContent` fallback, pinned hashes, `cmakeless.lock`, vcpkg/Conan manifests |
| `project.warnings = "strict"`                                                  | `/W4 /permissive-` on MSVC, `-Wall -Wextra -Wconversion ...` on GCC/Clang                           |
| `target.sanitize = ["address"]`                                                | sanitizer flags on **both** compile and link, per-compiler, rejected loudly where unsupported       |
| `project.add_test(...)`                                                        | GoogleTest/Catch2/doctest fetch, `enable_testing()`, per-case CTest discovery, Windows DLL paths    |
| `project.add_python_module(...)`                                               | pybind11/nanobind fetch, `find_package(Python)`, `<backend>_add_module`, stubs, env install         |
| `project.add_preset(Preset(..., options=, env=, inherits=))`                   | `CMakePresets.json`, per-preset out-of-source build trees, multi-config support                     |
| `app.link_options(...)` / `When.compiler(...)`                                 | `target_link_options`, generator-expression guards, no manual `$<...>` syntax                       |
| `project.option(...)` / `cmakeless options`                                    | `option()`/`set(... CACHE ...)`, discoverable without reading the script                             |
| `project.add_command(...)` / `add_custom_target(...)`                          | `add_custom_command(OUTPUT ...)`/`add_custom_target` wiring, argv-safe (`VERBATIM`)                 |
| `project.install(...)` / `project.package(...)`                                | `install(TARGETS ...)`, export sets, `Config.cmake`, version files, CPack                           |
| `project.include(...)` / `project.include_module(...)`                         | reflecting a `.cmake` file or module through real CMake, never a hand-written parser                |
| `project.cmake_globals()`                                                      | any CMake variable (`WIN32`, `ANDROID`, `CMAKE_CXX_COMPILER_ID`, ...) as `hasattr(cmake, ...)`       |
| `Toolchain.arm_none_eabi()` / `.ios()` / `.android(ndk=...)` / `.emscripten()` | a curated cross-compilation toolchain gallery, each validated with a helpful error                  |
| `project.lint(clang_tidy=True)` / `target.lint(...)`                           | `CXX_CLANG_TIDY`/`CXX_INCLUDE_WHAT_YOU_USE`, project-wide with a per-target override                |
| `cmakeless sbom` / `cmakeless vendor` / `--offline`                            | a CycloneDX/SPDX bill of materials, dependency vendoring, and zero-network builds                   |
| `cmakeless doctor`                                                             | one command checking cmake/generator/ccache/vcpkg/Conan/network, no project needed                  |
| `target.raw_cmake("...")` / `project.raw_cmake_file("...")`                    | the escape hatch: verbatim CMake, fenced with its `cmakelessfile.py` origin                         |

Watch progress through the Observer API, read the configured build as Python objects via the CMake File API, and query any CMake variable before you have emitted a single line:

```python
from cmakeless import Observer, Project, StepFinished

class Timer:
    def on_event(self, event):
        if isinstance(event, StepFinished):
            print(f"{event.step} finished ({event.exit_code})")

project = Project("app", cpp_std=20)
project.add_executable("app", sources=["src/main.cpp"])
project.add_observer(Timer())

for target in project.targets_info():        # read from CMake's File API, not scraped text
    print(target.name, target.type, target.artifacts)

info = project.cmake_info()                  # the resolved generator, compiler, and system
print(info.generator, info.system_name, [c.compiler_id for c in info.compilers])

cmake = project.cmake_globals()              # any CMake variable, at description time
if hasattr(cmake, "ANDROID"):                # mirrors CMake's if(DEFINED ANDROID)
    app.link(android_only_dependency)
```

The full before/after catalog lives in [FEATURES](docs/FEATURES.md).

## Where CMakeless fits in the C++ build ecosystem

| Tool                             | Approach                                   | You keep the CMake ecosystem? |
| --------------------------------- | ------------------------------------------- | ------------------------------ |
| **CMakeless**                    | Python frontend that generates CMake       | **Yes, entirely**             |
| Raw CMake                        | Write the CMake language by hand           | Yes                           |
| Meson / xmake / premake          | Replace CMake with a new build system      | No                             |
| Bazel                            | Replace with a hermetic build system       | No                             |
| scikit-build-core / meson-python | Use CMake/Meson to build _Python_ packages | Reverse problem               |

CMakeless is the only one of these that keeps 100% of the CMake ecosystem while removing the CMake language. If a tool understands CMake, it understands your CMakeless project, because the output _is_ CMake, not a translation of it.

## What CMakeless will not do

Boundaries, stated as promises, not limitations we hope to lift later:

- **It will not become a build system.** Compilation scheduling, incremental rebuilds, and dependency graphs between object files belong to CMake and Ninja, permanently. CMakeless describes intent; it never touches a compiler.
- **It will not invent a DSL.** `cmakelessfile.py` is plain Python, forever. Any proposal that adds CMakeless-only semantics to Python syntax is rejected on arrival.
- **It will not hold your project hostage.** The generated CMake is readable, committable, and standalone. Leaving must always be boring.

## FAQ

**Is this production-ready?**
CMakeless is in beta: pre-1.0, but no longer an unstable sketch. The public API is stabilizing and the pipeline is exercised by a real test suite and CI on all three major OSes, but the API can still change without a full deprecation cycle until v1.0 ships (see the [roadmap](docs/ROADMAP.md#phase-56-v10-the-stability-promise-v100-productionstable)). If you need long-term stability today, pin the exact version and read `CHANGELOG.md` before upgrading.

**Why not just use Meson, Bazel, or xmake?**
Because you would be leaving the CMake ecosystem behind: vcpkg, Conan, every IDE, every CI action, every existing library's build. CMakeless keeps all of that and only replaces the part everyone actually hates: writing the CMake language by hand.

**Does this only work with Ninja and Clang, or does it support MSVC/Visual Studio too?**
CMake's generator selection is untouched. CMakeless drives whichever generator CMake supports on your platform (Ninja, Visual Studio, Makefiles). MSVC works like any other CMake-driven MSVC project.

**Can I still hand-edit the generated `CMakeLists.txt`?**
You can, but the point is you should not have to. It regenerates from your `cmakelessfile.py` on every build, so hand edits get silently overwritten. Use `target.raw_cmake(...)` or `project.raw_cmake_file(...)` for anything the API does not model yet.

**How is this different from scikit-build-core or meson-python?**
Those solve the reverse problem: using CMake or Meson to build a _Python package_ that happens to contain C++. CMakeless is for C++ projects, full stop; Python is the authoring language, not the packaging target.

**Do I need CMake installed?**
To build, yes: CMake 3.25+ on `PATH`, same as any CMake project. Generating `CMakeLists.txt` from a `cmakelessfile.py` works without CMake present at all, with one exception: `project.include(...)`/`project.include_module(...)`/`project.cmake_globals(...)` reflect real CMake behavior by running it the moment they are called, since there is no other honest way to know what a `.cmake` file defines, or what a given platform sets, without asking CMake directly. A script that never calls any of them still generates without CMake.

**What happens if I stop using CMakeless later?**
Delete it. The generated `CMakeLists.txt` is standalone, readable, modern CMake with no CMakeless runtime dependency. Commit it and walk away.

## Requirements

- Python 3.12+
- CMake 3.25+ on `PATH` (only for building; generation works without it)

## Learn more

- [INTRODUCTION](docs/INTRODUCTION.md): The full story of why CMakeless exists.
- [FEATURES](docs/FEATURES.md): Everything it does for you, with before/after comparisons against raw CMake.
- [ARCHITECTURE](docs/ARCHITECTURE.md): How it is designed, layer by layer.
- [ROADMAP](docs/ROADMAP.md): Where it is going.
- [Tutorial](docs/tutorial.md): A ten-minute, linear walkthrough for a first project.
- [Cookbook](docs/cookbook.md): Task-oriented recipes for common jobs.
- [Migration guide](docs/migration.md): Bringing CMakeless into a project that already has a hand-written `CMakeLists.txt`.
- [Benchmarks](docs/benchmarks.md): Measured free-threaded parallelism wins, with the method.
- [CONTRIBUTING](CONTRIBUTING.md): Why your scars from CMake make you exactly the contributor we need.
- [Examples](examples/): Smallest first, up to a full real-world capstone.

Your build script should be the most boring file in your repository. Let us make it boring together.

## License

MPL-2.0. See [LICENSE](LICENSE).
