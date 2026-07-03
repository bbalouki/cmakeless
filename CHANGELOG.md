# Changelog

All notable changes to CMakeless are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

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
