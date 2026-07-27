# Cookbook

Task-oriented recipes. Each one is a complete, minimal answer to "how do I ___ in CMakeless"; none
require reading the rest of the documentation first. Recipes are grouped by concern, roughly in the
order a growing project needs them. See [FEATURES](FEATURES.md) for the full catalog and
[tutorial](tutorial.md) if you want the guided walkthrough instead.

## Targets and Linking

### Add an include directory and a private include directory

Public headers consumers should see go through `public_headers=` on `add_library(...)`. Private
headers a target's own sources need, but consumers never should, use `include_dirs()`:

```python
engine = project.add_library("engine", sources=["src/engine/*.cpp"], public_headers="include/")
engine.include_dirs("src/engine/internal")  # PRIVATE: never exposed to anything linking engine
```

### Link one library into another with the right visibility

`app.link(engine)` links privately by default, the right call for an executable. Library-to-library
linking states visibility as a plain argument, and CMakeless picks the correct CMake keyword:

```python
engine.link(math_lib, public=True)  # users of engine also need math_lib's headers/symbols
engine.link(zlib_dep)  # implementation detail: stays private, never leaks out
```

Header-only libraries pick `INTERFACE` automatically, since there is no other correct answer for a
target with nothing to compile.

### Build a header-only library

Omit `sources=`, or pass an empty sequence; only `public_headers=` is required:

```python
config = project.add_library("config", public_headers="include/config/")
app.link(config)
```

CMakeless emits `add_library(config INTERFACE)` and skips anything that assumes compiled objects
(`cpp_std` overrides, `pch`, `unity`, and `lint()` all raise or no-op with a clear message on a
header-only target, rather than silently doing nothing).

### Give one target its own C++ standard

```python
project = Project("mygame", cpp_std=23)
vendored_core = project.add_library("vendored_core", sources=["third_party/core/*.c*"])
vendored_core.cpp_std = 17  # this target only; everything else stays at 23
```

Useful for a vendored dependency you build from source but did not write, without splitting it into
a second `Project`.

### Split a project into subprojects

```python
project.add_subproject("tools/asset_packer")  # its own cmakelessfile.py, its own Project
```

The child directory needs its own `cmakelessfile.py` describing exactly one `Project`; CMakeless
runs it in description mode (its `project.build()` call registers the project instead of building
it) and mounts it, replacing `add_subdirectory` plus the folklore about which variables cross a
directory boundary. A subproject that tries to mount its own ancestor is a `ConfigurationError` at
freeze time, not a CMake-level infinite recursion.

### Precompile headers and enable unity builds

```python
engine.pch = ["<vector>", "src/engine/pch.hpp"]  # system headers verbatim, project headers quoted
engine.unity = True
```

Both raise a clear error on a header-only library, which compiles nothing to precompile or unify.

---

## Dependencies and Supply Chain

### Depend on a package outside the built-in registry

The registry (`fmt`, `boost`, `spdlog`, `sdl2`, and around forty others) is a seed, not a ceiling.
For a one-off package, tell `depends()` what CMake should see:

```python
app.depends(
    "mylib/2.1.0",
    cmake_name="MyLib",
    targets=["mylib::mylib"],
    url="https://example.com/mylib/mylib-2.1.0.tar.gz",
    sha256="…",
)
```

Get the name wrong and CMakeless says so immediately, before touching CMake, and lists every name
it does know:

```console
cmakeless: error: Unknown package 'not_a_real_package': the built-in registry only knows
abseil, assimp, benchmark, boost, ... zlib. To use it anyway, tell depends() what CMake
should see, for example depends("not_a_real_package/1.0.0", cmake_name=..., targets=[...], url=..., sha256=...).
```

If you reach for this often for the same package across projects, register it once instead (next
recipe) so every `cmakelessfile.py` gets the short form back.

### Register a package the whole team can reuse

```python
import cmakeless
from cmakeless import RegistryEntry

cmakeless.register_dependency(
    "mylib",
    RegistryEntry(cmake_name="MyLib", targets=("mylib::mylib",), vcpkg_name="mylib"),
)
```

Call this once, near the top of `cmakelessfile.py` (or in a small shared module every project
imports), and `app.depends("mylib/2.1.0")` works with no further arguments anywhere else in the
codebase. Shipping it as an installed plugin instead, so every project on the machine gets it with
zero per-project code, is one `pyproject.toml` entry point away:

```toml
# pyproject.toml of a plugin package
[project.entry-points."cmakeless.registry"]
mylib = "my_plugin:registry_entries"   # a zero-argument callable returning RegistryEntry or dict[str, RegistryEntry]
```

An explicit `register_dependency()` call always wins over a plugin-supplied entry, and a plugin
never overrides a built-in package name.

### Depend on a package with components

```python
app.depends("boost/1.84.0", components=["asio", "beast"])
```

Only the requested components are requested from `find_package`/fetched, and only their imported
targets are linked; leave `components=` off for packages that ship one target.

### Use a private dependency mirror

`cmakeless.mirror.json` maps a package name to the URL a build actually fetches from;
`cmakeless.lock` keeps recording the canonical upstream pin regardless, so the substitution is
invisible outside your own network. Write it by hand for an internal artifact mirror:

```json
{
  "schema": 1,
  "mirrors": {
    "fmt": "https://artifacts.internal.example.com/mirror/fmt-10.2.1.tar.gz"
  }
}
```

Every subsequent `cmakeless build` (online or `--offline`) fetches `fmt` from that URL instead of
upstream.

### Vendor dependencies for a zero-network build

For a build machine with no network access at all, let CMakeless populate the mirror map from
locally downloaded copies instead of writing it by hand:

```console
$ cmakeless lock                 # resolve and pin every dependency
$ cmakeless vendor                # download and hash-verify each one into vendor/, record it in cmakeless.mirror.json
$ cmakeless build --offline       # resolve from the vendored copies, no network at all
```

`--offline` refuses to fetch anything not already available rather than silently reaching the
network: a `DependencyError` names `cmakeless vendor` as the fix if something is missing. The
vcpkg backend checks its own `vcpkg_installed` output instead, and the Conan backend passes
`--build=never`, so both refuse a network fetch on their own terms too.

### Keep dependency resolution reproducible across machines

```console
$ cmakeless lock
```

Refreshes `cmakeless.lock` explicitly (equivalent to `project.dependencies.lock()` from Python),
without building anything. Commit the lockfile: every teammate and every CI job resolving against
it gets the identical archive, verified against the identical hash, regardless of what else that
machine happens to have installed or cached.

### Generate a bill of materials

```console
$ cmakeless sbom --format cyclonedx      # or --format spdx
```

Reads `cmakeless.lock`'s already-complete dependency inventory, no re-resolution or network needed,
and writes a CycloneDX 1.5 or SPDX 2.3 document naming every fetched package, its pinned version,
and its source URL.

---

## Compiler Settings and Conditions

### Turn on strict warnings, an optimization level, and LTO

```python
project.warnings = "strict"  # or "default", "none"
project.optimize = "release"  # ignored once a preset is active; see Presets below
project.lto = True
app.sanitize = ["address", "undefined"]
```

`warnings="strict"` becomes `/W4 /permissive-` on MSVC and
`-Wall -Wextra -Wconversion -Wsign-conversion -pedantic` on GCC/Clang, so you never maintain the
per-compiler translation table yourself. `ccache`/`sccache` are auto-detected and wired in
automatically; opt out project-wide with `project.cache = False`.

### Guard code with `When` conditions

```python
from cmakeless import When

app.define("USE_D3D12", when=When.platform("windows"))
app.compile_options("-march=native", when=When.compiler("gcc", "clang"))
app.define("ENABLE_TRACING", when=When.config("Debug"))
app.define("HAS_GUI", when=When.option(gui))  # gui = project.option(...)
app.define("VERBOSE_ASAN", when=When.compiler("clang") & When.config("Debug"))
```

One factory set (`platform`, `compiler`, `config`, `option`) composed with `&`/`|`/`~` covers every
condition `define()`, `compile_options()`, and `link_options()` accept; CMakeless decides internally
whether a given condition becomes a generator expression or an `if()` block, so the choice never
leaks into your code. The legacy `when="gcc|clang"` string is still valid sugar for
`When.compiler("gcc", "clang")`.

### Declare a project-wide option

```python
from cmakeless import When

gui = project.option("MYLIB_BUILD_GUI", default=True, help="Build the Qt front-end")
app.define("HAS_GUI", when=When.option(gui))
```

```console
$ cmakeless options
[cmakeless] MYLIB_BUILD_GUI (bool, default=True): Build the Qt front-end
```

`project.option(...)` declares a real CMake cache variable, discoverable without reading a single
line of `cmakelessfile.py`, and overridable per preset (see below).

### Run a sanitized test suite

```console
$ cmakeless test --sanitize=address
```

No changes to `cmakelessfile.py` required: the sanitizer preset is applied on top of your existing
`add_test(...)` targets, in its own build tree, so your normal build is untouched. Combine
sanitizers with a comma (`--sanitize=address,undefined`); an unsupported pairing for the active
compiler (some ASan+MSVC combinations, for instance) is rejected with a `ToolchainError` rather than
a confusing compiler-level failure.

---

## Presets and Toolchains

### Define Debug, Release, and CI presets with inheritance

```python
from cmakeless import Preset

project.add_preset(Preset("debug", optimize="none", sanitize=["address"]))
project.add_preset(Preset("release", optimize="release", lto=True))
project.add_preset(
    Preset(
        "ci",
        inherits="release",
        options={"MYLIB_BUILD_GUI": False},
        env={"CI": "1"},
    )
)
```

```console
$ cmakeless build --preset release
```

Each preset gets its own out-of-source build directory, and `CMakePresets.json` is generated
alongside `CMakeLists.txt`, so CLion, Visual Studio, and VS Code's CMake Tools pick every preset up
natively. `inherits=` is cycle-checked at freeze time; `options=` is validated against declared
`project.option()`s, so a typo in an overridden option name fails before CMake runs.

### Cross-compile for ARM

Register a toolchain from the curated gallery, then reference it from a preset:

```python
from cmakeless import Preset, Toolchain

project.add_toolchain(Toolchain.arm_none_eabi(cpu="cortex-m4"))
project.add_preset(Preset("firmware", toolchain="arm-none-eabi", optimize="release"))
```

```console
$ cmakeless build --preset firmware
```

Registering the toolchain never requires the SDK to be installed; only building with a preset that
references it does. For a target triple the gallery does not cover, describe it directly:

```python
project.add_toolchain(
    Toolchain(
        "arm64-linux",
        compiler="aarch64-linux-gnu-g++",
        system_name="Linux",
        system_processor="aarch64",
    )
)
```

or wrap an existing toolchain file unchanged:

```python
project.add_toolchain(Toolchain.from_file("cmake/rpi4.toolchain.cmake"))
```

### Cross-compile for iOS, Android, or WebAssembly

The same two primitives (`Toolchain.from_file(...)` or a fully described `Toolchain(...)`) back a
curated gallery entry per platform, each seeded with the cache variables that platform actually
needs:

```python
from cmakeless import Preset, Toolchain

project.add_toolchain(Toolchain.ios(platform="OS64", deployment_target="13.0"))
project.add_preset(Preset("ios-device", toolchain="ios-os64"))

project.add_toolchain(Toolchain.android(ndk="/opt/android-ndk", abi="arm64-v8a"))
project.add_preset(Preset("android-arm64", toolchain="android-arm64-v8a"))

project.add_toolchain(Toolchain.emscripten())  # reads the EMSDK environment variable
project.add_preset(Preset("wasm", toolchain="emscripten"))
```

A typo'd `abi=`/`platform=` value is rejected immediately at the call site, the same way
`When.compiler(...)` validates its own tokens; Android and Emscripten wrap the NDK's/SDK's own
toolchain file, checked for existence at freeze time, so cross-compiling is never a hand-written
toolchain file away. Gate SDK-dependent entries behind the environment variable the SDK itself sets
(`"EMSDK" in os.environ`, `os.environ.get("ANDROID_NDK_HOME")`) so the same `cmakelessfile.py` still
builds for the host on a machine without that SDK installed.

---

## Testing

### Switch test frameworks

```python
tests = project.add_test("engine_tests", sources=["tests/*.cpp"], framework="catch2")
```

`"gtest"` is the default; `"doctest"` and `"catch2"` are fetched and wired into CTest discovery the
same way. Pass `framework="none"` for a plain executable whose exit code is the verdict, useful for
a hand-rolled test runner CMakeless does not need to understand.

---

## Custom Build Steps

### Add a code-generation step

```python
gen = project.add_command(
    output=["generated/version.cpp"],
    command=["python", "tools/gen_version.py", "--out", "generated/version.cpp"],
    depends=["tools/gen_version.py"],
)
app.add_sources(gen)  # wires the dependency edge; CMakeless validates it is actually consumed
```

Commands are argument lists, never shell strings: portable across cmd and POSIX by construction,
and immune to injection (CMake's `VERBATIM` keyword is always emitted). An output nothing consumes
is a freeze-time warning, not a silent gap or a build-time surprise.

### Cook assets with an always-run custom target

```python
project.add_custom_target(
    "cook-assets",
    command=["python", "tools/cook_assets.py", "assets/manifest.txt"],
    depends=["tools/cook_assets.py", "assets/manifest.txt"],
)
```

No `output=` means the target has nothing CMake can treat as up to date, so it reruns every build,
the right shape for asset cooking, linting, or documentation generation as opposed to a single
generated source file (the previous recipe).

---

## Install, Packaging, and Tooling

### Install and package a release

```python
project.install(engine, headers=True)
project.install(app)
project.package(formats=["zip", "deb"])
```

```console
$ cmakeless install --prefix dist
$ cmakeless package
```

`project.install(...)` also writes export sets and a `Config.cmake`, so another CMake project can
`find_package(mygame)` yours the same way `app.depends(...)` finds a third-party one.
`project.package(...)` needs no separate configuration beyond the requested CPack `formats=`.

### Lint every target with clang-tidy or include-what-you-use

```python
project.lint(clang_tidy=True, iwyu=False)  # every compiled target
vendored_core.lint(clang_tidy=False)  # this one library opts out
strict_lib.lint(
    clang_tidy=["clang-tidy", "-checks=-*,modernize-*"]
)  # explicit checks, this target only
```

A target's own `lint()` call always wins over the project-wide default, including turning both
tools off deliberately. Header-only libraries are silently skipped, since they compile nothing to
lint.

### Check what a new machine is missing

```console
$ cmakeless doctor
```

No `cmakelessfile.py` required. Reports CMake's version, the generator CMakeless would
auto-select, `ccache`/`sccache`/`vcpkg`/`conan` on `PATH`, and network reachability, in one command.
Run it first when a teammate reports "it builds for me" but not for them.

---

## Python Interop

### Ship Python bindings

```python
bindings = project.add_python_module("mymath", sources=["src/bindings.cpp"])  # pybind11 by default
bindings.link(engine)
```

```console
$ cmakeless build
$ python -c "import mymath; print(mymath.__doc__)"
```

The built module lands in your current environment automatically; `import` works the moment the
build finishes. Pass `binding="nanobind"` for the other backend, which also generates a `.pyi`
stub unless `stubs=False`.

### Pin a minimum Python version for a binding module

```python
bindings = project.add_python_module("mymath", sources=["src/bindings.cpp"], python_version="3.13")
```

The generated `find_package(Python ...)` version defaults to CMakeless's own supported floor,
independent of whichever interpreter happens to invoke `cmakeless`, so two machines with different
Python versions installed still get byte-identical `CMakeLists.txt`. Raise it explicitly only when a
module needs newer C API surface; multiple modules with different floors combine to the highest one
requested.

---

## CMake Reflection and Introspection

### Query the platform before you link

`project.cmake_globals()` runs a throwaway CMake configure immediately and hands back every
variable CMake defined, so you can branch before anything is emitted:

```python
cmake = project.cmake_globals()

if hasattr(cmake, "WIN32"):
    app.depends("dirent")  # a POSIX-dirent shim, only needed on Windows
```

Remember: `hasattr(cmake, name)` mirrors CMake's `if(DEFINED name)`. `WIN32`/`APPLE`/`UNIX`/`ANDROID`
are only ever *set*, never defined-and-false, so this is exactly the right check. Pass a registered
toolchain (`project.cmake_globals(toolchain=Toolchain.android(...))`) to probe the platform a cross
build targets instead of the host; results are cached per toolchain, so a second call with the same
argument reuses the first probe.

### Reflect a custom `.cmake` helper or a built-in CMake module

```python
summary = project.include("cmake/print_build_summary.cmake")
summary.call("print_build_summary", "mygame")  # validated against what the file defines
version = summary.variable("PROJECT_HELPER_VERSION")  # read a value it defines back into Python

checks = project.include_module("CheckCXXCompilerFlag")  # a real built-in CMake module
checks.call("check_cxx_compiler_flag", "-Wall", "HAS_WALL")
```

CMakeless runs real CMake the moment `include()`/`include_module()` is called to discover the
file's functions, macros, and variables, script mode first and falling back to a throwaway configure
for the commands script mode rejects. `.call(...)` is validated against what was actually found,
case-insensitively, before anything is emitted, and lands right after the `include()` in the exact
order you wrote it, since a CMake function's side effects can be order-dependent. This is the one
exception to "generating `CMakeLists.txt` never needs CMake": CMake must be on `PATH` the moment
either method is called, not just at build time.

### Read back the resolved generator, compiler, and system

```python
info = project.cmake_info()
print(info.generator, info.system_name, info.system_processor)
for compiler in info.compilers:
    print(compiler.language, compiler.compiler_id, compiler.compiler_version)
```

A post-configure read via the same CMake File API pattern `targets_info()` uses: no
`--trace-expand`, no scraping `CMakeCache.txt` by hand.

### Read the configured build as Python objects

```python
for target in project.targets_info():
    print(target.name, target.type)
```

Returns the fully configured build as `TargetInfo` objects straight from the CMake File API,
useful for a custom packaging step, a dependency graph visualizer, or an assertion in a test that
a target you expect to exist actually does.

### Stream build progress to your own tooling

```python
from cmakeless import Observer, StepFailed, StepFinished, StepStarted


class MyObserver:
    def on_event(self, event) -> None:
        if isinstance(event, StepStarted):
            print(f"start: {event.step}")
        elif isinstance(event, StepFinished):
            print(f"done: {event.step}")
        elif isinstance(event, StepFailed):
            print(f"failed: {event.step} (exit {event.exit_code})")


project.add_observer(MyObserver())
```

Any object with an `on_event(event)` method satisfies the `Observer` protocol; the driver publishes
one event per pipeline step to every registered observer, the same mechanism the default console
output uses, so an IDE extension or a CI log formatter is a listener, not a special case.

---

## The Escape Hatch

### Drop to raw CMake for the 1%

```python
engine.raw_cmake("set_property(TARGET engine PROPERTY JOB_POOL_COMPILE heavy_jobs)")
project.raw_cmake_file("cmake/legacy_weirdness.cmake")
```

Raw snippets are emitted verbatim into the generated file, clearly fenced with comments naming
their `cmakelessfile.py` origin. This is deliberately a little ugly: if you reach for it often for
the same thing, that is a feature request, not a workflow (see
[CONTRIBUTING](https://github.com/bbalouki/cmakeless/blob/main/CONTRIBUTING.md)). It is also the
bridge for [migrating an existing CMakeLists.txt](migration.md) one target at a time, via
`project.raw_cmake_file("CMakeLists.legacy.cmake")`.
