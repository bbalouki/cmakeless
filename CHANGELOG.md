# Changelog

All notable changes to CMakeless are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Walking skeleton through all four layers (API, model, emitter, driver).
- `Project` and `Executable` public API; `project.build()` freezes, validates,
  emits `CMakeLists.txt`, and drives CMake configure + build.
- Freeze-time validation: missing source files are reported as
  `ConfigurationError` before CMake ever runs.
- `cmakeless build` CLI and `python -m cmakeless`; `python build.py` works as
  a first-class entry point.
- Exception hierarchy: `CmakelessError` with `ConfigurationError`,
  `DependencyError`, `ToolchainError`, and `CMakeError`.
