# CMakeless Roadmap

From an empty repository to a v1.0 that a team can bet a product on. The ordering rule is simple: **most basic first, and every phase ends with something a real user can run.** Feature details live in [FEATURES](FEATURES.md); the layer vocabulary (API, model, emitter, driver) comes from [ARCHITECTURE](ARCHITECTURE.md).

Versioning follows Semantic Versioning 2.0.0 throughout: breaking API changes bump the minor version pre-1.0 and the major version after, and every release updates `CHANGELOG.md`.

## Timeline at a Glance

| Phase | Release | Theme                                                                             |
| ----- | ------- | --------------------------------------------------------------------------------- |
| 0     | none    | Walking skeleton                                                                  |
| 1     | v0.1    | MVP: real projects build                                                          |
| 2     | v0.2    | Dependencies                                                                      |
| 3     | v0.3    | Quality of life: tests, presets, install                                          |
| 4     | v0.4    | Interop and parallelism                                                           |
| 5–5.2 | v0.5    | The language unlock: mechanical fixes, options and conditions, custom build steps |
| 5.3   | v0.5.3  | The interop unlock                                                                |
| 5.4   | v0.5.4  | The portability release                                                           |
| 5.5   | v0.5.5  | Documentation and quality debt                                                    |
| 5.6   | v1.0    | Stability promise                                                                 |

Scope is the fixed variable, order is the promise.

---

## Phase 0: Walking Skeleton

The thinnest possible slice through all four layers, proving the architecture before investing in it.

- Repository scaffold: src-layout, `pyproject.toml` (zero runtime deps), pytest wiring under `tests/unittests/`, ruff + mypy, GitHub Actions running on Windows, Linux, macOS from day one.
- Model: `ProjectModel` and `ExecutableModel` frozen dataclasses, freeze-time validation of source existence.
- Emitter: generate a correct, modern `CMakeLists.txt` for a single executable.
- Driver: run `cmake` configure + build, surface exit codes as `CMakeError`.
- CLI: `cmakeless build` and `python cmakelessfile.py` both compile a hello-world.

**Exit criterion:** a newcomer clones the repo, writes a 5-line `cmakelessfile.py`, and gets a running binary on all three OSes.

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

**Exit criterion:** a library author can build, test (sanitized), install, and package a release on CI using only `cmakelessfile.py`.

## Phase 4: Interop and Parallelism, v0.4

The differentiators:

- `add_python_module(...)` with nanobind and pybind11 backends, stub generation, current-environment installation.
- Free-threaded Python exploitation measured, not assumed: benchmarks for parallel dependency resolution and multi-preset configuration; published numbers.
- Observer event API stabilized for third-party progress consumers (IDE extensions, CI formatters).
- CMake File API integration completed: `project.targets_info()` returns the fully configured build as Python objects.

**Exit criterion:** a pybind11-based project migrates its entire binding build to one `add_python_module` call, and multi-preset configure shows measurable wall-clock wins on free-threaded 3.14.

## Phase 5.0: Mechanical Fixes and Extensibility, v0.5

Bugs and gaps in what already shipped, closed before any new language surface lands on top of them:

- Dynamic Python version in generated `find_package(Python ...)` calls, tracking the interpreter that is actually running CMakeless instead of a hard-coded constant.
- ccache/sccache wired for every generator family where `CMAKE_CXX_COMPILER_LAUNCHER` actually works (Makefiles, Ninja, Ninja Multi-Config), plus new generator shorthands (`"ninja-multi"`, `"make"`, `"xcode"`) alongside `"ninja"`/`"vs"`.
- The Conan adapter derives its build type from the active preset or `project.optimize`, instead of always installing Release dependencies.
- A public dependency-registry registration API (`cmakeless.register_dependency(...)`) and installed-plugin discovery via the `"cmakeless.registry"` entry-point group; the curated list itself stays ten packages for now (growing it at scale is Phase 4.4).
- Private include directories (`target.include_dirs(...)`) and a per-target C++ standard override (`target.cpp_std`), closing two of the four target-vocabulary gaps.
- The Python floor drops to 3.12 (not 3.10, to keep the PEP 695 syntax already in `api/targets.py` and `_parallel.py` unrewritten); CI tests 3.12 and 3.13 across all three OSes.

**Exit criterion:** every dependency/generator/target-vocabulary gap above is closed, with zero behavior change for a project that does not opt into the new surface.

## Phase 5.1: The Language Unlock, v0.5.1

The `When` condition object and everything it powers, the highest-leverage addition in this release, because it turns `raw_cmake()` from a necessity into a rarity while staying a closed, validated vocabulary rather than a new DSL:

- `When.platform(...)`, `When.compiler(...)`, `When.config(...)`, `When.option(...)`, composable with `&`/`|`/`~`; wired into `define()`, `compile_options()`, and the new `link_options()` (mirroring `compile_options()`). The legacy `when="gcc|clang"` string form stays as sugar for `When.compiler(...)`.
- Precompiled headers and unity builds (`target.pch = [...]`, `target.unity = True`), retiring the `raw_cmake()` workaround its own docstring used to demonstrate.
- `project.option(name, default=..., help=..., type=...)`, validated at freeze time, listed by the new `cmakeless options` verb, and usable in `When.option(...)`.
- `Preset(options={...}, env={...}, inherits="base")`, so a preset can set cache variables, an environment block, and inherit from another preset, validated the same way toolchain references already are.

**Exit criterion:** a mixed-standard, mixed-configuration project (a vendored C++17 core, a C++23 app, a Debug-only sanitizer flag, an optional GUI target gated on a cache variable) is describable without `raw_cmake()`.

**Deferred from this phase:** a structural `if()`-block renderer for `When` so `link()`/`add_subproject()` can accept `when=` directly (only the compile-level generator-expression form shipped in 4.2). Blocked on new `LinkModel`/`SubprojectModel` fields and on resolving how `When.config(...)` behaves under multi-config generators, where `CMAKE_BUILD_TYPE` is not set at configure time (Visual Studio, Xcode, Ninja Multi-Config); tracked for a future release once that design is settled.

## Phase 5.2: Custom Build Steps, v0.5.2

- `project.add_command(output=[...], command=[...], depends=[...], comment=...)`, returning a handle usable in a target's `add_sources()` and in another command's or custom target's `depends=`.
- `project.add_custom_target(name, command=[...], depends=[...])` for always-run targets (asset cooking, lint, docs).
- Commands are argument lists, never shell strings: portable across cmd/POSIX by construction, and injection-proof (CMake's `VERBATIM` keyword is always emitted). An output nothing consumes is a freeze-time warning, not a build error.

**Exit criterion:** a code-generation step (a version-info source file) and an asset-cooking step are both describable without `raw_cmake()`, and the generated `add_custom_command`/`add_custom_target` blocks are indistinguishable from hand-written modern CMake.

## Phase 5.3: The Interop Unlock, v0.5.3

Carried over from the "call `include()` and read variables from Python" idea: the last gap the escape hatch never covered, reflecting what a `.cmake` file or built-in module actually defines through real CMake instead of guessing at it:

- `project.include("cmake/print_build_summary.cmake")` / `project.include_module("CheckCXXCompilerFlag")` with reflection: run real CMake (script mode, falling back to a throwaway configure for the commands script mode rejects, plus the File API for a best-effort read of any targets declared) to discover a module's functions, variables, and targets, and validate `mod.call(...)`/`mod.variable(...)` invocations before emission, never a hand-written CMake-language parser.
- `project.cmake_info()`: a post-configure read of the resolved generator, compiler ID/version, system name/processor, and the project's own options' final values, via the same File API pattern `targets_info()` already uses.
- The curated dependency registry grew from ten packages to over forty, spanning general-purpose, gaming, and finance/engineering staples (the registration mechanism from Phase 5.0 was always the seed, not the ceiling).

**Exit criterion:** a project reflects a local `.cmake` helper and a built-in CMake module, calls a function and reads a variable each discovered, and reads the resolved generator, compiler, and system after configure, all without a hand-written CMake-language parser anywhere in CMakeless.

**Deferred from this phase:** target discovery for `include()`/`include_module()` is best-effort (an include that only works inside its real parent project reports no targets rather than failing the call), and `mod.variable(...)` reads one discovered variable's value at a time rather than bulk-exporting every variable an include defines.

## Phase 5.4: The Portability Release, v0.5.4

The industries-readiness work (gaming, finance, engineering, aerospace):

- A curated toolchain gallery: `Toolchain.arm_none_eabi()`, `Toolchain.emscripten()`, `Toolchain.android(ndk=..., abi=...)`, `Toolchain.ios()`, each validated with the project's signature helpful errors.
- `cmakeless sbom` (CycloneDX/SPDX from `cmakeless.lock`'s already-complete dependency inventory), `--offline` (fail loudly rather than fetch) plus a mirror map, and a `cmakeless vendor` verb to download every locked dependency for zero-network builds.
- `project.lint(clang_tidy=True, iwyu=False)` (and a per-target `target.lint(...)` override) wiring `CXX_CLANG_TIDY`/`CXX_INCLUDE_WHAT_YOU_USE` per target.
- A `cmakeless doctor` verb: one command that checks CMake version, generator, compilers, ccache, vcpkg/Conan, and network access, and prints exactly what a new machine is missing.

**Exit criterion:** a project registers a bare-metal ARM toolchain and an iOS toolchain without installing either SDK, generates a CycloneDX and an SPDX bill of materials from `cmakeless.lock`, vendors its one dependency and rebuilds with `--offline` using only the local copy, wires `clang-tidy` into its default build, and `cmakeless doctor` reports the local machine's CMake/generator/cache/network status with no project present at all.

**Deferred from this phase:** full `--offline` support for the vcpkg and Conan backends is real but partial, vcpkg is checked against its own `vcpkg_installed` output directory (no fetch is attempted if that manifest is already satisfied) and Conan is asked for `--build=never` instead of `--build=missing`, but neither backend's own network access is intercepted by CMakeless directly, since both fetch through external tooling outside CMakeless's Python (vcpkg's toolchain-triggered install runs inside CMake's own configure step; Conan's install step is a real subprocess CMakeless only supervises).

## Phase 5.5: Documentation and Quality Debt, v0.5.5 (beta)

The adoption-friction work a growing user base starts to feel, closed out before v1.0's stability promise:

- **`project.cmake_globals(toolchain=...)`**: a `CMakeGlobals` object exposing every CMake variable a real (throwaway) configure defined, as attributes, so `if hasattr(cmake, "ANDROID"): app.link(...)` can check the compiler, the architecture, or anything else CMake itself knows, before a single line of `CMakeLists.txt` is emitted. `hasattr(...)` mirrors CMake's `if(DEFINED ...)`, not `if(...)`: a platform variable like `ANDROID`/`IOS`/`WIN32` is only ever set, never defined-and-false. Since a bare `Project` has no single "active toolchain" outside of what presets reference, an explicit `toolchain=` argument answers the question under a specific cross-compilation target; the default reflects the host build.
- A ten-minute [tutorial](tutorial.md) and a task-oriented [cookbook](cookbook.md) ("add an include dir", "cross-compile for ARM", "use a private dependency mirror", and more).
- A [migration guide](migration.md) from raw CMake: an idiom mapping table, a worked conversion example, and an honest list of what still needs `raw_cmake_file()`.
- An error-message golden-file test suite (`tests/unittests/errors/`), covering one representative case per error class, so a regression in diagnostic quality fails CI the same way a regression in emitted CMake already does.
- A refreshed, real benchmark table and a `benchmarks.yml` GitHub Actions workflow (`workflow_dispatch`) to source Linux/macOS/free-threaded numbers going forward.

**Exit criterion:** a project queries `project.cmake_globals()` to branch on the host platform and, separately, under an explicit cross-compilation toolchain; a newcomer can go from `pip install` to a tested, linked, dependency-using project using only the tutorial; the cookbook and migration guide are real, runnable documents, not stubs; and an error-message regression fails the test suite the same way an emitted-CMake regression does.

**Deferred from this phase:** the benchmark table's Linux, macOS, and free-threaded (`3.14t`) rows remain `_to fill_`, sourced by triggering the new `benchmarks.yml` workflow by hand; only the Windows/CPython 3.13 row was re-measured directly during this phase.

## Phase 5.6: v1.0, the Stability Promise, v1.0.0 (Production/Stable)

v1.0 is a social contract, not a feature list. Declaring it requires:

- C++20/23 modules support (tracking CMake's own maturing support; this lands last on purpose, when the ground stops moving).
- Public API frozen and audited: every class, method, and argument justified or removed. Deprecations from 0.x deleted.
- Documentation complete: tutorial, cookbook, migration guide from raw CMake, API reference.
- Real-world validation: at least a handful of independent projects on 0.x in CI, their issues closed.
- From here on, SemVer with teeth: breaking changes mean 2.0, and `[[deprecated]]`-style migration paths are mandatory (deprecation warnings with the new spelling, one minor version of overlap minimum).

## Beyond 1.0 (unscheduled, honestly)

Ideas we are deliberately _not_ promising dates for: a `cmake-to-cmakeless` importer for existing CMakeLists, workspace/monorepo support, a public emitter API for alternative outputs, remote build integration.

## Non-Goals, Permanently

Repeated here because roadmaps grow by accretion and this one must not:

- **Not a build system.** No compilation scheduling, no dependency scanning of source files. CMake + Ninja own that.
- **Not a CMake replacement.** If CMake ships a feature, our job is to expose it elegantly, not to reimplement it.
- **Not a new language.** `cmakelessfile.py` is plain Python. Any proposal that adds CMakeless-only semantics to Python syntax is rejected on arrival.
- **Not a package repository.** We adapt to vcpkg/Conan/upstream sources; we never host packages.

Want to bend the timeline? The fastest way is to grab a phase item: see [CONTRIBUTING](CONTRIBUTING.md).
