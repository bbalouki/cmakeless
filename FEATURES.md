# CMakeless Features

Everything CMakeless does for you, organized by one rule: **you write the intent, we write the boilerplate.** For each feature you see the Python you write and the CMake ritual you no longer perform. All examples use the same project as [INTRODUCTION](INTRODUCTION.md): a game called `mygame` with an `engine` library.

The design principles behind this surface are in [ARCHITECTURE](ARCHITECTURE.md).

---

## 1. Projects and Targets

### Executables and libraries

**You write:**

```python
from cmakeless import Project

project = Project("mygame", version="1.0.0", cpp_std=23)

engine = project.add_library(
    "engine",
    sources=["src/engine/*.cpp"],
    public_headers="include/",
    kind="static",              # "static" | "shared" | "header_only"
)

app = project.add_executable("mygame", sources=["src/main.cpp"])
app.link(engine)
```

**We handle:** `cmake_minimum_required` and version policy selection, `project()` declaration, `add_library`/`add_executable`, `target_compile_features(... cxx_std_23)`, `target_include_directories` with correct `PUBLIC`/`PRIVATE`/`INTERFACE` visibility and build/install interface generator expressions, position-independent code for shared libraries, and export macros on Windows (`__declspec(dllexport)` header generation).

Glob patterns are expanded *by CMakeless in Python* and validated: a pattern that matches zero files is a `ConfigurationError` at freeze time, not a silent empty target.

### Linking with intent, not keywords

`app.link(engine)` links privately by default (the common case for executables). Library-to-library linking states visibility as a plain argument, with the correct CMake keyword chosen for you:

```python
engine.link(math_lib, public=True)    # users of engine also need math_lib
engine.link(zlib_dep)                 # implementation detail, stays private
```

No more guessing among `PUBLIC`, `PRIVATE`, and `INTERFACE`: `public=True` when your headers expose it, nothing otherwise. Header-only libraries pick `INTERFACE` automatically because there is no other correct answer.

### Private headers and a per-target standard

```python
engine.include_dirs("src/engine/internal")   # PRIVATE, never exposed to consumers
engine.cpp_std = 17                          # overrides the project's default for this target only
```

`include_dirs()` is the private counterpart to `public_headers=`: for the internal headers a target's own sources need but consumers never should. `cpp_std` lets one target compile against a different standard than the rest of the project (a vendored C++17 core underneath a C++23 app), without a second `Project`.

### Subprojects (Composite)

```python
project.add_subproject("tools/asset_packer")   # its own cmakelessfile.py
```

Replaces `add_subdirectory` plus the folkloric knowledge about variable scoping across directories. Each subproject is a self-contained `Project`; the parent composes them.

---

## 2. Dependencies: One Line, Any Backend

**You write:**

```python
app.depends("fmt/10.2.1")
app.depends("boost/1.84.0", components=["asio", "beast"])
```

**We handle:** the entire acquisition strategy, behind an Adapter interface (see [ARCHITECTURE](ARCHITECTURE.md#design-patterns-named)):

- system packages via `find_package` when present and version-compatible,
- source builds via `FetchContent` with pinned URL and hash,
- **vcpkg** or **Conan** when the project opts in (`project.package_manager = "vcpkg"`),
- generation of the corresponding manifest (`vcpkg.json`, `conanfile.txt`) so the package manager's own tooling still works.

What that one line replaces in raw CMake: the `find_package`-or-`FetchContent` fallback dance, `FetchContent_Declare`/`FetchContent_MakeAvailable` ceremony, remembering the exported target name (`fmt::fmt` is not `fmt`), and toolchain-file plumbing for vcpkg.

Resolution runs in parallel threads on free-threaded Python, one per dependency. And every resolution writes `cmakeless.lock`, so CI and teammates get byte-identical dependency trees.

```python
project.dependencies.lock()      # refresh the lockfile explicitly
```

### Extending the registry

The ten built-in packages are a seed, not a ceiling. Teach CMakeless about your own packages, once, in either of two ways:

```python
import cmakeless
from cmakeless import RegistryEntry

cmakeless.register_dependency(
    "mylib",
    RegistryEntry(cmake_name="MyLib", targets=("mylib::mylib",), vcpkg_name="mylib"),
)
```

or ship it as an installed plugin distribution, discovered automatically without any per-project code:

```toml
# pyproject.toml of a plugin package
[project.entry-points."cmakeless.registry"]
mylib = "my_plugin:registry_entries"   # a zero-argument callable returning RegistryEntry or dict[str, RegistryEntry]
```

An explicit `register_dependency()` call always wins over a plugin-supplied entry, and a plugin never overrides a built-in package.

---

## 3. Compiler Settings Without Flag Archaeology

**You write:**

```python
project.warnings = "strict"          # or "default", "none"
project.optimize = "release"         # per-preset, see section 6
app.sanitize = ["address", "undefined"]
project.lto = True
```

**We handle:** the per-compiler translation tables. `warnings="strict"` becomes `/W4 /permissive-` on MSVC and `-Wall -Wextra -Wconversion -Wsign-conversion -pedantic` on GCC/Clang. Sanitizer flags are applied to both compile and link steps (the half-applied-sanitizer bug is not reproducible through this API), checked against the active compiler, and rejected with a clear `ToolchainError` where unsupported (for example ASan+MSVC edge cases). LTO maps to `INTERPROCEDURAL_OPTIMIZATION` with the CMake policy dance included.

Escape hatches keep full control local and explicit:

```python
app.compile_options("-march=native", when="gcc|clang")
app.link_options("-Wl,--as-needed", when="gcc|clang")
app.define("GAME_MAX_PLAYERS", 8)
```

`ccache`/`sccache` are auto-detected and wired as compiler launchers (Makefiles, Ninja, and Ninja Multi-Config generators) unless disabled: `project.cache = False`.

### Conditions, typed instead of stringly

The `"gcc|clang"` string above is still valid (kept as sugar), but `When` gives you the same guard for platforms, build configurations, and your own project options, composed with `&`/`|`/`~`:

```python
from cmakeless import When

app.define("USE_D3D12", when=When.platform("windows"))
app.compile_options("-march=native", when=When.compiler("gcc", "clang"))
app.define("ENABLE_TRACING", when=When.config("Debug"))
```

One factory set, one mechanism: CMakeless decides internally whether a condition becomes a generator expression or an `if()` block, so you never have to.

### Project options

```python
gui = project.option("MYLIB_BUILD_GUI", default=True, help="Build the Qt front-end")
app.define("HAS_GUI", when=When.option(gui))
```

`project.option(...)` declares a real CMake cache variable (`option()` for booleans, `set(... CACHE ...)` otherwise), discoverable without reading a single line of `cmakelessfile.py`:

```console
$ cmakeless options
[cmakeless] MYLIB_BUILD_GUI (bool, default=True): Build the Qt front-end
```

Combine it with a condition (`When.option(gui)`), or override it per preset (section 6).

### Precompiled headers and unity builds

```python
engine.pch = ["<vector>", "src/engine/pch.hpp"]
engine.unity = True
```

**We handle:** `target_precompile_headers()` (system headers verbatim, project headers quoted) and the `UNITY_BUILD` target property, both rejected with a clear error on header-only libraries, which compile nothing.

---

## 4. Testing as a First-Class Verb

**You write:**

```python
tests = project.add_test(
    "engine_tests",
    sources=["tests/*.cpp"],
    framework="gtest",           # the default; or "catch2", "doctest", "none"
)
tests.link(engine)
```

```console
$ cmakeless test
```

**We handle:** fetching the framework (via section 2), `enable_testing()`, CTest registration with per-test-case discovery (`gtest_discover_tests`/`catch_discover_tests`), correct runtime path setup so shared-library tests run on Windows without PATH rituals, and result reporting back into Python via the driver.

Sanitized test runs are one argument: `cmakeless test --sanitize=address`.

---

## 5. Python and C++ Interop, Because That Is the Point

**You write:**

```python
bindings = project.add_python_module(
    "mygame_core", sources=["src/bindings.cpp"], binding="pybind11"  # the default
)
bindings.link(engine)
```

**We handle:** locating the Python development headers of the *invoking* interpreter, fetching pybind11 or nanobind (pinned in `cmakeless.lock` like any dependency), the module target boilerplate through the backend's own `pybind11_add_module`/`nanobind_add_module`, correct extension suffixes per platform, `.pyi` stub generation (nanobind), and, since CMakeless itself is Python, the module lands importable in your current environment after `project.build()`.

This is the flagship of the whole idea: the tool that builds your C++ is already inside the interpreter that will import it.

### A stable, deterministic version floor

The generated `find_package(Python ...)` version does **not** depend on whichever interpreter happens to run `cmakeless`: it defaults to CMakeless's own supported floor, so two developers (or a developer and CI) with different Python versions installed get byte-identical `CMakeLists.txt` for the same `cmakelessfile.py`. Raise it explicitly when a module needs newer C API surface:

```python
bindings = project.add_python_module(
    "mygame_core", sources=["src/bindings.cpp"], python_version="3.13"
)
```

Multiple Python modules with different `python_version=` floors combine to the highest one requested, since `find_package(Python X.Y ...)` already means "X.Y or newer."

---

## 6. Presets, Configurations, and Toolchains

**You write:**

```python
from cmakeless import Preset, Toolchain

project.add_preset(Preset("debug", optimize="none", sanitize=["address"]))
project.add_preset(Preset("release", optimize="release", lto=True))
project.add_preset(Preset(
    "ci",
    inherits="release",
    options={"MYLIB_BUILD_GUI": False},
    env={"CI": "1"},
))

project.add_toolchain(Toolchain.from_file("cmake/rpi4.toolchain.cmake"))
project.add_toolchain(Toolchain("arm64-linux", compiler="aarch64-linux-gnu-g++"))
```

```console
$ cmakeless build --preset release
```

**We handle:** generation of `CMakePresets.json` (so CLion, Visual Studio, and VS Code pick up your presets natively), per-preset build directories (out-of-source always, no in-source builds possible by construction), multi-config generator support on Windows, toolchain-file generation for the simple cross cases while accepting your existing toolchain files unchanged for the hard ones, and per-preset cache-variable overrides (`options=`, validated against declared `project.option()`s), environment blocks (`env=`), and inheritance (`inherits=`, cycle-checked).

On free-threaded Python, configuring multiple presets runs concurrently.

---

## 7. Install and Packaging

**You write:**

```python
project.install(app)
project.install(engine, headers=True)
project.package(formats=["zip", "deb"])    # CPack, when you want it
```

**We handle:** `install(TARGETS ...)` with GNUInstallDirs-correct destinations, header set installation, export sets and `Config.cmake` generation so *other* CMake users can `find_package(mygame)` your library, version-compatibility files, and CPack configuration for the requested formats. This paragraph of Python replaces the single most copy-pasted hundred lines in the CMake ecosystem.

---

## 8. Tooling Integration by Default

No opt-in required, because there is no reason not to want these:

- **`compile_commands.json`** is always exported and symlinked/copied to the project root: clangd, clang-tidy, and every editor just work.
- **IDE projects for free.** Since the output is honest CMake, CLion, Visual Studio, Qt Creator, and VS Code's CMake Tools open the project natively. CMakeless does not need IDE plugins to be usable inside every IDE.
- **`cmakeless init`** scaffolds a new project (directory layout, `cmakelessfile.py`, `.gitignore`, a hello-world target) in one command.
- **Structured build feedback.** The driver consumes the CMake File API, so `project.targets_info()` returns real Python objects describing the configured build, and progress events stream to the console (or your own Observer) instead of raw log walls.

---

## 9. The Escape Hatch

The 1% rule: anything we do not model must still be reachable, locally and visibly.

```python
engine.raw_cmake('set_property(TARGET engine PROPERTY JOB_POOL_COMPILE heavy_jobs)')
project.raw_cmake_file("cmake/legacy_weirdness.cmake")
```

Raw snippets are emitted verbatim into the generated file, clearly fenced with comments naming their `cmakelessfile.py` origin. The escape hatch is deliberately a little ugly: if you find yourself using it often, that is a feature request we want to hear about (see [CONTRIBUTING](CONTRIBUTING.md)). Precompiled headers and unity builds used to be the flagship example here (section 3 now models them directly); this is the up-to-date version of "still genuinely unmodeled."

---

## 10. Custom Build Steps

**You write:**

```python
gen = project.add_command(
    output=["generated/version.cpp"],
    command=["python", "tools/gen_version.py", "--out", "generated/version.cpp"],
    depends=["tools/gen_version.py"],
    comment="Generating version.cpp",
)
app.add_sources(gen)   # wires the dependency edge; no special CMake syntax needed

project.add_custom_target(
    "cook-assets",
    command=["python", "tools/cook.py", "assets/", "--out", "cooked/"],
    depends=[assets_manifest],
)
```

**We handle:** `add_custom_command(OUTPUT ...)` and `add_custom_target(...)` wiring, always with `VERBATIM`, so commands are argument lists, never shell strings, portable across cmd/POSIX by construction and immune to injection. Passing a `Command` handle to `add_sources()` or to another command's/custom target's `depends=` keeps the dependency graph validated in Python: a command whose output nothing consumes is a freeze-time warning, not a silent gap.

This is the answer to "does CMakeless support custom build steps": code generation, asset cooking, shader compilation, anything `add_custom_command`/`add_custom_target` would do by hand, now typed and validated.

---

## What CMakeless Will Not Do

Boundaries, stated as promises (see also the non-goals in [ROADMAP](ROADMAP.md)):

- **It will not become a build system.** Compilation, dependency graphs between object files, incremental rebuilds: CMake and Ninja own these, and they are better at it than anything we would write.
- **It will not invent a DSL.** `cmakelessfile.py` is plain Python forever.
- **It will not hold your project hostage.** The generated CMake is readable, committable, and standalone. Deleting CMakeless from your toolchain must always be a boring afternoon, not a migration project.
