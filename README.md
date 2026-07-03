# CMakeless

**Write your C++ builds in Python. Keep CMake. Lose the pain.**

CMakeless is a pure Python frontend for CMake. You describe your build in real Python, CMakeless validates it, generates clean, modern, human-readable CMake, and drives the CMake engine for you. Every generator, toolchain, IDE, and library that works with CMake keeps working, because underneath, it *is* CMake.

```python
# build.py
from cmakeless import Project

project = Project("hello", version="1.0.0", cpp_std=20)
project.add_executable("hello", sources=["src/main.cpp"])
project.build()
```

```console
$ python build.py     # or: cmakeless build
```

It does not stop at building. Tests, sanitizers, presets, install rules,
and packaging are one call each:

```python
from cmakeless import Preset, Project

project = Project("mygame", version="1.0.0", cpp_std=23)
engine = project.add_library("engine", sources=["src/engine/*.cpp"], public_headers="include/")

tests = project.add_test("engine_tests", sources=["tests/*.cpp"], framework="catch2")
tests.link(engine)

project.add_preset(Preset("debug", optimize="none", sanitize=["address"]))
project.add_preset(Preset("release", optimize="release", lto=True))

project.install(engine, headers=True)   # export set + Config.cmake included
project.package(formats=["zip"])
project.build()
```

```console
$ cmakeless test                        # CTest, per-case discovery
$ cmakeless test --sanitize=address     # same suite, sanitized build tree
$ cmakeless build --preset release      # CMakePresets.json, own build tree
$ cmakeless install --prefix dist       # GNUInstallDirs-correct layout
$ cmakeless package                     # CPack archives
```

`compile_commands.json` always lands at the project root, and ccache or
sccache is wired in automatically when found.

## Python and C++ interop

Build a C++ extension and import it from the very interpreter that built it:

```python
from cmakeless import Project

project = Project("mymath_demo", version="1.0.0", cpp_std=17)
project.add_python_module("mymath", sources=["src/mymath.cpp"], binding="pybind11")
project.build()
```

```console
$ python build.py
$ python -c "import mymath; print(mymath.add(2, 3))"   # 5
```

CMakeless fetches nanobind or pybind11, builds against the invoking
interpreter's headers, generates `.pyi` stubs (nanobind), and copies the
module into your environment, so the import just works.

## Progress events and structured build info

Watch every step through the Observer API, and read the configured build as
Python objects via the CMake File API:

```python
from cmakeless import Observer, Project, StepFinished

class Timer:
    def on_event(self, event):
        if isinstance(event, StepFinished):
            print(f"{event.step} finished ({event.exit_code})")

project = Project("app", cpp_std=20)
project.add_executable("app", sources=["src/main.cpp"])
project.add_observer(Timer())

for target in project.targets_info():        # from CMake's File API
    print(target.name, target.type, target.artifacts)
```

Configuring several presets at once runs concurrently on free-threaded Python;
the [benchmarks](benchmarks/) publish the measured wins.

## Requirements

- Python 3.13+
- CMake 3.25+ on PATH (only for building; generation works without it)

## Install

```console
$ pip install cmakeless
```

To scaffold a new project:

```console
$ cmakeless init
```

## Learn more

- [INTRODUCTION](INTRODUCTION.md): Why CMakeless exists.
- [FEATURES](FEATURES.md): Everything it does for you, with before/after comparisons.
- [ARCHITECTURE](ARCHITECTURE.md): How it is designed, layer by layer.
- [ROADMAP](ROADMAP.md): Where it is going.
- [Benchmarks](docs/benchmarks.md): Measured parallelism wins, with the method.
- [CONTRIBUTING](CONTRIBUTING.md): Why your scars from CMake make you exactly the contributor we need.

Runnable examples live in [examples/](examples/), smallest first.

