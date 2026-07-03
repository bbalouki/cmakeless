# CMakeless — Project Context

## Overview

CMakeless is a pure-Python frontend for CMake: users write a `cmakelessfile.py` describing a C++ project through a small, typed `Project` API (`add_executable`, `add_library`, `add_test`, `add_python_module`, `depends`, presets, install/package), and CMakeless generates a clean, standalone `CMakeLists.txt` and drives real CMake to configure and build it. It is pre-1.0 (alpha), not yet published to PyPI, so breaking changes are acceptable without a deprecation cycle.

## Repository Layout

- `src/cmakeless/`
  - `api/` — the public builder classes (`Project`, `Executable`, `Library`, `Test`, `PythonModule`, `Preset`, `Toolchain`, `Dependency`) that users call from `cmakelessfile.py`.
  - `model/` — the frozen, validated intermediate representation the API builds and the emitter reads.
  - `emitter/` — turns the model into `CMakeLists.txt` text; output is deterministic and byte-identical for the same model.
  - `driver/` — invokes the real `cmake`/`ctest`/`cpack` binaries and translates their failures into structured exceptions.
  - `deps/` — dependency resolution: `find_package`-then-`FetchContent` fallback, vcpkg, Conan, and the `cmakeless.lock` lockfile.
  - `cli.py` — the `cmakeless` console script and its verbs (build/configure/test/install/package/clean/lock/init).
  - `_constants.py` — shared literals (e.g. the default build-description filename) with no internal dependencies, safe for any module to import.
- `tests/unittests/` mirrors `src/cmakeless/` package-for-package; golden `.cmake` fixtures live under `tests/unittests/emitter/golden/`.
- `examples/` is a numbered, escalating series (`01_hello` through `08_capstone`), each a real `cmakelessfile.py` that regenerates its own gitignored `CMakeLists.txt`/`build/`.

## Entry-Point Convention

- `cmakelessfile.py` is the default build-description filename (the `Dockerfile`/`Jenkinsfile`-style convention: it names the tool, not the library, so it can't shadow the installed `cmakeless` package on `sys.path`). `cmakeless.py` was deliberately rejected for exactly that collision risk — see `ARCHITECTURE.md`.
- Two equivalent ways to run it: `cmakeless build` (or `configure`/`test`/`install`/`package`/`clean`/`lock`) via the CLI, or `python cmakelessfile.py` directly — both execute the same script under `__main__`.
- `cmakeless init` scaffolds a new `cmakelessfile.py` + `src/main.cpp` + `.gitignore`.

## Dev Commands

From `.github/workflows/ci.yml`:

- `uv run pytest` — full test suite (set `CMAKELESS_NETWORK_TESTS=1` to unskip tests that fetch and compile a real dependency).
- `uv run ruff check .` / `uv run ruff format --check .` — lint and format check.
- `uv run mypy src` — strict type check.

## Further Reading

- [ARCHITECTURE.md](ARCHITECTURE.md) — layered design, entry points, error-handling philosophy.
- [FEATURES.md](FEATURES.md) — full before/after comparison against raw CMake.
- [ROADMAP.md](ROADMAP.md) — where the project is going.
- [CONTRIBUTING.md](CONTRIBUTING.md) — contribution philosophy and review priorities.

---

# General Best Practices

## Testing Philosophy

- Use real implementations; only mock external dependencies (LLM APIs, cloud services).
- Test public interface behavior, not implementation details — keeps tests resilient to refactoring.
- Tests must be fast, isolated, and have descriptive names; cover edge cases and error conditions.
- Location: `tests/unittests/` following source structure.
- Add integration `tests/integration/`  tests to ensure that the library works as expected when integrated into larger projects with thousands of components.

## Comments

- Explain the _why_, not the _what_. Well-named code is self-documenting.
- Write comments as complete sentences; block comments begin with `# ` (space after hash).

## Versioning & Breaking Changes

- Follow Semantic Versioning 2.0.0 (`MAJOR.MINOR.PATCH`).
- A breaking change is any backward-incompatible modification to the public API, including data schemas, CLI, and server communication formats.

---

# Python Best Practices



## General

- Use immutable constants (tuple, frozenset) over magic literals; name mappings `value_by_key`.
- Use f-strings for formatting; use `%`-templates for logging.
- Use list/set/dict comprehensions; iterate directly with `enumerate()`, `dict.items()`, `zip()`.
- Never use mutable default arguments; use `None` as sentinel.
- Use `is`/`is not` for singleton comparisons (`None`, `True`, `False`); use `==` for values.
- Annotate with types using abstract types from `collections.abc`; use `NewType` to prevent argument transposition.
- Use decorators to add common functionality to functions, use `@functools.wraps()` to preserve the original function's metadata.
- Use context managers (`with`), `@property` only when needed, and `@functools.wraps()` in decorators.
- Implement `__repr__()` for developer output, `__str__()` for user-facing output.


## Code Quality

- Do not declare unused variables, objects, or functions
- Use a formatted string whenever you want to inject a variable in a string, especially in logging
- Follow project style: type hints, docstrings, meaningful comments
- Every function, class, module or method should have a docstring and all parameters, attributes and return values at the library level should be documented. 
- All functions and methods must be less than 35 lines of code

## Libraries

- `collections.Counter`/`defaultdict` for counting/grouping; `heapq` for top-N; `itertools.chain.from_iterable()` for flattening.
- Use `attrs` or `dataclasses` for simple classes; `pydantic` or `cattrs` for serialization.
- Use `re.VERBOSE` and compile reused regexes; avoid regex for simple string checks (`in`, `startswith`).
- Use `functools.lru_cache` carefully; prefer `functools.cached_property` for methods.
- Avoid `pickle`; prefer JSON, Protocol Buffers, or msgpack.
- Be aware of potential issues with `multiprocessing`, especially concerning `fork`, consider alternatives like `threading` or `asyncio` for I/O-bound tasks.

## Testing

- Use pytest `assert` with informative expressions; `@pytest.mark.parametrize` to eliminate duplication.
- Use fixtures for setup/teardown; `mock.create_autospec(spec_set=True)` for mocks; `tmp_path` for temp files.
- Use deterministic inputs — never random values in unit tests.
- Focus on public API invariants, not implementation details.

## Error Handling

- Use bare `raise` to preserve stack traces; `raise NewException from original` to chain; `from None` to suppress.
- Always include a descriptive message when raising exceptions.
- Use `sys.exit()` for expected terminations; use `repr(e)` or the `traceback` module for exception strings.

---
