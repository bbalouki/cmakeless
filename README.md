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
- [CONTRIBUTING](CONTRIBUTING.md): Why your scars from CMake make you exactly the contributor we need.

Runnable examples live in [examples/](examples/), smallest first.

