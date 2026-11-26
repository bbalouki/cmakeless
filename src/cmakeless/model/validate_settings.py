"""Freeze-time checks for per-target settings, tests, shipping, and supply chain.

Each check raises ConfigurationError with what went wrong, where, and what
to try next, before CMake ever runs.
"""

from __future__ import annotations

import re
from pathlib import Path

from cmakeless.errors import ConfigurationError
from cmakeless.model.nodes import (
    INSTRUMENTATIONS,
    SUPPLY_CHAIN_MODES,
    WARNING_PRESETS,
    CompiledModel,
    ExecutableModel,
    LibraryKind,
    LibraryModel,
    ProjectModel,
    WhenKind,
    WhenModel,
)
from cmakeless.model.properties import (
    MSVC_RUNTIMES,
    SUPPORTED_C_STANDARDS,
    VISIBILITY_PRESETS,
    TargetPropertiesModel,
    TestPropertiesModel,
)

# An output name becomes a file name, so it may not carry a path or a suffix
# the platform adds itself.
_OUTPUT_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.+-]*$")
_ABI_VERSION = re.compile(r"^[0-9]+(\.[0-9]+){0,3}$")
_CUDA_ARCHITECTURE = re.compile(r"^([0-9]+[a-z]?(-real|-virtual)?|native|all|all-major)$")
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_COMPONENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
_LIST_SEPARATOR = ";"
_RPATH_MODES = frozenset({"relative"})


def validate_settings(model: ProjectModel) -> None:
    """Run every settings, test, shipping, and supply-chain check.

    Args:
        model: The frozen project node.

    Raises:
        ConfigurationError: On the first defect found.
    """
    _check_c_std(model.c_std, where="Project(c_std=...)", model=model)
    if model.supply_chain not in SUPPLY_CHAIN_MODES:
        modes = ", ".join(repr(mode) for mode in sorted(SUPPLY_CHAIN_MODES))
        raise ConfigurationError(
            f"Unknown supply_chain {model.supply_chain!r} in {model.source_script}. "
            f"Pick one of: {modes}."
        )
    unknown = sorted(set(model.instrumentation) - INSTRUMENTATIONS)
    if unknown:
        raise ConfigurationError(f"Unknown instrumentation {', '.join(unknown)}.")
    for target in model.all_targets():
        _check_target_properties(target, model)
    for test in model.tests:
        _check_test_properties(test.name, test.test_properties, model)
    _check_install_options(model)
    _check_install_files(model)
    _check_package_metadata(model)
    _check_allow_system(model)
    _check_subproject_conditions(model)


def _check_c_std(value: int | None, *, where: str, model: ProjectModel) -> None:
    """Require a C standard CMake's c_std_NN feature knows.

    Args:
        value: The standard, or None for the compiler default.
        where: What set it, for the message.
        model: The owning project.

    Raises:
        ConfigurationError: On an unknown standard.
    """
    if value is not None and value not in SUPPORTED_C_STANDARDS:
        known = ", ".join(str(std) for std in sorted(SUPPORTED_C_STANDARDS))
        raise ConfigurationError(
            f"{where} = {value} in {model.source_script} is not a C standard CMake "
            f"knows. Use one of: {known}."
        )


def _check_target_properties(target: CompiledModel, model: ProjectModel) -> None:
    """Check one target's output, ABI, platform, and tooling settings.

    Args:
        target: The compiled target.
        model: The owning project.

    Raises:
        ConfigurationError: On the first invalid setting.
    """
    properties = target.properties
    where = f"target {target.name!r} in {model.source_script}"
    _check_c_std(properties.c_std, where=f"{target.name}.c_std", model=model)
    _check_choice(properties.warnings, WARNING_PRESETS, f"{target.name}.warnings", where)
    _check_choice(properties.visibility, VISIBILITY_PRESETS, f"{target.name}.visibility", where)
    _check_choice(properties.msvc_runtime, MSVC_RUNTIMES, f"{target.name}.msvc_runtime", where)
    if properties.output_name is not None and not _OUTPUT_NAME.match(properties.output_name):
        raise ConfigurationError(
            f"output_name {properties.output_name!r} on {where} must be a bare file "
            f"name without a path or extension; the platform adds lib, .so, or .dll itself."
        )
    if properties.gui and not isinstance(target, ExecutableModel):
        raise ConfigurationError(f"gui = True on {where} applies only to executables.")
    _check_abi_versions(target, where)
    _check_cuda_architectures(properties, where)
    _check_linker_script(properties, model, where)


def _check_choice(value: str | None, allowed: frozenset[str], what: str, where: str) -> None:
    """Require an optional setting to be one of a closed set.

    Args:
        value: The setting, or None for unset.
        allowed: The accepted values.
        what: The attribute name, for the message.
        where: The target and script, for the message.

    Raises:
        ConfigurationError: When the value is not allowed.
    """
    if value is not None and value not in allowed:
        choices = ", ".join(repr(choice) for choice in sorted(allowed))
        raise ConfigurationError(f"{what} = {value!r} on {where} must be one of: {choices}.")


def _check_abi_versions(target: CompiledModel, where: str) -> None:
    """Check VERSION and SOVERSION: well formed, and only on shared libraries.

    Args:
        target: The compiled target.
        where: The target and script, for the message.

    Raises:
        ConfigurationError: On a malformed version, or one on a target that
            has no shared-library ABI.
    """
    for label, value in (
        ("version", target.properties.version),
        ("soversion", target.properties.soversion),
    ):
        if value is None:
            continue
        shared = isinstance(target, LibraryModel) and target.kind in (
            LibraryKind.SHARED,
            LibraryKind.PLUGIN,
        )
        if not shared:
            raise ConfigurationError(
                f"{label}= on {where} applies only to shared libraries and plugins, "
                f'whose file names carry an ABI version. Use kind="shared" or drop it.'
            )
        if not _ABI_VERSION.match(value):
            raise ConfigurationError(
                f'{label}={value!r} on {where} must be dotted numbers, for example "2" or "2.3.1".'
            )


def _check_cuda_architectures(properties: TargetPropertiesModel, where: str) -> None:
    """Check CUDA architecture names against CMake's CUDA_ARCHITECTURES grammar.

    Args:
        properties: The target's properties.
        where: The target and script, for the message.

    Raises:
        ConfigurationError: On an architecture CMake would reject.
    """
    for architecture in properties.cuda_architectures:
        if not _CUDA_ARCHITECTURE.match(architecture):
            raise ConfigurationError(
                f"cuda_architectures entry {architecture!r} on {where} is not valid; use "
                f'numbers like "86", "90a", "80-real", or "native", "all", "all-major".'
            )


def _check_linker_script(
    properties: TargetPropertiesModel, model: ProjectModel, where: str
) -> None:
    """Require a linker script to be a real, project-relative file.

    Args:
        properties: The target's properties.
        model: The owning project.
        where: The target and script, for the message.

    Raises:
        ConfigurationError: When the script is absolute, escapes the root,
            or does not exist.
    """
    script = properties.linker_script
    if script is None:
        return
    _require_inside_root(script, what=f"linker_script on {where}")
    if not (model.root_dir / script).is_file():
        raise ConfigurationError(
            f"linker_script '{script.as_posix()}' on {where} does not exist "
            f"(looked for {model.root_dir / script}). Check the path."
        )


def _require_inside_root(path: Path, *, what: str) -> None:
    """Refuse an absolute path or one that climbs out of the project root.

    Args:
        path: The declared path.
        what: What it names, for the message.

    Raises:
        ConfigurationError: When the path is not a plain relative path.
    """
    if path.anchor or path.is_absolute() or ".." in path.parts:
        raise ConfigurationError(
            f"{what} '{path.as_posix()}' must be a relative path inside the project root."
        )


def _check_test_properties(name: str, properties: TestPropertiesModel, model: ProjectModel) -> None:
    """Check one test's CTest properties.

    Args:
        name: The test target name.
        properties: Its CTest properties.
        model: The owning project.

    Raises:
        ConfigurationError: On a non-positive timeout, a list value that
            would split in CTest, a bad variable name, or a missing directory.
    """
    where = f"test {name!r} in {model.source_script}"
    if properties.timeout is not None and properties.timeout <= 0:
        raise ConfigurationError(
            f"timeout = {properties.timeout} on {where} must be a positive number of seconds."
        )
    for key, _value in properties.env:
        if not _IDENTIFIER.match(key):
            raise ConfigurationError(f"Environment variable name {key!r} on {where} is invalid.")
    values = [
        *properties.labels,
        *(value for _key, value in properties.env),
        *properties.fixtures_setup,
        *properties.fixtures_cleanup,
        *properties.fixtures_required,
    ]
    for value in values:
        if _LIST_SEPARATOR in value:
            raise ConfigurationError(
                f"{value!r} on {where} contains ';', which CTest reads as a list "
                f"separator. Split it into separate entries."
            )
    directory = properties.working_directory
    if directory is not None:
        _require_inside_root(directory, what=f"working_directory on {where}")
        if not (model.root_dir / directory).is_dir():
            raise ConfigurationError(
                f"working_directory '{directory.as_posix()}' on {where} does not exist."
            )


def _check_install_options(model: ProjectModel) -> None:
    """Check each install rule's component, RPATH mode, and destination.

    Args:
        model: The frozen project node.

    Raises:
        ConfigurationError: On an invalid component name, RPATH mode, or an
            absolute destination.
    """
    for install in model.installs:
        options = install.options
        where = f"install({install.target}) in {model.source_script}"
        if options.component is not None and not _COMPONENT.match(options.component):
            raise ConfigurationError(
                f"component={options.component!r} on {where} is not a valid name."
            )
        if options.rpath is not None and options.rpath not in _RPATH_MODES:
            raise ConfigurationError(
                f'rpath={options.rpath!r} on {where} must be "relative" or None.'
            )
        if options.destination is not None:
            _require_inside_root(Path(options.destination), what=f"destination on {where}")


def _check_install_files(model: ProjectModel) -> None:
    """Require every install_files() path to exist inside the project root.

    Args:
        model: The frozen project node.

    Raises:
        ConfigurationError: When a path escapes the root or does not exist.
    """
    for files in model.install_files:
        _require_inside_root(Path(files.destination), what="install_files() destination")
        for path in files.paths:
            _require_inside_root(path, what="install_files() path")
            if not (model.root_dir / path).exists():
                raise ConfigurationError(
                    f"install_files() path '{path.as_posix()}' in {model.source_script} "
                    f"does not exist (looked for {model.root_dir / path})."
                )


def _check_package_metadata(model: ProjectModel) -> None:
    """Require a declared license file to exist, so installers can show it.

    Args:
        model: The frozen project node.

    Raises:
        ConfigurationError: When the license file is missing.
    """
    license_file = model.package_metadata.license_file
    if license_file is None:
        return
    _require_inside_root(license_file, what="package(license_file=...)")
    if not (model.root_dir / license_file).is_file():
        raise ConfigurationError(
            f"package(license_file='{license_file.as_posix()}') in {model.source_script} "
            f"does not exist. Point it at the project's LICENSE file."
        )


def _check_allow_system(model: ProjectModel) -> None:
    """Require allow_system() names to be packages this project depends on.

    Args:
        model: The frozen project node.

    Raises:
        ConfigurationError: When a name matches no dependency, which is
            almost always a typo that would silently do nothing.
    """
    known = {dependency.name for dependency in model.dependencies}
    unknown = sorted(set(model.allow_system) - known)
    if unknown:
        raise ConfigurationError(
            f"allow_system({', '.join(repr(name) for name in unknown)}) in "
            f"{model.source_script} names packages this project does not depend on. "
            f'Use the names from depends(), for example allow_system("zlib").'
        )


def _check_subproject_conditions(model: ProjectModel) -> None:
    """Refuse a build-configuration test on add_subproject(when=...).

    Whether a subdirectory exists is decided at configure time, and a
    multi-config generator (Visual Studio, Xcode, Ninja Multi-Config) has no
    single configuration then.

    Args:
        model: The frozen project node.

    Raises:
        ConfigurationError: When a subproject condition tests the config.
    """
    for node in model.subprojects:
        if node.when is not None and _tests_config(node.when):
            raise ConfigurationError(
                f"add_subproject('{node.directory.as_posix()}', when=...) in "
                f"{model.source_script} tests the build configuration, which is not "
                f"known at configure time under multi-config generators. Guard on a "
                f"platform, compiler, or project.option() instead."
            )


def _tests_config(when: WhenModel) -> bool:
    """Tell whether a condition tree contains a build-configuration leaf.

    Args:
        when: The condition.

    Returns:
        True when any leaf is When.config(...).
    """
    if when.kind is WhenKind.CONFIG:
        return True
    return any(_tests_config(operand) for operand in when.operands)
