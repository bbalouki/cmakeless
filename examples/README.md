# CMakeless Examples

Runnable projects, smallest first. Each one builds with either entry point:

```console
$ python build.py       # the script is the tool
$ cmakeless build       # the CLI finds build.py and runs it
```

| Example | Shows |
|---|---|
| [01_hello](01_hello/) | The 5-line build.py: one executable, one source file. |
| [02_library](02_library/) | A static library with public headers, glob sources, strict warnings, defines, and linking. |
| [03_subprojects](03_subprojects/) | A parent project composing a self-contained subproject. |
| [04_dependencies](04_dependencies/) | An external package in one line: `app.depends("fmt/10.2.1")`, resolved through the find_package-then-FetchContent fallback and pinned in `cmakeless.lock`. |
| [05_testing](05_testing/) | Testing as a verb: `add_test(..., framework="catch2")` fetches the framework, registers every case with CTest, and `cmakeless test` runs the suite (add `--sanitize=address` for a sanitized run). |
| [06_ship](06_ship/) | Everything that ships: sanitized and LTO `Preset`s in `CMakePresets.json`, `install()` with export sets and `Config.cmake`, and `package()` producing archives via CPack. |

The generated `CMakeLists.txt` files are not committed: run any example once
and read the output. It should look like an expert wrote it by hand; if it
does not, that is a bug we want to hear about.
