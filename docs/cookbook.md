# Cookbook

Task-oriented recipes. Each one is a complete, minimal answer to "how do I ___ in CMakeless"; none require reading the rest of the documentation first. See [FEATURES](FEATURES.md) for the full catalog and [tutorial](tutorial.md) if you want the guided walkthrough instead.

## Add an include directory

Public headers consumers should see go through `public_headers=` on `add_library(...)`. Private headers a target's own sources need, but consumers never should, use `include_dirs()`:

```python
engine = project.add_library("engine", sources=["src/engine/*.cpp"], public_headers="include/")
engine.include_dirs("src/engine/internal")   # PRIVATE: never exposed to anything linking engine
```

## Cross-compile for ARM

Register a toolchain from the curated gallery, then reference it from a preset:

```python
from cmakeless import Preset, Toolchain

project.add_toolchain(Toolchain.arm_none_eabi(cpu="cortex-m4"))
project.add_preset(Preset("firmware", toolchain="arm-none-eabi", optimize="release"))
```

```console
$ cmakeless build --preset firmware
```

Registering the toolchain never requires the SDK to be installed; only building with a preset that references it does. For a target triple the gallery does not cover, describe it directly:

```python
project.add_toolchain(Toolchain("arm64-linux", compiler="aarch64-linux-gnu-g++", system_name="Linux", system_processor="aarch64"))
```

or wrap an existing toolchain file unchanged:

```python
project.add_toolchain(Toolchain.from_file("cmake/rpi4.toolchain.cmake"))
```

## Use a private dependency mirror

`cmakeless.mirror.json` maps a package name to the URL a build actually fetches from; `cmakeless.lock` keeps recording the canonical upstream pin regardless, so the substitution is invisible outside your own network. Write it by hand for an internal artifact mirror:

```json
{
  "schema": 1,
  "mirrors": {
    "fmt": "https://artifacts.internal.example.com/mirror/fmt-10.2.1.tar.gz"
  }
}
```

Every subsequent `cmakeless build` (online or `--offline`) fetches `fmt` from that URL instead of upstream. For a zero-network build from packages you already have, let CMakeless populate the file for you instead:

```console
$ cmakeless lock                 # resolve and pin every dependency
$ cmakeless vendor                # download and hash-verify each one, record it in cmakeless.mirror.json
$ cmakeless build --offline       # resolve from the vendored copies, no network at all
```

## Query the platform before you link

`project.cmake_globals()` runs a throwaway CMake configure immediately and hands back every variable CMake defined, so you can branch before anything is emitted:

```python
cmake = project.cmake_globals()

if hasattr(cmake, "WIN32"):
    app.depends("dirent")   # a POSIX-dirent shim, only needed on Windows
```

Remember: `hasattr(cmake, name)` mirrors CMake's `if(DEFINED name)`. `WIN32`/`APPLE`/`UNIX`/`ANDROID` are only ever *set*, never defined-and-false, so this is exactly the right check.

## Run a sanitized test suite

```console
$ cmakeless test --sanitize=address
```

No changes to `cmakelessfile.py` required: the sanitizer preset is applied on top of your existing `add_test(...)` targets, in its own build tree.

## Add a code-generation step

```python
gen = project.add_command(
    output=["generated/version.cpp"],
    command=["python", "tools/gen_version.py", "--out", "generated/version.cpp"],
    depends=["tools/gen_version.py"],
)
app.add_sources(gen)   # wires the dependency edge; CMakeless validates it is actually consumed
```

Commands are argument lists, never shell strings: portable across cmd and POSIX by construction, and immune to injection.

## Declare a project-wide option

```python
from cmakeless import When

gui = project.option("MYLIB_BUILD_GUI", default=True, help="Build the Qt front-end")
app.define("HAS_GUI", when=When.option(gui))
```

```console
$ cmakeless options
[cmakeless] MYLIB_BUILD_GUI (bool, default=True): Build the Qt front-end
```

## Ship Python bindings

```python
bindings = project.add_python_module("mymath", sources=["src/bindings.cpp"])  # pybind11 by default
bindings.link(engine)
```

```console
$ cmakeless build
$ python -c "import mymath; print(mymath.__doc__)"
```

The built module lands in your current environment automatically; `import` works the moment the build finishes.

## Install and package a release

```python
project.install(engine, headers=True)
project.install(app)
project.package(formats=["zip", "deb"])
```

```console
$ cmakeless install --prefix dist
$ cmakeless package
```

## Check what a new machine is missing

```console
$ cmakeless doctor
```

No `cmakelessfile.py` required. Reports CMake's version, the generator CMakeless would auto-select, `ccache`/`sccache`/`vcpkg`/`conan` on `PATH`, and network reachability, in one command.
