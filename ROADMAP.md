# CMakeless Roadmap

From an empty repository to a v1.0 that a team can bet a product on. The ordering rule is simple: **most basic first, and every phase ends with something a real user can run.** Feature details live in [FEATURES](FEATURES.md); the layer vocabulary (API, model, emitter, driver) comes from [ARCHITECTURE](ARCHITECTURE.md).

Versioning follows Semantic Versioning 2.0.0 throughout: breaking API changes bump the minor version pre-1.0 and the major version after, and every release updates `CHANGELOG.md`.

## Timeline at a Glance

| Phase | Release | Theme |
|---|---|---|
| 0 | none | Walking skeleton | 
| 1 | v0.1 | MVP: real projects build |
| 2 | v0.2 | Dependencies |
| 3 | v0.3 | Quality of life: tests, presets, install |
| 4 | v0.4 | Interop and parallelism |
| 5 | v1.0 | Stability promise |

Scope is the fixed variable, order is the promise.

---

## Phase 0: Walking Skeleton

The thinnest possible slice through all four layers, proving the architecture before investing in it.

- Repository scaffold: src-layout, `pyproject.toml` (zero runtime deps), pytest wiring under `tests/unittests/`, ruff + mypy, GitHub Actions running on Windows, Linux, macOS from day one.
- Model: `ProjectModel` and `ExecutableModel` frozen dataclasses, freeze-time validation of source existence.
- Emitter: generate a correct, modern `CMakeLists.txt` for a single executable.
- Driver: run `cmake` configure + build, surface exit codes as `CMakeError`.
- CLI: `cmakeless build` and `python build.py` both compile a hello-world.

**Exit criterion:** a newcomer clones the repo, writes a 5-line `build.py`, and gets a running binary on all three OSes.

## Phase 1: MVP, v0.1 

The features without which nothing is real. After this phase, a small self-contained project (no external deps) uses CMakeless instead of hand-written CMake.

- Full target set: `Executable`, `Library` (static, shared, header-only) with correct visibility propagation and Windows export handling.
- The link graph: `target.link(...)`, `public=` visibility, cycle detection at freeze time.
- Compile settings: `cpp_std`, `warnings` presets per compiler, `define()`, `compile_options()` with `when=` guards.
- Emitter contract enforced: deterministic output, golden-file tests comparing generated CMake byte-for-byte.
- Driver: error translation (parse compiler/CMake failures into structured `CMakeError`), Ninja and Visual Studio generators.
- Subprojects (Composite) with isolated scopes.
- `cmakeless init` scaffolding; first three `examples/` projects.
- Documentation site seeded from these five documents.

**Exit criterion:** the CMakeless examples and at least one real third-party hobby project build with zero raw CMake written.

## Phase 2: Dependencies, v0.2 

The phase that decides adoption, sequenced by backend difficulty:

1. `find_package` adapter (system packages) with version checking.
2. `FetchContent` adapter with pinned hashes; the `find_package`-then-fetch fallback strategy.
3. `cmakeless.lock` lockfile: deterministic resolution for CI and teammates.
4. vcpkg adapter (manifest generation, toolchain wiring).
5. Conan 2 adapter.
6. Parallel resolution using a thread pool (correct on GIL builds, fast on free-threaded builds).

**Exit criterion:** `app.depends("fmt/10.2.1")` works on all three OSes through at least three of the four backends, and resolution is reproducible from the lockfile alone.

## Phase 3: Quality of Life, v0.3 

Everything that turns "it builds" into "it ships":

- Testing verb: `add_test` with Catch2/GoogleTest/doctest auto-integration, CTest registration, `cmakeless test` with per-case discovery.
- Sanitizer presets (`sanitize=["address", "undefined"]`) applied to compile and link, validated per compiler.
- `Preset` API generating `CMakePresets.json`; per-preset out-of-source build trees.
- `Toolchain` API: wrap existing toolchain files, generate simple cross-compilation ones.
- Install and packaging: `project.install(...)`, export sets, `Config.cmake` generation, CPack formats.
- `compile_commands.json` always-on plumbing; ccache/sccache auto-detection.

**Exit criterion:** a library author can build, test (sanitized), install, and package a release on CI using only `build.py`.

## Phase 4: Interop and Parallelism, v0.4 

The differentiators:

- `add_python_module(...)` with nanobind and pybind11 backends, stub generation, current-environment installation.
- Free-threaded Python exploitation measured, not assumed: benchmarks for parallel dependency resolution and multi-preset configuration; published numbers.
- Observer event API stabilized for third-party progress consumers (IDE extensions, CI formatters).
- CMake File API integration completed: `project.targets_info()` returns the fully configured build as Python objects.

**Exit criterion:** a pybind11-based project migrates its entire binding build to one `add_python_module` call, and multi-preset configure shows measurable wall-clock wins on free-threaded 3.14.

## Phase 5: v1.0, the Stability Promise

v1.0 is a social contract, not a feature list. Declaring it requires:

- C++20/23 modules support (tracking CMake's own maturing support; this lands last on purpose, when the ground stops moving).
- Public API frozen and audited: every class, method, and argument justified or removed. Deprecations from 0.x deleted.
- Documentation complete: tutorial, cookbook, migration guide from raw CMake, API reference.
- Real-world validation: at least a handful of independent projects on 0.x in CI, their issues closed.
- From here on, SemVer with teeth: breaking changes mean 2.0, and `[[deprecated]]`-style migration paths are mandatory (deprecation warnings with the new spelling, one minor version of overlap minimum).

## Beyond 1.0 (unscheduled, honestly)

Ideas we are deliberately *not* promising dates for: a `cmake-to-cmakeless` importer for existing CMakeLists, workspace/monorepo support, a public emitter API for alternative outputs, remote build integration.

## Non-Goals, Permanently

Repeated here because roadmaps grow by accretion and this one must not:

- **Not a build system.** No compilation scheduling, no dependency scanning of source files. CMake + Ninja own that.
- **Not a CMake replacement.** If CMake ships a feature, our job is to expose it elegantly, not to reimplement it.
- **Not a new language.** `build.py` is plain Python. Any proposal that adds CMakeless-only semantics to Python syntax is rejected on arrival.
- **Not a package repository.** We adapt to vcpkg/Conan/upstream sources; we never host packages.

Want to bend the timeline? The fastest way is to grab a phase item: see [CONTRIBUTING](CONTRIBUTING.md).
