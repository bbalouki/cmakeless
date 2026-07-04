# Changelog

All notable changes to CMakeless are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

## [0.5.4]

The portability release: the industries-readiness work (gaming, finance,
engineering, aerospace) — a curated cross-compilation toolchain gallery,
supply-chain tooling for zero-network builds, static-analysis wiring, and a
one-command environment check (see ROADMAP.md Phase 5.4).

### Added

- **A curated `Toolchain` gallery**: `Toolchain.arm_none_eabi(cpu=...)` (bare-metal
  ARM), `Toolchain.ios(platform=..., deployment_target=...)`, `Toolchain.android(ndk=...,
  abi=..., platform=...)`, and `Toolchain.emscripten(emsdk=...)`, each building on the
  existing `Toolchain` primitives (a compiler/system-name description, or a
  wrapped SDK toolchain file) with the project's signature helpful errors:
  `abi`/`platform` enum typos are rejected immediately, at the call site;
  filesystem existence of a wrapped SDK file is checked at freeze time, same
  as `Toolchain.from_file()`. Android and Emscripten wrap the NDK's/SDK's own
  toolchain file, seeded with the extra cache variables it expects
  (`ANDROID_ABI`, `CMAKE_OSX_SYSROOT`, ...) via a small generated wrapper.
- **`cmakeless sbom --format cyclonedx|spdx`**: a CycloneDX 1.5 or SPDX 2.3
  bill of materials generated straight from `cmakeless.lock`'s already-complete
  dependency inventory, no network or re-resolution required.
- **`cmakeless vendor`**: downloads every locked dependency's archive,
  verifies it against its locked SHA256, and records the local copy in the
  new `cmakeless.mirror.json`, so a later `--offline` build resolves each
  vendored package from disk automatically.
- **`--offline`**: disallows network access during dependency resolution.
  The default `find_package`-then-`FetchContent` backend resolves from the
  lockfile, the mirror map, or a registry-curated hash, raising a clear
  `DependencyError` naming `cmakeless vendor` as the fix when none is
  available; the vcpkg backend checks that its manifest is already installed
  into `vcpkg_installed` before letting configure run; the Conan backend
  passes `--build=never` instead of `--build=missing`, so Conan itself fails
  loudly on anything not already in its local cache. The mirror substitution
  is applied only for emission, never written back into `cmakeless.lock`,
  which keeps recording the canonical upstream pin.
- **`project.lint(clang_tidy=True, iwyu=False)`** and the matching
  **`target.lint(...)`** override: wires `CXX_CLANG_TIDY`/`CXX_INCLUDE_WHAT_YOU_USE`
  per compiled target. The project-wide setting applies to every target that
  has not called its own `lint()` (which always wins, including calling it
  with both arguments `False` to opt a specific target out); header-only
  libraries are silently skipped, since they compile nothing. Both accept
  `True` for the tool's bare default command, or a sequence for extra
  arguments (for example `["clang-tidy", "-checks=-*,modernize-*"]`).
- **`cmakeless doctor`**: a standalone verb (no `cmakelessfile.py` required)
  that checks `cmake`'s presence and version, the auto-selected generator,
  `ccache`/`sccache`/`vcpkg`/`conan` on `PATH`, and network reachability,
  printing exactly what a new machine is missing.
- `Dependencies` joins the public API (it was already the return type of
  `project.dependencies`, but missing from `cmakeless`'s own top-level import
  surface).

### Docs

- `FEATURES.md`, `README.md`, `docs/index.md`, and `examples/README.md`
  updated for the new surface; `examples/11_portability` demonstrates the
  toolchain gallery, `project.lint(...)`, and the `doctor`/`sbom`/`vendor`/
  `--offline` workflow end to end.

## [0.5.3]

The interop unlock: reflect a `.cmake` file or a built-in CMake module through
real CMake, call what it defines, and read the resolved toolchain back after
configure — closing the last gap the `raw_cmake()` escape hatch never
covered (see ROADMAP.md Phase 5.3).

### Added

- **`project.include(path)` / `project.include_module(name, module_path=...)`**:
  reflected includes. Calling either runs real CMake immediately (script
  mode first, falling back to a throwaway configure for the commands script
  mode rejects, such as `add_library()`) to discover the include's
  functions, macros, and variables, and a second, best-effort throwaway
  configure to discover any targets it declares. This is the one exception
  to "generating `CMakeLists.txt` never needs CMake": there is no honest way
  to know what a `.cmake` file defines without running CMake on it, and
  never a hand-written CMake-language parser.
- **`CMakeModule.call(function, *args)`**: validates `function` against the
  include's own discovered functions (case-insensitively, matching CMake)
  before recording it, raising `ConfigurationError` immediately for an
  unknown one; calls are emitted right after the `include()`, in the exact
  order declared, since (unlike `add_command()`/`add_custom_target()`) a
  CMake function call's side effects can be order-dependent.
- **`CMakeModule.variable(name)`**: reads one discovered variable's resolved
  value back into Python, the "read variables from Python" half of the
  original idea this phase carries over from.
- **`project.cmake_info()`**: a post-configure read of the resolved
  generator, compiler ID/version per language, system name/processor, and
  this project's own declared `project.option()`s' final values (after any
  `-D` override or preset `options=` override), via the same CMake File API
  pattern `targets_info()` already uses, no `--trace-expand` and no text
  scraping.
- **The curated dependency registry grew from ten packages to over forty**,
  spanning general-purpose (Abseil, Protobuf, gRPC, OpenSSL, Eigen, ...),
  gaming (SDL2, GLFW, Vulkan, Dear ImGui, ...), and finance/engineering
  staples (QuantLib, OpenCV, Ceres, PROJ, ...); the registration mechanism
  from Phase 5.0 was always the seed, not the ceiling.

### Fixed

- **`targets_info()` (and the new `include()`/`include_module()` target
  discovery) now sees interface, alias, and imported targets.** CMake's
  File API codemodel lists targets with no build rules under a separate
  `abstractTargets` array; only compiled targets were being read before,
  so an `INTERFACE` library or an imported target never appeared.

### Docs

- `FEATURES.md`, `README.md`, and `docs/index.md` updated for the new
  surface; `examples/10_cmake_interop` demonstrates all three calls end to
  end.

## [0.5.2]

### Changed

- **Breaking: `add_python_module()`'s generated `find_package(Python ...)` no
  longer tracks whichever interpreter happens to invoke `cmakeless`.** That
  behavior made the generated `CMakeLists.txt` non-deterministic across
  machines: the same `cmakelessfile.py` emitted a different minimum Python
  version depending on who ran it, violating the emitter's own "same model
  in, byte-identical output out" contract. It now defaults to CMakeless's own
  supported floor (3.12) and accepts an explicit `python_version="3.13"`
  override; a project with several Python modules requesting different
  floors emits the highest one, since `find_package(Python X.Y ...)` already
  means "X.Y or newer."

## [0.5.0]

The language unlock: options, typed conditions, and custom build steps —
the last things standing between "a nicer way to write the easy 90% of
CMake" and the full power of CMake, in Python, with types and a debugger.

### Changed

- **Breaking: the default build description filename is now `cmakelessfile.py`**
  (was `build.py`). `cmakeless.py` was considered and rejected: on a
  case-insensitive filesystem (Windows, macOS) it would collide with the
  installed `cmakeless` package, making `from cmakeless import Project`
  inside the script resolve to itself. `cmakelessfile.py` names the tool the
  way `Dockerfile`/`Jenkinsfile` do, with no such collision. Since the
  project has not published a stable release yet, there is no migration
  path: rename `build.py` to `cmakelessfile.py` in existing projects.
- **Breaking: the Python floor is now 3.12** (was 3.13). IMPROVEMENTS.md
  originally suggested 3.10 for the widest possible reach, but the codebase
  already uses PEP 695 syntax (`type X = ...` aliases, `def f[T](...)`
  generics) introduced in 3.12; keeping the floor at 3.12 avoids rewriting
  that syntax while still covering most current LTS/CI base images. CI now
  tests 3.12 and 3.13 across all three OSes.
- **Breaking: `target.compile_options(..., when=...)` now accepts a `When`
  condition** (see Added, below), or the pre-existing `"gcc|clang"`-style
  compiler string, kept as sugar. The underlying model field is
  `when: WhenModel | None`, replacing `compilers: tuple[str, ...]`.
- **Breaking: `DependencyProvider.pre_configure()`/`.toolchain_args()` now
  require a `build_type` argument.** Fixes the Conan adapter silently
  installing Release dependencies under a Debug preset (IMPROVEMENTS §2.2):
  the active preset's (or `project.optimize`'s) build type now flows all the
  way through to `conan install -s build_type=...`.
- ccache/sccache are now wired for Unix Makefiles and Ninja Multi-Config too,
  not just Ninja (IMPROVEMENTS §2.6); new generator shorthands `"ninja-multi"`,
  `"make"`, and `"xcode"` join `"ninja"` and `"vs"`.
- `find_package(Python ...)` now requests the interpreter actually running
  CMakeless, not a hard-coded `3.13` (IMPROVEMENTS §2.5).

### Added

- **`When` conditions** (SUGGESTIONS §2.2): `When.platform(...)`,
  `When.compiler(...)`, `When.config(...)`, and `When.option(...)`,
  composable with `&`/`|`/`~`, rendered as CMake generator expressions.
  Wired into `define()`, `compile_options()`, and the new `link_options()`.
- **Project options** (IMPROVEMENTS §2.3, SUGGESTIONS §2.1):
  `project.option(name, default=..., help=..., type=...)` declares a typed
  CMake cache variable, discoverable with the new `cmakeless options` verb
  (lists every declared option without building anything) and usable in
  `When.option(...)`.
- **Expanded presets**: `Preset(options={...}, env={...}, inherits="base")`
  so a preset can set cache-variable overrides, an environment block, and
  inherit from another preset (IMPROVEMENTS §2.3), validated the same way
  toolchain references already are.
- **Custom build steps** (SUGGESTIONS §1): `project.add_command(output=[...],
  command=[...], depends=[...], comment=...)` for code-generation and
  asset-cooking steps, and `project.add_custom_target(name, command=[...],
  depends=[...])` for always-run targets (lint, docs). A command's output
  feeds a target's `add_sources()` directly; an output nothing consumes is a
  soft freeze-time warning, not a build error.
- **Target vocabulary completion** (IMPROVEMENTS §2.4): `target.include_dirs(...)`
  (private include directories on any target kind, closing the gap next to
  `Library(public_headers=...)`), `target.link_options(...)` (mirrors
  `compile_options()`), a per-target `cpp_std` override, and
  `target.pch = [...]`/`target.unity = True` for precompiled headers and
  unity builds, retiring the `raw_cmake()` workaround the escape hatch's
  own docstring used to demonstrate.
- **An extensible dependency registry** (IMPROVEMENTS §2.1):
  `cmakeless.register_dependency(name, RegistryEntry(...))` registers or
  overrides one package, and installed plugin distributions can contribute
  entries via the `"cmakeless.registry"` entry-point group. The curated list
  itself stays the same ten packages for now; growing it from vcpkg/Conan
  metadata at scale is future work (see ROADMAP.md sub-phase 4.4).

### Docs

- `ROADMAP.md`'s Phase 4 is now followed by sub-phases 4.1–4.3 (this
  release) and 4.4–4.6 (planned: the interop unlock, the portability
  release, and documentation/quality debt, see ROADMAP.md for what each
  covers).
- `FEATURES.md` and `README.md` updated throughout for the new surface.

## [0.4.1]

Sensible defaults, the escape hatch, and a release pipeline: the polish that
makes the interop and quality-of-life work land in a real project.

### Changed

- **Default binding backend is now pybind11** (was nanobind):
  `add_python_module(name, sources)` builds a pybind11 extension unless you pass
  `binding="nanobind"`. This is a behavior change for callers that relied on the
  implicit default.
- **Default test framework is now GoogleTest** (was Catch2):
  `add_test(name, sources)` fetches and links GoogleTest unless you pass
  `framework="catch2"` (or `"doctest"`/`"none"`). Also a behavior change for the
  implicit default.

### Added

- **The escape hatch (FEATURES section 9), now implemented**:
  `target.raw_cmake("...")` emits a verbatim CMake snippet after the target is
  defined, and `project.raw_cmake_file("cmake/extra.cmake")` includes an existing
  CMake file near the top of the generated `CMakeLists.txt`. Both are fenced with
  a comment naming their `cmakelessfile.py` origin; `raw_cmake_file` paths are validated
  to exist inside the project root at freeze time.
- **Project-level `optimize` and `lto`** (FEATURES section 3): `project.optimize =
  "release"` and `project.lto = True` set the default (no-preset) build type and
  interprocedural optimization. Both are emitted behind CMake guards, so an active
  preset always wins.
- **A tag-driven release workflow** (`.github/workflows/release.yml`): pushing a
  `v*` tag builds the sdist and wheel, publishes to PyPI via Trusted Publishing
  (OIDC, no stored token), and cuts a GitHub Release from the matching changelog
  section. The pushed tag is checked against `_version.py`.

### Docs and examples

- Rewrote `README.md` into a fuller, discoverable front door: the philosophy,
  a concrete end-to-end workflow, a feature tour, and an ecosystem comparison.
- Reworked `examples/07_python_module` into a real pybind11 module (a `Vec2`
  type with operators, properties, and C++-to-Python exception translation),
  and added `examples/08_capstone`: one `cmakelessfile.py` shipping a library as a CLI,
  a GoogleTest suite, and a pybind11 module, with presets, install/export, CPack,
  and a live Observer.
- Corrected the project URLs to `github.com/bbalouki/cmakeless`.

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
on CI using only `cmakelessfile.py`.

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
  child projects (their own `cmakelessfile.py`); every generated file is standalone.
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
- `cmakeless build` CLI and `python -m cmakeless`; `python cmakelessfile.py` works as
  a first-class entry point.
- Exception hierarchy: `CmakelessError` with `ConfigurationError`,
  `DependencyError`, `ToolchainError`, and `CMakeError`.
