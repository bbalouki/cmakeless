"""Named, composable bundles of expert defaults for one industry's builds.

A profile is plain data: every flag it adds is visible in the generated
CMakeLists.txt and in 'cmakeless explain'. Profiles compose with `|`, and a
target's own profile replaces the project's for that target alone.
"""

from __future__ import annotations

from cmakeless.model.properties import FlagSetModel, ProfileModel

# The OpenSSF compiler-hardening baseline, split by command-line syntax.
_HARDENED = FlagSetModel(
    gnu_compile=("-fstack-protector-strong",),
    msvc_compile=("/sdl", "/guard:cf"),
    msvc_link=("/guard:cf",),
    defines=("_GLIBCXX_ASSERTIONS",),
)
# _FORTIFY_SOURCE needs optimization, and some distributions predefine a
# lower level, so it is reset first and applied to optimized configs only.
_FORTIFY = FlagSetModel(gnu_compile=("-U_FORTIFY_SOURCE", "-D_FORTIFY_SOURCE=3"), release_only=True)
_HARDENED_LINUX = FlagSetModel(
    gnu_compile=("-fstack-clash-protection",),
    gnu_link=("-z,relro", "-z,now", "-z,noexecstack"),
)
_HARDENED_X86 = FlagSetModel(gnu_compile=("-fcf-protection=full",), msvc_link=("/CETCOMPAT",))

_REPRODUCIBLE = FlagSetModel(
    gnu_compile=(
        "-ffile-prefix-map=${CMAKE_SOURCE_DIR}=.",
        "-ffile-prefix-map=${CMAKE_BINARY_DIR}=build",
        "-Wdate-time",
    ),
    msvc_compile=("/Brepro",),
    msvc_link=("/Brepro",),
)

_LOW_LATENCY = FlagSetModel(
    gnu_compile=("-O3", "-fno-omit-frame-pointer"),
    msvc_compile=("/O2", "/Ob3", "/Oy-"),
    release_only=True,
)
_LOW_LATENCY_LINUX = FlagSetModel(gnu_compile=("-fno-plt",))

_EMBEDDED = FlagSetModel(
    gnu_compile=("-ffunction-sections", "-fdata-sections"),
    msvc_compile=("/Gy", "/Gw"),
    gnu_link=("--gc-sections",),
    apple_link=("-dead_strip",),
    msvc_link=("/OPT:REF", "/OPT:ICF"),
)
_EMBEDDED_SIZE = FlagSetModel(gnu_compile=("-Os",), msvc_compile=("/O1",), release_only=True)
_NO_EXCEPTIONS = FlagSetModel(gnu_compile=("-fno-exceptions",), msvc_compile=("/EHs-c-",))
_NO_RTTI = FlagSetModel(gnu_compile=("-fno-rtti",), msvc_compile=("/GR-",))

# Optimizations that turn undefined behavior into silently different code,
# disabled the way safety-critical and kernel code bases conventionally do.
_SAFETY = FlagSetModel(gnu_compile=("-fno-strict-aliasing", "-fno-delete-null-pointer-checks"))


class Profile:
    """A composable profile, assigned to Project(profile=...) or target.profile."""

    def __init__(self, model: ProfileModel) -> None:
        """Wrap an already-built profile description.

        Args:
            model: The frozen description the factories produce.
        """
        self._model = model

    @classmethod
    def hardened(cls) -> Profile:
        """Runtime exploit mitigations: stack protection, CFI, full RELRO, PIE.

        Returns:
            The profile.
        """
        return cls(
            ProfileModel(
                names=("hardened",),
                flag_sets=(_HARDENED, _FORTIFY),
                linux_only=(_HARDENED_LINUX,),
                x86_only=(_HARDENED_X86,),
                position_independent=True,
            )
        )

    @classmethod
    def reproducible(cls) -> Profile:
        """Bit-identical outputs: no absolute paths or timestamps in binaries.

        Returns:
            The profile.
        """
        return cls(ProfileModel(names=("reproducible",), flag_sets=(_REPRODUCIBLE,)))

    @classmethod
    def low_latency(cls) -> Profile:
        """Aggressive optimization with frame pointers kept for profiling.

        Returns:
            The profile.
        """
        return cls(
            ProfileModel(
                names=("low_latency",),
                flag_sets=(_LOW_LATENCY,),
                linux_only=(_LOW_LATENCY_LINUX,),
                ipo_release=True,
            )
        )

    @classmethod
    def embedded(cls, *, exceptions: bool = False, rtti: bool = False) -> Profile:
        """Size-first code with dead sections stripped and a linker map file.

        Args:
            exceptions: True to keep C++ exceptions enabled.
            rtti: True to keep run-time type information enabled.

        Returns:
            The profile.
        """
        flag_sets = [_EMBEDDED, _EMBEDDED_SIZE]
        if not exceptions:
            flag_sets.append(_NO_EXCEPTIONS)
        if not rtti:
            flag_sets.append(_NO_RTTI)
        return cls(ProfileModel(names=("embedded",), flag_sets=tuple(flag_sets), map_file=True))

    @classmethod
    def safety_critical(cls) -> Profile:
        """Reproducible, warning-free builds without UB-exploiting optimizations.

        This is configuration-management hygiene, not a certification: a
        qualified toolchain and process are still required for DO-178C or
        ISO 26262.

        Returns:
            The profile.
        """
        safety = ProfileModel(
            names=("safety_critical",), flag_sets=(_SAFETY,), warnings_as_errors=True
        )
        return cls.reproducible() | cls(safety)

    def __or__(self, other: Profile) -> Profile:
        """Compose two profiles; flags accumulate and switches combine.

        Args:
            other: The profile to add.

        Returns:
            A new profile carrying both.
        """
        left, right = self._model, other._model
        names = tuple(dict.fromkeys((*left.names, *right.names)))
        return Profile(
            ProfileModel(
                names=names,
                flag_sets=(*left.flag_sets, *right.flag_sets),
                x86_only=(*left.x86_only, *right.x86_only),
                linux_only=(*left.linux_only, *right.linux_only),
                warnings_as_errors=left.warnings_as_errors or right.warnings_as_errors,
                position_independent=left.position_independent or right.position_independent,
                ipo_release=left.ipo_release or right.ipo_release,
                map_file=left.map_file or right.map_file,
            )
        )

    @property
    def names(self) -> tuple[str, ...]:
        """The profile names composed into this one."""
        return self._model.names

    def __repr__(self) -> str:
        """Developer-facing representation.

        Returns:
            The composed profile names.
        """
        return f"Profile({' | '.join(self._model.names)})"

    def _freeze(self) -> ProfileModel:
        """Hand the profile description to the model.

        Returns:
            The frozen profile.
        """
        return self._model
