# CMakeless Documentation

Write your C++ builds in Python. Keep CMake. Lose the pain.

The documentation lives in the pages below: the narrative docs (introduction, features,
architecture, roadmap), a tutorial and cookbook for hands-on tasks, a migration guide for
existing CMake projects, and an [API reference](reference/cmakeless/index.md) generated straight from
the docstrings on `cmakeless` and everything it re-exports.

## Start here

- [Introduction](INTRODUCTION.md): The problem, the idea, and why Python.
- [Features](FEATURES.md): Everything CMakeless does for you, with
  before/after comparisons against raw CMake.
- [Architecture](ARCHITECTURE.md): The four layers (API, model, emitter,
  driver) and the design patterns behind them.
- [Roadmap](ROADMAP.md): Where the project is going, phase by phase.
- [Tutorial](tutorial.md): A ten-minute, linear walkthrough for a first project.
- [Cookbook](cookbook.md): Task-oriented recipes ("add an include dir",
  "cross-compile for ARM", "use a private dependency mirror").
- [Migration guide](migration.md): Introducing CMakeless into an existing,
  hand-written CMake project.
- [Benchmarks](benchmarks.md): Measured parallelism wins, with the method
  behind them.
- [API Reference](reference/cmakeless/index.md): Every public class and function,
  generated from source.
- [Contributing](contributing.md): How to help, starting from your own
  CMake scars.

## Quick start

```console
$ pip install cmakeless
$ cmakeless init
$ cmakeless build
```

Once your project grows, the other verbs are already there:

```console
$ cmakeless test                      # CTest with per-case discovery
$ cmakeless build --preset release    # from your CMakePresets.json
$ cmakeless install --prefix dist     # install rules and export sets
$ cmakeless package                   # CPack archives
$ cmakeless doctor                    # check cmake/generator/ccache/vcpkg/Conan/network
$ cmakeless sbom --format spdx        # a bill of materials from cmakeless.lock
$ cmakeless vendor && cmakeless build --offline   # zero-network build
```

Interop and introspection are one call each too:

```python
project.add_python_module("mymath", sources=["src/mymath.cpp"], binding="pybind11")
project.add_observer(my_observer)     # progress events for IDEs and CI
targets = project.targets_info()      # the configured build as Python objects
mod = project.include_module("CheckCXXCompilerFlag")  # reflected via real CMake
info = project.cmake_info()           # resolved generator, compiler, and system
cmake = project.cmake_globals()       # any CMake variable, hasattr(cmake, "ANDROID")
```

Or write the five lines yourself:

```python
# cmakelessfile.py
from cmakeless import Project

project = Project("hello", version="1.0.0", cpp_std=20)
project.add_executable("hello", sources=["src/main.cpp"])
project.build()
```

Runnable projects live in [Examples](../examples/), smallest first.
