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

Taken on Windows 11, CMake 3.x with the Ninja generator. The free-threaded
rows are left for CI to fill on a `3.14t` interpreter; the standard-build rows
already show that most of the win is I/O overlap the GIL does not block.

| Benchmark                  | Interpreter   | GIL | Serial    | Parallel  | Speedup   |
| -------------------------- | ------------- | --- | --------- | --------- | --------- |
| Resolution (16 pkgs)       | CPython 3.13  | on  | 0.807s    | 0.064s    | 12.53x    |
| Resolution (16 pkgs)       | CPython 3.14t | off | _to fill_ | _to fill_ | _to fill_ |
| Multi-preset configure (6) | CPython 3.13  | on  | 15.645s   | 5.439s    | 2.88x     |
| Multi-preset configure (6) | CPython 3.14t | off | _to fill_ | _to fill_ | _to fill_ |

## Reading the numbers

- **Resolution** is dominated by I/O the GIL releases, so even a standard build
  overlaps the fetches and reaches a large speedup bounded by the pool size.
- **Multi-preset configure** spends its time in the CMake subprocess, again I/O
  the GIL releases; the ~2.9x here is bounded by disk and the CMake process
  itself rather than the interpreter.
- A free-threaded interpreter is expected to add the CPU-bound share (hashing
  during resolution, Python-side emission), not to change the shape: parallel
  stays well below serial in both cases. Publishing both interpreters keeps the
  claim honest rather than assumed.
