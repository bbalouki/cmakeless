# Changelog

All notable changes to CMakeless are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

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
