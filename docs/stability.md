# The Stability Promise

CMakeless 1.0 is a social contract before it is a version number. This page
states exactly what that contract covers, what it does not, and how a change
that breaks it is supposed to reach you.

## What counts as the public API

Exactly three things:

1. **Every name re-exported from `cmakeless/__init__.py`**, and the signature of
   every public method on those classes. `cmakeless.__all__` is the
   authoritative list.
2. **The generated file formats**: `CMakeLists.txt`, `CMakePresets.json`,
   generated toolchain files, `cmakeless.lock`, `vcpkg.json`, `conanfile.txt`,
   and the CycloneDX/SPDX bills of materials.
3. **The command line**: verb names, flag names and their meanings, and the exit
   codes (`0` success, `1` a CMakeless error, `2` a usage error).

Anything else is implementation detail, including `cmakeless.model`,
`cmakeless.emitter`, `cmakeless.driver`, and `cmakeless.deps`, every name
starting with an underscore, and the exact wording of error messages. Those
change in any release. Import from `cmakeless` and nowhere else.

## What the version number promises

Semantic Versioning 2.0.0, with teeth:

| Change                                                       | Version bump |
| ------------------------------------------------------------ | ------------ |
| A backward-incompatible change to anything in the list above | major        |
| New API, new verb, new flag, new emitted construct           | minor        |
| Bug fix that does not change a documented behavior           | patch        |

Generated output is covered, so a change that alters the CMake we emit for an
unchanged build description is a real change with a real version bump behind it,
not a silent one. The exception is the self-describing header comment, which
carries the tool version and therefore differs on every release.

## How things get removed

Nothing in the public API simply disappears. Removing anything takes at least
two releases:

1. In some release, it starts emitting a `DeprecationWarning` that names its
   replacement and the version that will remove it. It keeps working, unchanged.
2. No earlier than the next minor release, and only in a major release if the
   removal is breaking, it goes away.

There is one spelling for this, so every deprecation reads the same:

```python
from cmakeless import deprecated


@deprecated(replacement="target.include_dirs()", removed_in="2.0.0")
def private_headers(self, *dirs: str) -> None:
    """The old spelling, still working, now warning."""
```

To see them in your own build, run Python with warnings enabled:

```console
$ python -W error::DeprecationWarning cmakelessfile.py
```

## How the promise is enforced

Not by good intentions. Three tests fail CI when the contract moves:

- `tests/unittests/test_public_api.py` compares the entire public surface,
  including inherited methods and full signatures, against a golden snapshot.
  Any addition, removal, or signature change fails until the snapshot is
  regenerated deliberately, which is the moment a CHANGELOG entry gets written.
- `tests/unittests/emitter/golden/` compares generated CMake byte for byte.
- `tests/integration/` builds every project under `examples/` from its real
  `cmakelessfile.py`, so a change that breaks documented usage fails before it
  reaches anyone.

## What this does not promise

- **CMake's own behavior.** We generate CMake; CMake and your compiler do the
  rest. A CMake release changing how it treats what we emit is outside anything
  we can version.
- **Anything marked experimental in CMake itself.** C++20 module interfaces are
  supported because `FILE_SET CXX_MODULES` is stable; installing and exporting
  them is not, so CMakeless refuses it rather than emitting output that breaks
  on the next CMake release.
- **Error message wording.** Messages are meant to be read by people and improved
  constantly. Match on exception types, never on text.

## If we break it anyway

Open an issue. A regression against this page is a bug with priority over
features, and the fix ships in a patch release.
