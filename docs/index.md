# CMakeless Documentation

Write your C++ builds in Python. Keep CMake. Lose the pain.

The documentation currently lives in five documents at the repository root;
this site is seeded from them and will grow a tutorial, cookbook, and API
reference as the project approaches v1.0 (see the roadmap).

## Start here

- [Introduction](../INTRODUCTION.md): the problem, the idea, and why Python.
- [Features](../FEATURES.md): everything CMakeless does for you, with
  before/after comparisons against raw CMake.
- [Architecture](../ARCHITECTURE.md): the four layers (API, model, emitter,
  driver) and the design patterns behind them.
- [Roadmap](../ROADMAP.md): where the project is going, phase by phase.
- [Contributing](../CONTRIBUTING.md): how to help, starting from your own
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
```

Or write the five lines yourself:

```python
# build.py
from cmakeless import Project

project = Project("hello", version="1.0.0", cpp_std=20)
project.add_executable("hello", sources=["src/main.cpp"])
project.build()
```

Runnable projects live in [examples/](../examples/), smallest first.
