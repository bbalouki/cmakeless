# 08 - Capstone: the whole surface in one project

This is not a toy. It is a small but complete C++ project, a summary-statistics
library, described entirely in one [cmakelessfile.py](cmakelessfile.py) and shipped four ways
from a single definition. It is the example to read once you have skimmed the
smaller ones, because it shows how the pieces compose.

## What it demonstrates

| Call in `cmakelessfile.py` | What you get |
|---|---|
| `add_library("stats", ..., public_headers="include/")` | a static C++ library with a public header set |
| `stats.depends("fmt/10.2.1")` | a **private** dependency: `fmt` is used inside `series.cpp` only, never leaked to consumers |
| `add_executable("stats_cli", ...)` + `cli.link(stats)` | a command-line tool over the library |
| `add_test("stats_tests", ...)` | a **GoogleTest** suite (the default framework), auto-fetched and CTest-registered |
| `add_python_module("pystats", ...)` | a **pybind11** module (the default binding) exposing the same C++ class to Python |
| `add_preset(Preset("release", optimize="release", lto=True))` | named configurations in `CMakePresets.json`, each with its own build tree |
| `install(stats, headers=True)` + `package(...)` | install rules, an export set with `Config.cmake`, and a CPack archive |
| `add_observer(StepPrinter())` | live progress events for every configure/build/test step |

The C++ library (`stats::Series`) computes mean, variance, standard deviation,
min, max, and median, formats a summary with `fmt`, and rejects an empty sample
set, an error that surfaces in Python as a normal `ValueError`.

## Run it

```console
$ cmakeless build                     # build the library, CLI, and Python module
$ ./build/stats_cli 3 1 4 1 5 9 2 6   # n=8 mean=3.875 stddev=2.571 min=1.000 median=3.500 max=9.000
$ cmakeless test                      # run the GoogleTest suite through CTest
$ python test_pystats.py              # import pystats and use the C++ from Python
```

Ship a release:

```console
$ cmakeless build --preset release    # optimized, LTO, in build/release/
$ cmakeless install --prefix dist     # headers + library + Config.cmake under dist/
$ cmakeless package                   # a stats-1.0.0-*.zip archive via CPack
```

## Introspect the configured build

Because the driver consumes CMake's File API, the configured build is available
as plain Python objects, no log scraping. Anywhere you hold the `Project` (for
example in `cmakelessfile.py`, in place of `project.build()`):

```python
for target in project.targets_info():
    print(target.name, target.type, target.artifacts)
```

## The point

Every capability above is one line of Python. The generated `CMakeLists.txt`
(run the example once and read it) is honest, modern CMake you could commit and
maintain by hand, if you wanted to. You do not have to.
