# Changelog

All notable changes to CMakeless are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

## [0.4.0]

Interop and parallelism: the differentiators. A pybind11 project migrates its
binding build to one `add_python_module` call, and multi-preset configure runs
concurrently.

### Added

- **Python and C++ interop**: `project.add_python_module(name, sources,
  binding="nanobind")` builds a C++ extension with nanobind or pybind11. The
  binding backend is acquired like any dependency (pinned in `cmakeless.lock`),
  the module is built against the invoking interpreter's development headers,
  `.pyi` stubs are generated for nanobind, and after `cmakeless build` the
  module is copied into the current environment, so `import <name>` works
  immediately.
- **Observer event API**: `project.add_observer(observer)` registers a
  consumer that receives a `StepStarted`/`StepFinished`/`StepFailed` event for
  every configure, build, test, install, and package step, so IDE extensions
  and CI log formatters are listeners rather than special cases. The console
  display is now just the default `ConsoleObserver`. `Observer`, `BuildEvent`,
  and the event classes join the public API.
- **CMake File API**: `project.targets_info()` configures the build and returns
  it as `TargetInfo` objects (name, type, artifacts, sources, dependencies),
  read from CMake's File API rather than scraped from text.
- **Free-threaded parallelism, measured**: `project.configure_presets()`
  configures every preset concurrently, each into its own build tree, over one
  lock-free frozen model. A reproducible `benchmarks/` harness and published
  numbers for parallel dependency resolution and multi-preset configure live in
  [docs/benchmarks.md](docs/benchmarks.md).
- `PythonModule`, `Observer`, `BuildEvent`, `StepStarted`, `StepFinished`,
  `StepFailed`, `ConsoleObserver`, and `TargetInfo` join the public API;
  `cmakeless.api` now re-exports the full layer-1 surface. Registry entries for
  pybind11 and nanobind.
- A new runnable project, `examples/07_python_module`.

## [0.3.0]

Quality of life: everything that turns "it builds" into "it ships". A
library author can build, test (sanitized), install, and package a release
on CI using only `build.py`.

### Added

- **Testing as a verb**: `project.add_test(name, sources, framework=...)`
  with Catch2, GoogleTest, and doctest auto-integration (the framework is
  acquired like any dependency and pinned in `cmakeless.lock`), CTest
  registration with per-case discovery, and shared-library tests that run
  on Windows without PATH rituals. `cmakeless test` builds and runs the
  suite; `framework="none"` registers a plain pass/fail executable.
- **Sanitizers**: `target.sanitize = ["address", "undefined"]` applied to
  compile *and* link (the half-applied-sanitizer bug is not reproducible
  through this API), translated per compiler, and rejected loudly where
  unsupported. `cmakeless test --sanitize=address` runs the suite under a
  sanitizer in its own build tree.
- **`Preset` API**: `project.add_preset(Preset("release",
  optimize="release", lto=True))` generates `CMakePresets.json` (with
  build and test presets), so CLion, Visual Studio, and VS Code pick the
  configurations up natively. Every preset gets its own out-of-source
  build tree under `build/<name>`; `--preset` works on build, configure,
  test, install, and package.
- **`Toolchain` API**: `Toolchain.from_file(...)` wraps existing toolchain
  files unchanged; `Toolchain(name, compiler=..., system_name=...)`
  generates simple cross-compilation files under `cmake/toolchains/`.
  Presets reference toolchains by name.
- **Install and packaging**: `project.install(target, headers=True)` emits
  GNUInstallDirs-correct install rules, export sets, and
  `Config.cmake`/`ConfigVersion.cmake` generation so other CMake users can
  `find_package()` the result; `project.package(formats=["zip", "deb"])`
  configures CPack. New `cmakeless install --prefix ...` and `cmakeless
  package` verbs.
- **Tooling by default**: `compile_commands.json` is always exported and
  copied to the project root; ccache/sccache are auto-detected and wired
  as the compiler launcher on Ninja builds (opt out with `project.cache =
  False`).
- `Preset`, `Toolchain`, and `Test` join the public API. Curated registry
  pins for the default test framework versions (catch2 3.5.4, googletest
  1.14.0, doctest 2.4.11), so test projects resolve without network.
- Two new runnable projects: `examples/05_testing` and `examples/06_ship`.

## [0.2.0]

Dependencies: `app.depends("fmt/10.2.1")` works through four backends, and
resolution is reproducible from the lockfile alone.

### Added

- **`target.depends("name/version")`**: one line per external package, with
  `components=` for packages like boost and `public=` visibility. Escape
  hatches (`url=`, `sha256=`, `cmake_name=`, `targets=`) make any package
  usable, not just the built-in registry's.
- **Built-in package registry**: the folklore raw CMake makes you memorize
  (`fmt::fmt` is not `fmt`, googletest is `GTest`, the vcpkg port of
  nlohmann_json is `nlohmann-json`) curated for fmt, spdlog, catch2,
  doctest, googletest, nlohmann_json, zlib, and boost.
- **The default acquisition strategy**: emitted CMake tries `find_package`
  first and falls back to `FetchContent` pinned by URL and SHA256, so the
  generated file stays standalone.
- **`cmakeless.lock`**: byte-deterministic JSON lockfile written on every
  resolution; a complete lockfile resolves with zero network. Refresh it
  with `project.dependencies.lock()` or the new `cmakeless lock` verb.
- **`find_package` backend** (`project.package_manager = "find_package"`):
  system packages only, version-checked, no source fetches.
- **vcpkg backend** (`project.package_manager = "vcpkg"`): generates
  `vcpkg.json` (with `builtin-baseline` and version constraints when
  available) and wires the vcpkg toolchain file into the configure step.
- **Conan 2 backend** (`project.package_manager = "conan"`): generates
  `conanfile.txt`, runs `conan install` before configure, and wires the
  generated toolchain file.
- **Parallel resolution**: dependencies resolve in one thread each,
  correct on GIL builds and fast on free-threaded ones; completion order
  never leaks into the emitted files or the lockfile.
- `Dependency` joins the public API; `DependencyError` is now raised.
- A fourth runnable project, `examples/04_dependencies`.

## [0.1.0] 

The MVP: a small self-contained C++ project can use CMakeless instead of
hand-written CMake.

### Added

- **Full target set**: `Library` targets ("static", "shared", "header_only")
  next to `Executable`, with public header directories, correct
  `PUBLIC`/`PRIVATE`/`INTERFACE` visibility, position-independent code, and
  Windows export handling via `generate_export_header` for shared libraries.
- **The link graph**: `target.link(...)` with `public=` visibility on
  library-to-library links, `INTERFACE` chosen automatically for header-only
  libraries, and link-cycle detection at freeze time that names the cycle.
- **Compile settings**: `warnings` presets ("strict", "default", "none")
  translated per compiler, `target.define(...)`, and
  `target.compile_options(..., when="gcc|clang")` guards.
- **Glob sources**: patterns like `src/*.cpp` are expanded and validated in
  Python; a pattern matching zero files is a `ConfigurationError`.
- **Subprojects**: `project.add_subproject(path)` composes self-contained
  child projects (their own `build.py`); every generated file is standalone.
- **Driver**: generator selection ("ninja", "vs", or any raw CMake `-G`
  name) and error translation that parses CMake, GCC/Clang, MSVC, and linker
  failures into structured diagnostics on `CMakeError`.
- **Emitter contract**: byte-deterministic output enforced by golden-file
  tests.
- **CLI**: `cmakeless configure`, `cmakeless clean`, and `cmakeless init`
  scaffolding next to `cmakeless build`.
- Three runnable projects under `examples/`, smallest first, and a seeded
  `docs/` landing page.

## [0.0.1] 

Phase 0: the walking skeleton through all four layers.

### Added

- Walking skeleton through all four layers (API, model, emitter, driver).
- `Project` and `Executable` public API; `project.build()` freezes, validates,
  emits `CMakeLists.txt`, and drives CMake configure + build.
- Freeze-time validation: missing source files are reported as
  `ConfigurationError` before CMake ever runs.
- `cmakeless build` CLI and `python -m cmakeless`; `python build.py` works as
  a first-class entry point.
- Exception hierarchy: `CmakelessError` with `ConfigurationError`,
  `DependencyError`, `ToolchainError`, and `CMakeError`.
