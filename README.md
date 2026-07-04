# CMakeless

[![CI](https://github.com/bbalouki/cmakeless/actions/workflows/ci.yml/badge.svg)](https://github.com/bbalouki/cmakeless/actions/workflows/ci.yml)
[![CodeFactor](https://www.codefactor.io/repository/github/bbalouki/cmakeless/badge)](https://www.codefactor.io/repository/github/bbalouki/cmakeless)
[![PyPI version](https://img.shields.io/pypi/v/cmakeless.svg)](https://pypi.org/project/cmakeless/)
[![Python versions](https://img.shields.io/pypi/pyversions/cmakeless.svg)](https://pypi.org/project/cmakeless/)
[![License: MPL 2.0](https://img.shields.io/badge/License-MPL_2.0-brightgreen.svg)](LICENSE)
[![Typed](https://img.shields.io/badge/typing-strict-brightgreen.svg)](https://peps.python.org/pep-0561/)

**CMakeless is a pure-Python frontend for CMake: a modern CMake alternative that lets you describe C++ builds in real Python instead of the CMake language, then generates clean, human-readable `CMakeLists.txt` and drives CMake for you.**

You get the entire CMake ecosystem, every generator, toolchain, IDE, and library, without ever writing CMake by hand again.

```python
# cmakelessfile.py
from cmakeless import Project

project = Project("hello", version="1.0.0", cpp_std=20)
project.add_executable("hello", sources=["src/main.cpp"])
project.build()
```

```console
$ python cmakelessfile.py   # or: cmakeless build
```

That is a complete, cross-platform C++ build. No `cmake_minimum_required`, no `PARENT_SCOPE`, no semicolon-lists, no guessing whether a variable needs quotes. If you make a mistake, you get a Python exception with a real message, at author time, not a cryptic configure-time failure three modules deep.

> If you have ever committed a build fix with the message `fix build` and been afraid to touch the file again, this project is for you.

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

Let us be honest and precise, because CMake deserves both.

The CMake **engine** is a marvel. It configures builds for every compiler, every platform, and every IDE that matters. It is the de facto standard of the C++ world: vcpkg, Conan, CLion, Visual Studio, and thousands of libraries all agree on it. Nobody sane wants to rebuild that.

The CMake **language** is another story. It is the single most criticized part of the C++ toolchain, and the complaints have been remarkably consistent for over a decade:

- **Everything is a string.** No integers, no booleans, no real lists. A "list" is a string with semicolons in it, and you discover the difference between `"a b c"` and `a b c` at configure time, or worse, at link time.
- **Scoping is a trap.** Variables have dynamic scope and flow into subdirectories but not back out, unless you reach for `PARENT_SCOPE`. Functions cannot return a value; they set magic variables in the caller's scope.
- **The syntax cannot be memorized.** Is it `target_link_libraries(app PRIVATE fmt)` or `target_link_libraries(app fmt)`? When do you need `PUBLIC` vs `PRIVATE` vs `INTERFACE`? Fifteen-year veterans keep the docs open in a permanent tab.
- **You cannot debug it.** There is no breakpoint. There is `message(STATUS "WHY: ${VAR}")` sprinkled through your build like archaeological evidence of past suffering.
- **Twenty years of legacy never dies.** Every historical mistake lives on behind a policy flag. "Modern CMake" is a genuinely good set of ideas that most projects never adopted, because the old examples still rank first in search results.

None of this is controversial. People do not use the CMake language because they enjoy it; they use it because they feel they have no choice.

**CMakeless gives you the choice.**

## The design philosophy: replace the language, keep the engine

Every previous attempt to fix this pain, Meson, xmake, premake, Bazel, tried to replace CMake entirely. All capable tools, and all of them ask you to walk away from the largest build ecosystem in C++. That price is why they remain the exception, not the rule.

CMakeless takes the opposite bet:

> **CMake is not the enemy. Writing CMake is.**

Like *serverless*, where the servers never went away, *CMakeless* still has CMake at its core. You just never write it again. Four principles hold the line:

1. **A tiny API you can hold in your head.** A handful of classes: `Project`, `Executable`, `Library`, `Test`, `PythonModule`, `Preset`, `Toolchain`. If you need the documentation open in a permanent tab, we have failed.
2. **Fail early, fail in Python.** Every error that can be caught before CMake runs is caught before CMake runs, and reported as a normal Python exception with a helpful message.
3. **Boring, readable output.** The generated `CMakeLists.txt` is modern, target-centric, deterministic, and diffable, clean enough to commit and to leave behind. Deleting CMakeless must always be a boring afternoon, never a migration project.
4. **Delegate, never reimplement.** CMake configures, generates, and builds. CMakeless is a frontend, not a build system.

## Why Python, specifically

Because C++ and Python have been best friends for years.

- **Your team already knows it.** Python is the second language of nearly every C++ shop: it runs your test scripts, your code generators, your CI glue. There is nothing new to learn.
- **The interop story is already written.** pybind11 and nanobind made Python bindings a standard part of serious C++ projects. A Python-native build frontend turns `add_python_module("core")` into a one-liner instead of a page of ritual, and the tool that builds your C++ is already inside the interpreter that will import it.
- **Real tooling, for free.** Autocomplete on every function. Type checking on every argument. `breakpoint()` inside your build script. Unit tests for your build logic. Things the CMake language will never have.
- **Built for the free-threaded future.** On a free-threaded interpreter, dependency resolution and multi-preset configuration run in parallel threads with no GIL in the way, and degrade gracefully everywhere else.

To be clear about what CMakeless is *not*: scikit-build-core and meson-python solve the reverse problem, using CMake to build Python packages. CMakeless is for C++ projects, full stop. Python is the pen, not the product.

---

## Install

```console
$ pip install cmakeless
```

Requirements: Python 3.12+ and CMake 3.25+ on `PATH` (CMake is needed only to build; generating `CMakeLists.txt` works without it).

Scaffold a new project in one command:

```console
$ cmakeless init
```

---

## A concrete, end-to-end workflow

Here is what a real project looks like as it grows, from a single file to a shippable, tested, Python-importable library. Every step is a few lines of `cmakelessfile.py`, and every verb is one command.

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

The generated `find_package(Python ...)` floor defaults to CMakeless's own supported Python version, not whichever interpreter happens to run `cmakeless` — so the same `cmakelessfile.py` always emits the same `CMakeLists.txt`, on any machine. Pass `python_version="3.13"` to `add_python_module(...)` to raise it.

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

`compile_commands.json` always lands at the project root (clangd, clang-tidy, and every editor just work), and `ccache`/`sccache` is wired in automatically when found. The generated `CMakeLists.txt` is honest, standalone CMake: commit it, open it in CLion or Visual Studio, or delete CMakeless entirely. Your build keeps working either way.

---

## Feature tour

| You write (Python) | We handle (the CMake ritual you skip) |
|---|---|
| `project.add_library(..., kind="shared")` | `add_library`, PIC, `__declspec(dllexport)` export headers, visibility |
| `app.link(engine)` / `lib.link(dep, public=True)` | the correct `PUBLIC`/`PRIVATE`/`INTERFACE` keyword, every time |
| `app.depends("fmt/10.2.1")` | `find_package`-then-`FetchContent` fallback, pinned hashes, `cmakeless.lock`, vcpkg/Conan manifests |
| `project.warnings = "strict"` | `/W4 /permissive-` on MSVC, `-Wall -Wextra -Wconversion ...` on GCC/Clang |
| `target.sanitize = ["address"]` | sanitizer flags on **both** compile and link, per-compiler, rejected loudly where unsupported |
| `project.add_test(...)` | GoogleTest/Catch2/doctest fetch, `enable_testing()`, per-case CTest discovery, Windows DLL paths |
| `project.add_python_module(...)` | pybind11/nanobind fetch, `find_package(Python)`, `<backend>_add_module`, stubs, env install |
| `project.add_preset(Preset(..., options=, env=, inherits=))` | `CMakePresets.json`, per-preset out-of-source build trees, multi-config support |
| `app.link_options(...)` / `When.compiler(...)` | `target_link_options`, generator-expression guards, no manual `$<...>` syntax |
| `project.option(...)` / `cmakeless options` | `option()`/`set(... CACHE ...)`, discoverable without reading the script |
| `project.add_command(...)` / `add_custom_target(...)` | `add_custom_command(OUTPUT ...)`/`add_custom_target` wiring, argv-safe (`VERBATIM`) |
| `project.install(...)` / `project.package(...)` | `install(TARGETS ...)`, export sets, `Config.cmake`, version files, CPack |
| `project.include(...)` / `project.include_module(...)` | reflecting a `.cmake` file or module through real CMake, never a hand-written parser |
| `target.raw_cmake("...")` / `project.raw_cmake_file("...")` | the escape hatch: verbatim CMake, fenced with its `cmakelessfile.py` origin |

Watch progress through the Observer API, and read the configured build as Python objects via the CMake File API:

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
```

The full before/after catalog lives in [FEATURES.md](FEATURES.md).

## Where CMakeless fits in the C++ build ecosystem

| Tool | Approach | You keep the CMake ecosystem? |
|---|---|---|
| **CMakeless** | Python frontend that generates CMake | **Yes, entirely** |
| Raw CMake | Write the CMake language by hand | Yes |
| Meson / xmake / premake | Replace CMake with a new build system | No |
| Bazel | Replace with a hermetic build system | No |
| scikit-build-core / meson-python | Use CMake/Meson to build *Python* packages | Reverse problem |

CMakeless is the only one of these that keeps 100% of the CMake ecosystem while removing the CMake language. If a tool understands CMake, it understands your CMakeless project, because the output *is* CMake.

## What CMakeless will not do

Boundaries, stated as promises:

- **It will not become a build system.** Compilation, incremental rebuilds, and object-file graphs belong to CMake and Ninja, which are better at it than anything we would write.
- **It will not invent a DSL.** `cmakelessfile.py` is plain Python forever.
- **It will not hold your project hostage.** The generated CMake is readable, committable, and standalone. Leaving must always be boring.

## FAQ

**Is this production-ready?**
No. CMakeless is pre-1.0, alpha software. The API can still change without a deprecation cycle. If you need stability today, pin the exact version and read the changelog before upgrading.

**Why not just use Meson, Bazel, or xmake?**
Because you would be leaving the CMake ecosystem behind: vcpkg, Conan, every IDE, every CI action, every existing library's build. CMakeless keeps all of that and only replaces the part everyone actually hates: writing the CMake language by hand.

**Does this only work with Ninja and Clang, or does it support MSVC/Visual Studio too?**
CMake's generator selection is untouched. CMakeless drives whichever generator CMake supports on your platform (Ninja, Visual Studio, Makefiles). MSVC works like any other CMake-driven MSVC project.

**Can I still hand-edit the generated `CMakeLists.txt`?**
You can, but the point is you should not have to. It regenerates from your `cmakelessfile.py` on every build, so hand edits get silently overwritten. Use `target.raw_cmake(...)` or `project.raw_cmake_file(...)` for anything the API does not model yet.

**How is this different from scikit-build-core or meson-python?**
Those solve the reverse problem: using CMake or Meson to build a *Python package* that happens to contain C++. CMakeless is for C++ projects, full stop; Python is the authoring language, not the packaging target.

**Do I need CMake installed?**
To build, yes: CMake 3.25+ on `PATH`, same as any CMake project. Generating `CMakeLists.txt` from a `cmakelessfile.py` works without CMake present at all — with one exception: `project.include(...)`/`project.include_module(...)` reflect a `.cmake` file or module by running real CMake the moment they are called, since there is no other honest way to know what it defines. A script that never calls either still generates without CMake.

**What happens if I stop using CMakeless later?**
Delete it. The generated `CMakeLists.txt` is standalone, readable, modern CMake with no CMakeless runtime dependency. Commit it and walk away.

## Requirements

- Python 3.12+
- CMake 3.25+ on `PATH` (only for building; generation works without it)

## Learn more

- [INTRODUCTION.md](INTRODUCTION.md): the full story of why CMakeless exists.
- [FEATURES.md](FEATURES.md): everything it does for you, with before/after comparisons against raw CMake.
- [ARCHITECTURE.md](ARCHITECTURE.md): how it is designed, layer by layer.
- [ROADMAP.md](ROADMAP.md): where it is going.
- [docs/benchmarks.md](docs/benchmarks.md): measured free-threaded parallelism wins, with the method.
- [CONTRIBUTING.md](CONTRIBUTING.md): why your scars from CMake make you exactly the contributor we need.
- Runnable [examples/](examples/), smallest first, up to a full real-world capstone.

Your build script should be the most boring file in your repository. Let us make it boring together.

## License

MIT. See [LICENSE](LICENSE).
