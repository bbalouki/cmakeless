# CMakeless Architecture

This document describes how CMakeless is designed, how the codebase is organized, and why each decision was made. If [INTRODUCTION](INTRODUCTION.md) is the "why", this is the "how".

## Design Goals

Every architectural decision below serves four goals, in priority order:

1. **A tiny, obvious public API.** The end user sees a handful of classes. Everything else is private machinery.
2. **Fail early, fail in Python.** Every error that can be caught before CMake runs must be caught before CMake runs, and reported as a normal Python exception with a helpful message.
3. **Readable output.** The generated `CMakeLists.txt` must look like an expert wrote it by hand: modern, target-centric, deterministic, diffable. Users must be able to walk away from CMakeless at any time and keep their build.
4. **Delegate, never reimplement.** CMake does the real work: configuring, generating, building. CMakeless is a frontend, not a build system.

## The Big Picture: Four Layers

CMakeless is a strict layered architecture. Each layer depends only on the layer directly below it. Data flows down; results and errors flow back up.

```text
+--------------------------------------------------------------+
|  1. API layer          cmakeless/api/                         |
|     What the user touches: Project, Executable, Library,     |
|     Dependency, Toolchain, Preset. Friendly, forgiving,      |
|     mutable while the user is describing the build.          |
+--------------------------------------------------------------+
                              | freeze() + validate
                              v
+--------------------------------------------------------------+
|  2. Model layer        cmakeless/model/                       |
|     The single source of truth: an immutable, validated      |
|     build graph made of frozen dataclasses. No CMake         |
|     knowledge, no subprocess calls, pure data.               |
+--------------------------------------------------------------+
                              | visit
                              v
+--------------------------------------------------------------+
|  3. Emitter layer      cmakeless/emitter/                     |
|     Walks the model and generates idiomatic, modern          |
|     CMakeLists.txt, preset files, and toolchain files.       |
|     Deterministic: same model in, same bytes out.            |
+--------------------------------------------------------------+
                              | invoke
                              v
+--------------------------------------------------------------+
|  4. Driver layer       cmakeless/driver/                      |
|     Runs cmake / ctest / cpack as subprocesses, consumes     |
|     the CMake File API for structured results, and           |
|     translates CMake failures into Python exceptions.        |
+--------------------------------------------------------------+
```

### Why layers, and why these layers

The separation between **API** and **model** exists because the two have opposite needs. While the user is describing a build, objects must be mutable and forgiving (`app.link(engine)` after construction). Once description ends, everything downstream wants immutability: the emitter can cache, the validator can reason about the whole graph at once, and parallel threads can share the model without locks. `Project.build()` is the boundary: it freezes the API objects into the model, validates, and only then proceeds.

The separation between **model** and **emitter** is what keeps us honest about goal 4. The model knows nothing about CMake syntax. This means the emitter is replaceable and testable in isolation (feed it a model, assert on the generated text), and it leaves the door open for other emitters later (for example, a compile_commands-only emitter for tooling) without touching the user-facing API.

The separation between **emitter** and **driver** means generation never requires CMake to be installed. You can generate, inspect, and commit build files on a machine that has never seen a compiler. Only `build()`, `configure()`, and `test()` need the real tool.

## The Public API

The user-facing surface is intentionally small, and the intent is that the classes you actually construct in a `cmakelessfile.py` stay close to this size forever:

| Class                       | Role                                                                                                        |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `Project`                    | The root object and facade. Owns targets, settings, and the `build()`/`configure()`/`test()`/`install()` verbs. |
| `Executable`                  | A runnable target. Created via `project.add_executable(...)`.                                                |
| `Library`                     | A static, shared, or header-only library. Created via `project.add_library(...)`.                            |
| `Test`                        | A test executable registered with CTest. Created via `project.add_test(...)`.                                |
| `PythonModule`                | A pybind11/nanobind extension module. Created via `project.add_python_module(...)`.                          |
| `Dependency`                  | An external package requirement, usually created implicitly by `target.depends("fmt/10.2.1")`.               |
| `Toolchain`                   | A compiler/platform description for cross or pinned builds.                                                  |
| `Preset`                      | A named bundle of configuration (build type, flags, toolchain) mapped onto CMake presets.                    |
| `Option`                      | A typed CMake cache variable. Created via `project.option(...)`.                                             |
| `When`                        | A composable build-time condition (`&`/`\|`/`~`), for `define()`, `compile_options()`, and friends.           |
| `Command` / `CustomTarget`    | A custom build step or always-run target. Created via `project.add_command(...)`/`add_custom_target(...)`.  |
| `CMakeModule`                 | A reflected `include()`/`include_module()`, with validated `.call()`/`.variable()` access.                   |
| `CMakeGlobals`                | Every CMake variable a real configure defined, as attributes. Created via `project.cmake_globals()`.         |

Alongside these builders, the public surface also re-exports read-only result types (`CMakeInfo`, `CompilerInfo`, `TargetInfo`, `RegistryEntry`), the `Observer` event types (`StepStarted`, `StepFinished`, `StepFailed`, `BuildEvent`), and the error hierarchy (see below): data and diagnostics you read, not classes you construct. `cmakeless.__all__` is the authoritative, current list.

Users never import from `cmakeless.model`, `cmakeless.emitter`, or `cmakeless.driver`. Those are implementation details, and the package layout enforces it: only names re-exported in `cmakeless/__init__.py` are public, and the package ships `py.typed` so every signature is checked by the user's IDE and type checker.

A deliberate non-feature: there is no CMakeless DSL, no YAML dialect, no magic globals. A `cmakelessfile.py` is a plain Python script that happens to import `cmakeless`. Anything Python can do (conditionals, loops, functions, reading environment variables, importing your own helper modules), your build description can do, with zero new semantics to learn.

## Entry Points: `cmakelessfile.py` and the CLI

The user's build description lives in **`cmakelessfile.py`** at the project root. This is a convention, not a requirement, chosen deliberately over a single-module design ("just one `cmakeless.py` file") for three reasons:

1. `cmakelessfile.py` names the user's _intent_ (this file builds the project), the way `conanfile.py` and `noxfile.py` do, while `cmakeless.py` would name our library and shadow the actual `cmakeless` package on the import path, a classic Python footgun.
2. The library itself must be a package, not a module, because the four layers above need separate, privately importable subpackages to grow without breaking users.
3. A predictable filename lets the CLI find the build description with zero configuration.

Both invocation styles are first-class:

```console
$ python cmakelessfile.py   # the script is the tool
$ cmakeless build           # the CLI finds cmakelessfile.py and runs it
$ cmakeless configure --preset debug
$ cmakeless test
$ cmakeless clean
$ cmakeless init            # scaffold a new project interactively
```

The `cmakeless` console script and `python -m cmakeless` share one implementation in `cmakeless/cli.py`.

## Repository Layout

Standard src-layout, so the installed package is what gets tested, not the working directory:

```text
cmakeless/
├── pyproject.toml            # PEP 621 metadata; zero runtime dependencies
├── README.md
├── CONTRIBUTING.md
├── CHANGELOG.md
├── src/
│   └── cmakeless/
│       ├── __init__.py       # the ONLY public import surface
│       ├── py.typed
│       ├── cli.py
│       ├── errors.py         # exception hierarchy (see below)
│       ├── api/              # layer 1: Project, targets, deps, toolchains
│       ├── model/            # layer 2: frozen dataclasses, validation
│       ├── emitter/          # layer 3: model -> CMakeLists.txt
│       ├── driver/           # layer 4: subprocess + CMake File API
│       └── deps/             # dependency-provider strategies (see below)
├── tests/
│   └── unittests/            # mirrors src/ structure; pytest
├── examples/                 # runnable example projects, smallest first
└── docs/
    ├── index.md              # documentation site entry point
    ├── INTRODUCTION.md       # the why: problem, idea, and why Python
    ├── ARCHITECTURE.md       # this file
    ├── FEATURES.md           # the before/after feature catalog
    ├── ROADMAP.md            # phase-by-phase plan
    ├── tutorial.md           # a ten-minute, linear first project
    ├── cookbook.md           # task-oriented recipes
    ├── migration.md          # introducing CMakeless into raw CMake
    └── benchmarks.md         # measured parallelism wins
```

`pyproject.toml` declares **zero runtime dependencies**. A tool whose reason to exist is reducing build friction cannot itself bring a dependency tree. The standard library is enough: `dataclasses` for the model, `subprocess` for the driver, `json` for the File API, `argparse` for the CLI.

## Design Patterns, Named

CMakeless uses classic, [design patterns](https://github.com/bbalouki/DesignPatterns) deliberately, so that any contributor can locate responsibility by name:

- **Facade.** `Project` is a facade over the entire pipeline. `project.build()` hides freeze, validate, emit, configure, and compile behind one verb. The library as a whole is a facade over CMake.
- **Builder.** The API layer is a builder for the model layer: users incrementally describe (`add_library`, `link`, `depends`), then `freeze()` produces the immutable product.
- **Visitor.** The emitter is a visitor over the build graph. Each node type (executable, library, test, install rule) has a visit method that contributes its section of the generated file. New node types plug in without modifying the traversal.
- **Strategy.** Anything with interchangeable backends is a strategy behind a small interface: CMake generators (Ninja, Visual Studio, Xcode), and above all **dependency providers**.
- **Adapter.** Each dependency provider in `cmakeless/deps/` (FetchContent, `find_package`, vcpkg, Conan) adapts a foreign tool to the single internal `DependencyProvider` interface, so `target.depends("fmt/10.2.1")` never changes when the backend does.
- **Composite.** A `Project` may contain subprojects; targets and subprojects form a tree that the emitter and validator traverse uniformly.
- **Template Method.** Target emission shares a fixed skeleton (declare, sources, properties, links, install) with per-target-type overrides, which is what keeps the generated CMake uniform and boring.
- **Observer.** The driver publishes progress events (configure started, target compiled, test finished) to subscribers, so the CLI progress display, IDE integrations, and CI log formatting are listeners, not special cases inside the driver.

## Error Handling: Errors Are a Feature

The single biggest quality-of-life difference over raw CMake is _when_ and _how_ things fail. The rules:

1. **Validate at freeze time.** Unknown source files, dependency cycles, linking a test-only target into a release binary, a typo in a C++ standard: all reported before CMake is ever invoked, with the offending `cmakelessfile.py` line in the traceback.
2. **Translate at run time.** When CMake or the compiler does fail, the driver parses the output and raises a structured exception instead of dumping a wall of text.
3. **One hierarchy.** Everything raised on purpose derives from `CmakelessError`:

```text
CmakelessError
├── ConfigurationError      # invalid build description (caught at freeze)
├── DependencyError         # package cannot be resolved/fetched
├── ToolchainError          # compiler/toolchain missing or misconfigured
└── CMakeError              # CMake itself failed; carries parsed stderr,
                            # the exact command line, and the log path
```

Every message must say three things: what went wrong, where (file and target), and what to try next. A message that fails the "what to try next" test is a bug.

## Free-Threaded Python: Parallelism Where It Pays

CMakeless targets Python 3.12+ (CI also runs 3.13) and is designed for the free-threaded interpreter (PEP 703, supported non-experimentally since 3.14). The immutable model layer is what makes this safe and cheap: frozen dataclasses can be shared across threads with no locks and no copies.

Parallelism is applied only where wall-clock time actually lives:

- **Dependency resolution.** Fetching and resolving N external packages is embarrassingly parallel network and disk I/O; each provider strategy runs in its own thread.
- **Multi-configuration emission.** Emitting Debug/Release/RelWithDebInfo trees, or several presets, are independent pure functions over the same frozen model.
- **Orchestration.** Driving multiple CMake configurations or test partitions concurrently, with the Observer events merged into one coherent progress stream.

On a standard GIL build everything still works; the executor degrades to interleaved I/O concurrency, which is where most of the benefit is anyway. Detection is a single startup check (`sys._is_gil_enabled()`), never a fork in the codebase.

The compile itself is _not_ our parallelism: that belongs to Ninja and the compiler, and per goal 4 we delegate it.

## What the Emitter Must Guarantee

Because the generated `CMakeLists.txt` is our public face to the rest of the ecosystem, it has its own contract:

- **Modern, target-centric CMake only.** `target_include_directories`, `target_compile_features`, `target_link_libraries` with explicit visibility. Never directory-level globals, never `include_directories()`, never `file(GLOB)` at configure time (globs are expanded by CMakeless in Python, where they can be validated).
- **Deterministic.** Same model in, byte-identical output out. Sorted where order is arbitrary. This makes output committable and diffs reviewable.
- **Self-describing.** A generated header comment states the CMakeless version and the source `cmakelessfile.py`, so a reader landing in the file knows where the truth lives.
- **Standalone.** The output must build with plain `cmake` on a machine without Python. This is the no-lock-in promise made mechanical.

## Read Next

- [FEATURES](FEATURES.md): The complete feature surface built on this architecture.
- [ROADMAP](ROADMAP.md): The order in which these layers get built.
- [CONTRIBUTING](../CONTRIBUTING.md): How to help build them.
