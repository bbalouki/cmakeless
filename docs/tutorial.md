# Ten-Minute Tutorial

A straight line from an empty directory to a tested, linked, dependency-using project. Every step is copy-pasteable; every command runs on Windows, Linux, and macOS unchanged.

## 1. Install and scaffold

```console
$ pip install cmakeless
$ mkdir tutorial && cd tutorial
$ cmakeless init
```

`cmakeless init` writes a minimal `cmakelessfile.py`, a `src/main.cpp`, and a `.gitignore`. Open `cmakelessfile.py`: it is five lines, and it is the whole build.

```python
# cmakelessfile.py
from cmakeless import Project

project = Project("tutorial", version="1.0.0", cpp_std=20)
project.add_executable("tutorial", sources=["src/main.cpp"])
project.build()
```

Build it:

```console
$ cmakeless build
```

That command generated a `CMakeLists.txt`, configured it, and compiled a real binary, all from the five lines above. Open the generated file if you are curious; it is meant to be read.

## 2. Add a library

Real projects split code into a library and an entry point. Add one:

```console
$ mkdir -p src/engine include
```

```cpp
// include/engine.hpp
#pragma once
auto greeting() -> const char*;
```

```cpp
// src/engine/engine.cpp
#include "engine.hpp"
auto greeting() -> const char* { return "Hello from the engine"; }
```

Update `cmakelessfile.py`:

```python
from cmakeless import Project

project = Project("tutorial", version="1.0.0", cpp_std=20)

engine = project.add_library(
    "engine",
    sources=["src/engine/*.cpp"],
    public_headers="include/",
)

app = project.add_executable("tutorial", sources=["src/main.cpp"])
app.link(engine)

project.build()
```

`app.link(engine)` links privately by default, the right call for an executable. No `PUBLIC`/`PRIVATE`/`INTERFACE` to memorize.

Update `src/main.cpp` to use it:

```cpp
// src/main.cpp
#include "engine.hpp"
#include <iostream>

auto main() -> int {
    std::cout << greeting() << "\n";
    return 0;
}
```

```console
$ cmakeless build
```

## 3. Add a dependency

Depend on a real third-party library in one line:

```python
app.depends("fmt/10.2.1")
```

`cmakeless build` resolves it (`find_package` first, then `FetchContent` if not found on the system), pins the exact version in `cmakeless.lock`, and links the correct target (`fmt::fmt`, not `fmt`) automatically. Nothing else changes.

## 4. Test it

```python
tests = project.add_test("engine_tests", sources=["tests/*.cpp"])  # GoogleTest by default
tests.link(engine)
```

```cpp
// tests/engine_tests.cpp
#include "engine.hpp"
#include <gtest/gtest.h>

TEST(Engine, GreetingIsNotEmpty) {
    EXPECT_STRNE(greeting(), "");
}
```

```console
$ cmakeless test
```

CMakeless fetched GoogleTest, registered the test case with CTest, and ran it. Prefer Catch2 or doctest? Pass `framework="catch2"` or `framework="doctest"` instead.

## 5. What you have

A library, an executable, a real external dependency, and a test suite, described in about fifteen lines of plain Python, with a `CMakeLists.txt` you can commit, open in any IDE, or delete CMakeless entirely and keep building. That is the whole model: describe the build in Python, let CMakeless generate and drive real CMake.

## Where next

- [Cookbook](cookbook.md): task-oriented recipes for the things you'll want next (cross-compiling, presets, custom build steps, a private dependency mirror).
- [Features](FEATURES.md): the complete feature catalog, with before/after CMake comparisons.
- [Migration guide](migration.md): bringing CMakeless into a project that already has a hand-written `CMakeLists.txt`.
