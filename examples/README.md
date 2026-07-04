# CMakeless Examples

Runnable projects, smallest first. Each one builds with either entry point:

```console
$ python cmakelessfile.py   # the script is the tool
$ cmakeless build           # the CLI finds cmakelessfile.py and runs it
```

| Example | Shows |
|---|---|
| [01_hello](01_hello/) | The 5-line cmakelessfile.py: one executable, one source file. |
| [02_library](02_library/) | A static library with public headers, glob sources, strict warnings, defines, linking, a private `include_dirs()`, and a compiler-guarded `link_options()`. |
| [03_subprojects](03_subprojects/) | A parent project composing a self-contained subproject. |
| [04_dependencies](04_dependencies/) | An external package in one line: `app.depends("fmt/10.2.1")`, resolved through the find_package-then-FetchContent fallback and pinned in `cmakeless.lock`. |
| [05_testing](05_testing/) | Testing as a verb: `add_test(..., framework="catch2")` picks Catch2 over the default GoogleTest, fetches it, registers every case with CTest, and `cmakeless test` runs the suite (add `--sanitize=address` for a sanitized run). |
| [06_ship](06_ship/) | Everything that ships: sanitized and LTO `Preset`s in `CMakePresets.json`, `install()` with export sets and `Config.cmake`, and `package()` producing archives via CPack. |
| [07_python_module](07_python_module/) | Python and C++ interop: `add_python_module(...)` (pybind11 by default) builds a real 2D-vector `Vec2` class, operators, properties, and C++ exceptions that surface as Python `ValueError`, importable right after the build. |
| [08_capstone](08_capstone/) | The whole surface in one project: a `stats` library (private `fmt` dep) shipped as a CLI, a **GoogleTest** suite, and a **pybind11** module, plus presets, install/export, CPack, and a live `Observer`. Not a toy. |
| [09_build_language](09_build_language/) | The language unlock: `project.add_command(...)` runs a code-generation step whose output feeds a target's `add_sources()`, `project.option(...)` declares a real CMake cache variable, and `When.option(...)`/`When.config(...)` gate defines on that option and on the active build configuration. |

The generated `CMakeLists.txt` files are not committed: run any example once
and read the output. It should look like an expert wrote it by hand; if it
does not, that is a bug we want to hear about.
