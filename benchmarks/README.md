# CMakeless Benchmarks

Reproducible harnesses for the two places CMakeless applies parallelism, per
[ARCHITECTURE](../ARCHITECTURE.md#free-threaded-python-parallelism-where-it-pays):
**dependency resolution** and **multi-preset configuration**. Both are safe to
parallelize because the model layer is immutable, so threads share it without
locks or copies.

## Running

```console
$ python benchmarks/bench_resolution.py     # parallel vs serial resolution
$ python benchmarks/bench_presets.py        # parallel vs serial configure
```

Run each under both a standard interpreter and a free-threaded one to compare:

```console
$ python3.13  benchmarks/bench_resolution.py
$ python3.14t benchmarks/bench_resolution.py   # free-threaded build
```

Each script prints the interpreter version, whether the GIL is enabled
(`sys._is_gil_enabled()`), the serial and parallel wall-clock times, and the
speedup.

## What each measures

- **`bench_resolution.py`** times resolving N packages. Resolution is
  I/O-bound (fetch + hash), so the one-thread-per-dependency pool overlaps the
  waits. The GIL is released across I/O, so the win appears on standard builds
  too; a free-threaded interpreter additionally overlaps the CPU-bound hashing.
  The per-package latency is a fixed, deterministic stand-in for a real fetch,
  so the number is reproducible.
- **`bench_presets.py`** times configuring N presets, each into its own build
  tree, over one shared frozen model. With CMake on `PATH` it runs real
  configures; without it, it prints a clearly labelled _simulated_ run so the
  harness works anywhere. Build trees are reset before each phase so serial and
  parallel do identical cold work.

Published numbers, with methodology and the interpreter/OS they were taken on,
live in [docs/benchmarks](../docs/benchmarks.md).
