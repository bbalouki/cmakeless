"""Frozen settings shared by every compiled target, test, and project.

Each compiled target model carries one TargetPropertiesModel instead of a
dozen loose fields, so a new per-target setting is one field here rather than
four identical fields across the target models.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path

# The C standards CMake's c_std_NN compile feature knows about.
SUPPORTED_C_STANDARDS: frozenset[int] = frozenset({90, 99, 11, 17, 23})

# Symbol visibility presets for CXX_VISIBILITY_PRESET.
VISIBILITY_PRESETS: frozenset[str] = frozenset({"default", "hidden"})

# MSVC runtime library flavours for MSVC_RUNTIME_LIBRARY.
MSVC_RUNTIMES: frozenset[str] = frozenset({"static", "dynamic"})

# The x86-64 microarchitecture levels Cpu.x86_64(level=...) accepts.
X86_64_LEVELS: frozenset[str] = frozenset({"v1", "v2", "v3", "v4"})

# The ARM floating-point ABIs Cpu.arm(float_abi=...) accepts.
ARM_FLOAT_ABIS: frozenset[str] = frozenset({"soft", "softfp", "hard"})


class CpuFamily(enum.Enum):
    """Which instruction-set family a CpuModel targets.

    Attributes:
        X86_64: 64-bit x86, targeted by microarchitecture level.
        ARM: 32-bit or 64-bit ARM, targeted by core name.
        NATIVE: Whatever the build machine is; never portable.
    """

    X86_64 = "x86_64"
    ARM = "arm"
    NATIVE = "native"


@dataclass(frozen=True, slots=True)
class CpuModel:
    """A validated CPU target, translated to per-compiler flags by the emitter.

    Attributes:
        family: The instruction-set family.
        level: The x86-64 microarchitecture level ("v1" to "v4"), or None.
        core: The ARM core name passed as -mcpu (for example "cortex-m7").
        fpu: The ARM FPU passed as -mfpu, or None for the core default.
        float_abi: The ARM float ABI passed as -mfloat-abi, or None.
    """

    family: CpuFamily
    level: str | None = None
    core: str | None = None
    fpu: str | None = None
    float_abi: str | None = None


@dataclass(frozen=True, slots=True)
class FlagSetModel:
    """Compiler and linker flags split by command-line syntax.

    MSVC-syntax flags go to cl and clang-cl; GNU-syntax flags go to GCC,
    Clang, and every compiler that mimics their driver. Link flags are
    linker flags (without -Wl,), split by linker family because the
    compiler frontend does not decide which linker runs.

    Attributes:
        msvc_compile: Flags for an MSVC-syntax compiler.
        gnu_compile: Flags for a GNU-syntax compiler.
        msvc_link: Flags for the MSVC linker (link.exe, lld-link).
        gnu_link: Flags for an ELF linker (GNU ld, gold, lld, mold).
        apple_link: Flags for Apple's ld64.
        defines: Preprocessor definitions as NAME or NAME=VALUE.
        release_only: True when the flags apply to optimized configs only.
    """

    msvc_compile: tuple[str, ...] = ()
    gnu_compile: tuple[str, ...] = ()
    msvc_link: tuple[str, ...] = ()
    gnu_link: tuple[str, ...] = ()
    apple_link: tuple[str, ...] = ()
    defines: tuple[str, ...] = ()
    release_only: bool = False


@dataclass(frozen=True, slots=True)
class ProfileModel:
    """A named, composable bundle of flags and target settings.

    Attributes:
        names: The profile names composed into this one, in order.
        flag_sets: Every flag set the profile contributes.
        x86_only: Flag sets valid only when targeting x86 or x86-64.
        linux_only: Flag sets valid only when targeting Linux.
        warnings_as_errors: True to turn on COMPILE_WARNING_AS_ERROR.
        position_independent: True to build position-independent
            executables (PIE), with CMake's own link-time check.
        ipo_release: True to enable interprocedural optimization for
            optimized configurations.
        map_file: True to write a linker map file next to each binary.
    """

    names: tuple[str, ...]
    flag_sets: tuple[FlagSetModel, ...] = ()
    x86_only: tuple[FlagSetModel, ...] = ()
    linux_only: tuple[FlagSetModel, ...] = ()
    warnings_as_errors: bool = False
    position_independent: bool = False
    ipo_release: bool = False
    map_file: bool = False


@dataclass(frozen=True, slots=True)
class QtModel:
    """Qt integration for one target.

    Attributes:
        major: The Qt major version (5 or 6).
        components: Qt modules to find and link, for example "Widgets".
        resources: Project-root-relative .qrc files compiled into the
            target.
    """

    major: int
    components: tuple[str, ...]
    resources: tuple[Path, ...] = ()


@dataclass(frozen=True, slots=True)
class ExtensionUseModel:
    """One plugin extension applied to a target.

    Attributes:
        name: The extension's entry-point name.
        version: The plugin distribution version, for the output fence.
        snippet: The CMake the extension produced for this target.
    """

    name: str
    version: str
    snippet: str


@dataclass(frozen=True, slots=True)
class TargetPropertiesModel:
    """Per-target settings beyond sources, links, and compile flags.

    Attributes:
        c_std: This target's C standard override, or None for the project's.
        output_name: The built file's base name, or None for the target name.
        version: A shared library's full ABI version (VERSION property).
        soversion: A shared library's ABI compatibility version.
        visibility: "hidden" or "default" symbol visibility, or None to
            leave the compiler default.
        gui: True for a windowed application (WIN32_EXECUTABLE and
            MACOSX_BUNDLE) rather than a console one.
        msvc_runtime: "static" or "dynamic" MSVC runtime, or None.
        linker_script: Project-root-relative linker script, or None.
        map_file: True to write a linker map file next to the binary.
        post_build: Argument vectors run after the target links.
        cuda_architectures: CUDA_ARCHITECTURES values, for example "86".
        cpu: The CPU this target is optimized for, or None.
        profile: This target's own profile, overriding the project's.
        warnings: This target's warning preset, overriding the project's.
        warnings_as_errors: This target's COMPILE_WARNING_AS_ERROR
            setting, or None to inherit the project's.
        qt: Qt integration, or None.
        extensions: Plugin extensions applied to this target.
        declared_line: The cmakelessfile.py line that declared the target.
    """

    c_std: int | None = None
    output_name: str | None = None
    version: str | None = None
    soversion: str | None = None
    visibility: str | None = None
    gui: bool = False
    msvc_runtime: str | None = None
    linker_script: Path | None = None
    map_file: bool = False
    post_build: tuple[tuple[str, ...], ...] = ()
    cuda_architectures: tuple[str, ...] = ()
    cpu: CpuModel | None = None
    profile: ProfileModel | None = None
    warnings: str | None = None
    warnings_as_errors: bool | None = None
    qt: QtModel | None = None
    extensions: tuple[ExtensionUseModel, ...] = ()
    declared_line: int | None = None


@dataclass(frozen=True, slots=True)
class TestPropertiesModel:
    """CTest properties for every case a test target registers.

    Attributes:
        timeout: Seconds before CTest kills a case, or None for no limit.
        labels: Labels for 'ctest -L' and 'cmakeless test --label'.
        env: Environment variables as sorted (name, value) pairs.
        working_directory: Project-root-relative directory to run in.
        serial: True to never run this test alongside others (RUN_SERIAL).
        will_fail: True when a non-zero exit is the expected verdict.
        fixtures_setup: Fixture names this test sets up.
        fixtures_cleanup: Fixture names this test tears down.
        fixtures_required: Fixture names that must be set up first.
    """

    timeout: int | None = None
    labels: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = ()
    working_directory: Path | None = None
    serial: bool = False
    will_fail: bool = False
    fixtures_setup: tuple[str, ...] = ()
    fixtures_cleanup: tuple[str, ...] = ()
    fixtures_required: tuple[str, ...] = ()

    # Tell pytest this model is not a test case, despite the Test* name.
    __test__ = False


@dataclass(frozen=True, slots=True)
class InstallFilesModel:
    """Plain files or directories shipped by install, outside any target.

    Attributes:
        paths: Project-root-relative files or directories to install.
        destination: Install-prefix-relative destination directory.
        component: The CPack component, or None for the default one.
        directory: True when every path is a directory.
        contents_only: True to install a directory's contents rather than
            the directory itself (the path was written with a trailing '/').
    """

    paths: tuple[Path, ...]
    destination: str
    component: str | None = None
    directory: bool = False
    contents_only: bool = False


@dataclass(frozen=True, slots=True)
class PackageMetadataModel:
    """CPack metadata describing who ships a package and what it needs.

    Attributes:
        vendor: The organization shipping the package.
        contact: Maintainer contact, required by Debian packages.
        description: One-line package summary.
        homepage: Project homepage URL.
        license_file: Project-root-relative license file.
        deb_depends: Debian package dependencies, for example "libc6".
        rpm_requires: RPM package requirements.
    """

    vendor: str | None = None
    contact: str | None = None
    description: str | None = None
    homepage: str | None = None
    license_file: Path | None = None
    deb_depends: tuple[str, ...] = ()
    rpm_requires: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SigningModel:
    """Post-install code signing, credentials read only from the environment.

    Attributes:
        windows_cert_env: Environment variable holding the signtool
            certificate path, or None to skip Windows signing.
        windows_timestamp_url: The RFC 3161 timestamp server for signtool.
        macos_identity_env: Environment variable holding the codesign
            identity, or None to skip macOS signing.
    """

    windows_cert_env: str | None = None
    windows_timestamp_url: str | None = None
    macos_identity_env: str | None = None


@dataclass(frozen=True, slots=True)
class CacheModel:
    """A compiler cache and the environment its backend needs.

    Attributes:
        tool: "ccache" or "sccache".
        env: Backend environment variables as sorted (name, value) pairs.
    """

    tool: str
    env: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class ExportModel:
    """Which package metadata formats install() exports.

    Attributes:
        cmake: True for the classic Config.cmake files.
        cps: True for a Common Package Specification (.cps) file.
        pkg_config: True for a pkg-config (.pc) file.
    """

    cmake: bool = True
    cps: bool = False
    pkg_config: bool = False


@dataclass(frozen=True, slots=True)
class InstallOptionsModel:
    """Extra install behavior for one installed target.

    Attributes:
        component: The CPack component, or None for the default one.
        rpath: "relative" to find sibling libraries from the install tree,
            or None to leave CMake's default.
        destination: An explicit install destination, or None for the
            GNUInstallDirs default.
        runtime_dependencies: True to also install the shared libraries
            the target needs at runtime.
    """

    component: str | None = None
    rpath: str | None = None
    destination: str | None = None
    runtime_dependencies: bool = False
