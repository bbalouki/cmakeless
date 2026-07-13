## Summary

<!-- What does this PR do, and why? Link the issue it addresses. -->

Closes #

## Checklist

- [ ] An issue exists for this change (or this is a typo/doc fix too small to need one, see CONTRIBUTING.md's PR flow).
- [ ] Tests added or updated under `tests/unittests/`, mirroring the `src/` layout. Emitter changes include golden-file tests with deterministic inputs.
- [ ] Every new/changed public module, class, function, and method has a docstring.
- [ ] `CHANGELOG.md` updated under `[Unreleased]` for any public API change (new/changed `cmakelessfile.py` surface, CLI, or generated-file format).
- [ ] Docs updated (`docs/*.md`) if this changes public behavior.
- [ ] `ruff check .` and `ruff format --check .` pass locally.
- [ ] `mypy src` passes locally (strict mode).
- [ ] CI is green on Windows, Linux, and macOS, the build tool for a cross-platform language doesn't get to have a favorite platform.

## Notes for reviewers

<!-- Anything a reviewer should pay special attention to: design tradeoffs, things you're unsure about, etc. -->
