# Parallelism Benchmarks

CMakeless applies parallelism in exactly two places, both made safe by the
immutable model layer (frozen dataclasses shared across threads without locks):
**dependency resolution** and **multi-preset configuration**. This page
publishes measured numbers and the method behind them. The harnesses are in
[benchmarks](../benchmarks/); anyone can reproduce or extend the table.

## Method

- `benchmarks/bench_resolution.py` times resolving 16 packages with a fixed
  0.05s simulated per-package I/O latency, serial versus a thread-per-package
  pool.
- `benchmarks/bench_presets.py` times configuring 6 presets, each into its own
  build tree, over one shared frozen model, serial versus concurrent. Build
  trees are reset before each phase so both do the full cold work.
- Each run reports the interpreter, `sys._is_gil_enabled()`, wall-clock times,
  and speedup. Resolution numbers are deterministic; configure numbers depend
  on the CMake version, generator, and machine, so the absolute times matter
  less than the serial-to-parallel ratio.

## Results

The Windows/CPython 3.13 row was last refreshed by a real local run on
2026-07-09, against CMake with the Ninja generator (Clang as the compiler).
Linux, macOS, and the free-threaded (`3.14t`) rows are sourced from
the [`benchmarks.yml`](https://github.com/bbalouki/cmakeless/blob/main/.github/workflows/benchmarks.yml) GitHub Actions
workflow (`workflow_dispatch`, run manually): triggering it runs the matrix
and opens a pull request with any `_to fill_` cells it can resolve, ready to
review and merge. They are left as `_to fill_` here because no run has been
recorded yet; the standard-build rows already show that most of the win is
I/O overlap the GIL does not block.

| Benchmark                   | OS      | Interpreter   | GIL | Serial    | Parallel  | Speedup   |
| --------------------------- | ------- | ------------- | --- | --------- | --------- | --------- |
| Resolution (16 pkgs)       | Windows | CPython 3.13  | on  | 0.806s    | 0.056s    | 14.37x    |
| Resolution (16 pkgs)       | Linux   | CPython 3.13  | on  | 0.802s | 0.053s | 15.00x |
| Resolution (16 pkgs)       | macOS   | CPython 3.13  | on  | 2.114s | 0.107s | 19.83x |
| Resolution (16 pkgs)       | any     | CPython 3.14t | off | 0.802s | 0.057s | 14.04x |
| Multi-preset configure (6) | Windows | CPython 3.13  | on  | 12.999s   | 4.149s    | 3.13x     |
| Multi-preset configure (6) | Linux   | CPython 3.13  | on  | 1.761s | 0.360s | 4.89x |
| Multi-preset configure (6) | macOS   | CPython 3.13  | on  | 4.506s | 0.936s | 4.81x |
| Multi-preset configure (6) | any     | CPython 3.14t | off | 2.120s | 0.358s | 5.92x |

## Reading the numbers

- **Resolution** is dominated by I/O the GIL releases, so even a standard build
  overlaps the fetches and reaches a large speedup bounded by the pool size.
- **Multi-preset configure** spends its time in the CMake subprocess, again I/O
  the GIL releases; the ~3x here is bounded by disk and the CMake process
  itself rather than the interpreter.
- A free-threaded interpreter is expected to add the CPU-bound share (hashing
  during resolution, Python-side emission), not to change the shape: parallel
  stays well below serial in both cases. Publishing both interpreters keeps the
  claim honest rather than assumed.
