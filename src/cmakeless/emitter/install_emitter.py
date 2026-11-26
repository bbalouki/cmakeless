"""Install rules, package exports, and CPack configuration for one project node.

Pure functions of the frozen model, so the visitor only decides where in the
file these sections land.
"""

from __future__ import annotations

import uuid

from cmakeless.emitter.quoting import quote_argument
from cmakeless.model.nodes import (
    CPACK_GENERATOR_BY_FORMAT,
    CompiledModel,
    InstallModel,
    LibraryKind,
    LibraryModel,
    ProjectModel,
    PythonModuleModel,
)
from cmakeless.model.properties import InstallFilesModel

# The namespace WiX upgrade codes are derived from, so a project keeps the
# same upgrade code across releases without anyone storing a GUID.
_WIX_NAMESPACE = uuid.UUID("6f6c3a4e-8b1f-5c7d-9e2a-3b4c5d6e7f80")

# Runtime dependencies the operating system always provides; bundling them
# would ship copies of the C runtime or the Windows API sets.
_SYSTEM_DEPENDENCY_EXCLUDES = (
    '    PRE_EXCLUDE_REGEXES "api-ms-.*" "ext-ms-.*"\n'
    '    POST_EXCLUDE_REGEXES ".*[Ss]ystem32/.*\\\\.dll" "^/lib.*" "^/usr/lib.*" "^/System/.*"'
)

PKG_CONFIG_TEMPLATE_SUFFIX = ".pc.in"
SIGNING_SCRIPT_NAME = "cmakeless_sign.cmake"


def install_sections(model: ProjectModel) -> list[str]:
    """Emit every install rule, file install, export, and signing step.

    Args:
        model: The frozen project node.

    Returns:
        The sections in a fixed order; empty without install rules or files.
    """
    sections = [
        _visit_install(install, model)
        for install in sorted(model.installs, key=lambda rule: rule.target)
    ]
    sections.extend(_install_files_section(files) for files in model.install_files)
    if _exported_installs(model):
        sections.append(export_section(model))
        if model.export.pkg_config:
            sections.append(_pkg_config_section(model))
    if model.signing is not None and model.installs:
        sections.append(
            f"# Code signing reads its credentials from the environment at install time.\n"
            f"install(SCRIPT ${{CMAKE_CURRENT_SOURCE_DIR}}/cmake/{SIGNING_SCRIPT_NAME})"
        )
    return sections


def _target_named(model: ProjectModel, name: str) -> CompiledModel | None:
    """Find one of this node's compiled targets by name.

    Args:
        model: The frozen project node.
        name: The target name.

    Returns:
        The target, or None when it is not this node's.
    """
    return next((target for target in model.all_targets() if target.name == name), None)


def _exported_installs(model: ProjectModel) -> list[InstallModel]:
    """The install rules whose targets join the project's export set.

    Python modules are imported by an interpreter, never found with
    find_package(), so they are installed but not exported.

    Args:
        model: The frozen project node.

    Returns:
        The exportable install rules.
    """
    return [
        install
        for install in model.installs
        if not isinstance(_target_named(model, install.target), PythonModuleModel)
    ]


def _visit_install(install: InstallModel, model: ProjectModel) -> str:
    """Emit one target's install rule, plus headers, RPATH, and runtime DLLs.

    Args:
        install: The install rule to emit.
        model: The frozen project node.

    Returns:
        The rule's complete section text.
    """
    target = _target_named(model, install.target)
    blocks = []
    if install.options.rpath == "relative":
        blocks.append(_rpath_block(install.target))
    if install.options.runtime_dependencies:
        blocks.append(_runtime_dependency_block(install, model, target))
    else:
        blocks.append(_install_targets_command(install, model, target, dependency_set=None))
    if install.headers and isinstance(target, LibraryModel):
        blocks.extend(_header_install_blocks(target, install.options.component))
    return "\n\n".join(blocks)


def _install_targets_command(
    install: InstallModel,
    model: ProjectModel,
    target: CompiledModel | None,
    *,
    dependency_set: str | None,
) -> str:
    """Write the install(TARGETS ...) command for one rule.

    Args:
        install: The install rule.
        model: The frozen project node.
        target: The installed target, when it belongs to this node.
        dependency_set: The runtime dependency set to record, or None.

    Returns:
        The command text.
    """
    component = _component_suffix(install.options.component)
    lines = [f"install(TARGETS {install.target}"]
    if not isinstance(target, PythonModuleModel):
        lines.append(f"    EXPORT {model.name}Targets")
    if dependency_set is not None:
        lines.append(f"    RUNTIME_DEPENDENCY_SET {dependency_set}")
    lines.extend(f"    {line}{component}" for line in _destination_lines(install, target))
    if target is not None and target.cxx_modules and isinstance(target, LibraryModel):
        lines.append(
            f"    FILE_SET CXX_MODULES DESTINATION "
            f"${{CMAKE_INSTALL_INCLUDEDIR}}/{target.name}{component}"
        )
    if install.headers:
        # INCLUDES DESTINATION teaches the exported target where its
        # headers land, replacing the BUILD_INTERFACE-only build path.
        lines.append("    INCLUDES DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}")
    lines.append(")")
    return "\n".join(lines)


def _destination_lines(install: InstallModel, target: CompiledModel | None) -> list[str]:
    """Choose the artifact destinations for one install rule.

    Args:
        install: The install rule.
        target: The installed target, when it belongs to this node.

    Returns:
        The RUNTIME/LIBRARY/ARCHIVE destination clauses.
    """
    explicit = install.options.destination
    if isinstance(target, PythonModuleModel):
        return [f"LIBRARY DESTINATION {explicit or '.'}"]
    if explicit is not None:
        return [f"{kind} DESTINATION {explicit}" for kind in ("RUNTIME", "LIBRARY", "ARCHIVE")]
    return [
        "RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}",
        "LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}",
        "ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}",
    ]


def _component_suffix(component: str | None) -> str:
    """Render the COMPONENT clause appended to each destination.

    Args:
        component: The CPack component, or None.

    Returns:
        " COMPONENT <name>", or an empty string.
    """
    return f" COMPONENT {component}" if component is not None else ""


def _rpath_block(target_name: str) -> str:
    """Make an installed binary find its sibling libraries without LD_LIBRARY_PATH.

    Args:
        target_name: The installed target.

    Returns:
        The platform-split INSTALL_RPATH block.
    """
    return (
        f"if(APPLE)\n"
        f"    set_target_properties({target_name} PROPERTIES INSTALL_RPATH\n"
        f'        "@loader_path/../${{CMAKE_INSTALL_LIBDIR}};@loader_path")\n'
        f"else()\n"
        f"    set_target_properties({target_name} PROPERTIES INSTALL_RPATH\n"
        f'        "$ORIGIN/../${{CMAKE_INSTALL_LIBDIR}};$ORIGIN")\n'
        f"endif()"
    )


def _runtime_dependency_block(
    install: InstallModel, model: ProjectModel, target: CompiledModel | None
) -> str:
    """Install a target together with the shared libraries it loads at runtime.

    CMake resolves runtime dependency sets only on Windows, Linux, and macOS
    hosts building natively, so every other case falls back to a plain
    install rule rather than failing to configure.

    Args:
        install: The install rule.
        model: The frozen project node.
        target: The installed target.

    Returns:
        The guarded block.
    """
    dependency_set = f"{install.target}_runtime_dependencies"
    with_set = _install_targets_command(install, model, target, dependency_set=dependency_set)
    without_set = _install_targets_command(install, model, target, dependency_set=None)
    component = _component_suffix(install.options.component)
    return (
        f'if(CMAKE_SYSTEM_NAME MATCHES "^(Windows|Linux|Darwin)$" AND NOT CMAKE_CROSSCOMPILING)\n'
        f"{_indent(with_set)}\n"
        f"    install(RUNTIME_DEPENDENCY_SET {dependency_set}\n"
        f"{_indent(_SYSTEM_DEPENDENCY_EXCLUDES)}\n"
        f"        RUNTIME DESTINATION ${{CMAKE_INSTALL_BINDIR}}{component}\n"
        f"        LIBRARY DESTINATION ${{CMAKE_INSTALL_LIBDIR}}{component}\n"
        f"    )\n"
        f"else()\n"
        f"{_indent(without_set)}\n"
        f"endif()"
    )


def _indent(text: str) -> str:
    """Indent every line of a block by one level.

    Args:
        text: The block.

    Returns:
        The block, each line prefixed with four spaces.
    """
    return "\n".join(f"    {line}" for line in text.splitlines())


def _header_install_blocks(library: LibraryModel, component: str | None) -> list[str]:
    """Emit the header installs for one installed library.

    Args:
        library: The installed library.
        component: The CPack component, or None.

    Returns:
        One install command per public header directory, plus the
        generated export header for shared libraries and plugins.
    """
    suffix = _component_suffix(component)
    blocks = [
        f"install(DIRECTORY {directory.as_posix()}/ "
        f"DESTINATION ${{CMAKE_INSTALL_INCLUDEDIR}}{suffix})"
        for directory in sorted(library.public_include_dirs)
    ]
    if library.kind in (LibraryKind.SHARED, LibraryKind.PLUGIN):
        blocks.append(
            f"install(FILES ${{CMAKE_CURRENT_BINARY_DIR}}/{library.name}_export.h "
            f"DESTINATION ${{CMAKE_INSTALL_INCLUDEDIR}}{suffix})"
        )
    return blocks


def _install_files_section(files: InstallFilesModel) -> str:
    """Emit one install_files() call.

    Args:
        files: The files or directories to ship.

    Returns:
        The install(FILES|DIRECTORY ...) command text.
    """
    keyword = "DIRECTORY" if files.directory else "FILES"
    trailing = "/" if files.directory and files.contents_only else ""
    lines = [f"install({keyword}"]
    lines.extend(f"    {path.as_posix()}{trailing}" for path in files.paths)
    lines.append(f"    DESTINATION {files.destination}{_component_suffix(files.component)}")
    lines.append(")")
    return "\n".join(lines)


def export_section(model: ProjectModel) -> str:
    """Emit the export set and package metadata files for find_package.

    Args:
        model: The frozen project node.

    Returns:
        The complete export section: install(EXPORT), the version and
        config files, and, when requested, a CPS description.
    """
    name = model.name
    destination = f"${{CMAKE_INSTALL_LIBDIR}}/cmake/{name}"
    modules = (
        "    CXX_MODULES_DIRECTORY cxx-modules\n"
        if any(target.cxx_modules for target in model.libraries)
        else ""
    )
    text = (
        f"install(EXPORT {name}Targets\n"
        f"    FILE {name}Targets.cmake\n"
        f"    NAMESPACE {name}::\n"
        f"    DESTINATION {destination}\n"
        f"{modules}"
        f")\n"
        f"\n"
        f"{_config_files_text(name, destination)}"
    )
    if model.export.cps:
        text += "\n\n" + _cps_command(model)
    return text


def _config_files_text(name: str, destination: str) -> str:
    """Write the Config.cmake and ConfigVersion.cmake generation and install.

    Args:
        name: The package name.
        destination: The install directory of the CMake package files.

    Returns:
        The commands text.
    """
    return (
        f"include(CMakePackageConfigHelpers)\n"
        f"\n"
        f"configure_package_config_file(\n"
        f"    ${{CMAKE_CURRENT_SOURCE_DIR}}/cmake/{name}Config.cmake.in\n"
        f"    ${{CMAKE_CURRENT_BINARY_DIR}}/{name}Config.cmake\n"
        f"    INSTALL_DESTINATION {destination}\n"
        f")\n"
        f"\n"
        f"write_basic_package_version_file(\n"
        f"    ${{CMAKE_CURRENT_BINARY_DIR}}/{name}ConfigVersion.cmake\n"
        f"    VERSION ${{PROJECT_VERSION}}\n"
        f"    COMPATIBILITY SameMajorVersion\n"
        f")\n"
        f"\n"
        f"install(FILES\n"
        f"    ${{CMAKE_CURRENT_BINARY_DIR}}/{name}Config.cmake\n"
        f"    ${{CMAKE_CURRENT_BINARY_DIR}}/{name}ConfigVersion.cmake\n"
        f"    DESTINATION {destination}\n"
        f")"
    )


def _cps_command(model: ProjectModel) -> str:
    """Write the install(PACKAGE_INFO ...) command for a CPS description.

    Args:
        model: The frozen project node.

    Returns:
        The command text.
    """
    metadata = model.package_metadata
    lines = [
        "# A Common Package Specification file, readable by tools other than CMake.",
        f"install(PACKAGE_INFO {model.name}",
        f"    EXPORT {model.name}Targets",
        "    VERSION ${PROJECT_VERSION}",
    ]
    if metadata.description is not None:
        lines.append(f"    DESCRIPTION {quote_argument(metadata.description)}")
    if metadata.homepage is not None:
        lines.append(f"    HOMEPAGE_URL {quote_argument(metadata.homepage)}")
    lines.append(")")
    return "\n".join(lines)


def _pkg_config_section(model: ProjectModel) -> str:
    """Configure and install the project's pkg-config file.

    Args:
        model: The frozen project node.

    Returns:
        The configure_file and install commands.
    """
    template = f"${{CMAKE_CURRENT_SOURCE_DIR}}/cmake/{model.name}{PKG_CONFIG_TEMPLATE_SUFFIX}"
    output = f"${{CMAKE_CURRENT_BINARY_DIR}}/{model.name}.pc"
    return (
        f"configure_file({template} {output} @ONLY)\n"
        f"install(FILES {output} DESTINATION ${{CMAKE_INSTALL_LIBDIR}}/pkgconfig)"
    )


def pkg_config_template(model: ProjectModel) -> str:
    """Write the pkg-config template configure_file() fills in.

    Args:
        model: The frozen project node.

    Returns:
        The .pc.in text, listing every installed compiled library.
    """
    installed = {install.target for install in model.installs}
    libraries = sorted(
        library.properties.output_name or library.name
        for library in model.libraries
        if library.name in installed and library.kind in (LibraryKind.STATIC, LibraryKind.SHARED)
    )
    description = model.package_metadata.description or model.name
    libs = "".join(f" -l{name}" for name in libraries)
    return (
        "prefix=@CMAKE_INSTALL_PREFIX@\n"
        "exec_prefix=${prefix}\n"
        "libdir=${prefix}/@CMAKE_INSTALL_LIBDIR@\n"
        "includedir=${prefix}/@CMAKE_INSTALL_INCLUDEDIR@\n"
        "\n"
        "Name: @PROJECT_NAME@\n"
        f"Description: {description}\n"
        "Version: @PROJECT_VERSION@\n"
        f"Libs: -L${{libdir}}{libs}\n"
        "Cflags: -I${includedir}\n"
    )


def cpack_sections(model: ProjectModel) -> list[str]:
    """Emit the CPack configuration for the requested package formats.

    Args:
        model: The frozen project node.

    Returns:
        The settings block and the include(CPack) that must come last;
        empty when packaging was not requested.
    """
    if not model.package_formats:
        return []
    generators = ";".join(
        CPACK_GENERATOR_BY_FORMAT[format_name] for format_name in sorted(model.package_formats)
    )
    lines = [
        f"set(CPACK_PACKAGE_NAME {model.name})",
        f"set(CPACK_PACKAGE_VERSION {model.version})",
    ]
    lines.extend(_cpack_metadata_lines(model))
    lines.append(f'set(CPACK_GENERATOR "{generators}")')
    return ["\n".join(lines), "include(CPack)"]


def _cpack_metadata_lines(model: ProjectModel) -> list[str]:
    """Translate package metadata into CPACK_* variables.

    Args:
        model: The frozen project node.

    Returns:
        One set() line per provided field, in a fixed order.
    """
    metadata = model.package_metadata
    values = (
        ("CPACK_PACKAGE_VENDOR", metadata.vendor),
        ("CPACK_PACKAGE_DESCRIPTION_SUMMARY", metadata.description),
        ("CPACK_PACKAGE_HOMEPAGE_URL", metadata.homepage),
    )
    lines = [f"set({name} {quote_argument(value)})" for name, value in values if value is not None]
    if metadata.license_file is not None:
        license_path = f"${{CMAKE_CURRENT_SOURCE_DIR}}/{metadata.license_file.as_posix()}"
        lines.append(f'set(CPACK_RESOURCE_FILE_LICENSE "{license_path}")')
    contact = metadata.contact
    if contact is None and "deb" in model.package_formats:
        # Debian packages refuse to build without a maintainer contact.
        contact = f"{model.name} maintainers"
    if contact is not None:
        lines.append(f"set(CPACK_PACKAGE_CONTACT {quote_argument(contact)})")
    if metadata.deb_depends:
        lines.append(
            f"set(CPACK_DEBIAN_PACKAGE_DEPENDS {quote_argument(', '.join(metadata.deb_depends))})"
        )
    if metadata.rpm_requires:
        lines.append(
            f"set(CPACK_RPM_PACKAGE_REQUIRES {quote_argument(', '.join(metadata.rpm_requires))})"
        )
    if "wix" in model.package_formats:
        upgrade = uuid.uuid5(_WIX_NAMESPACE, model.name)
        lines.append(f'set(CPACK_WIX_UPGRADE_GUID "{str(upgrade).upper()}")')
    return lines


def signing_script(model: ProjectModel) -> str:
    """Write the install-time signing script for every installed binary.

    Credentials never appear in the build description or the generated
    files: the script reads the environment variables the project named, and
    skips signing (with a status message) when they are unset, so developer
    installs stay fast.

    Args:
        model: The frozen project node, which must declare signing.

    Returns:
        The script text install(SCRIPT ...) runs.
    """
    assert model.signing is not None, "only emitted for projects that sign"
    signing = model.signing
    root = '"$ENV{DESTDIR}${CMAKE_INSTALL_PREFIX}"'
    lines = [f"# Generated by cmakeless from {model.source_script}; signs installed binaries."]
    if signing.windows_cert_env is not None:
        timestamp = signing.windows_timestamp_url or "http://timestamp.digicert.com"
        lines.extend(_windows_signing_lines(signing.windows_cert_env, timestamp, root))
    if signing.macos_identity_env is not None:
        lines.extend(_macos_signing_lines(signing.macos_identity_env, root))
    return "\n".join(lines) + "\n"


def _windows_signing_lines(cert_env: str, timestamp: str, root: str) -> list[str]:
    """Sign every installed .exe and .dll with signtool.

    Args:
        cert_env: The environment variable holding the certificate path.
        timestamp: The RFC 3161 timestamp server.
        root: The quoted install root expression.

    Returns:
        The script lines.
    """
    return [
        f"if(WIN32 AND DEFINED ENV{{{cert_env}}})",
        "    find_program(_cmakeless_signtool signtool REQUIRED)",
        f"    file(GLOB_RECURSE _cmakeless_binaries {root}/*.exe {root}/*.dll)",
        "    foreach(_binary IN LISTS _cmakeless_binaries)",
        "        execute_process(COMMAND ${_cmakeless_signtool} sign /fd SHA256",
        f'            /f "$ENV{{{cert_env}}}" /tr {quote_argument(timestamp)}',
        '            /td SHA256 "${_binary}"',
        "            COMMAND_ERROR_IS_FATAL ANY)",
        "    endforeach()",
        "elseif(WIN32)",
        f'    message(STATUS "Skipping Windows signing: {cert_env} is not set")',
        "endif()",
    ]


def _macos_signing_lines(identity_env: str, root: str) -> list[str]:
    """Sign every installed binary and bundle with codesign.

    Args:
        identity_env: The environment variable holding the signing identity.
        root: The quoted install root expression.

    Returns:
        The script lines.
    """
    return [
        f"if(APPLE AND DEFINED ENV{{{identity_env}}})",
        f"    file(GLOB_RECURSE _cmakeless_binaries {root}/bin/* {root}/lib/*.dylib)",
        "    foreach(_binary IN LISTS _cmakeless_binaries)",
        "        execute_process(COMMAND codesign --force --timestamp --options runtime",
        f'            --sign "$ENV{{{identity_env}}}" "${{_binary}}" COMMAND_ERROR_IS_FATAL ANY)',
        "    endforeach()",
        "elseif(APPLE)",
        f'    message(STATUS "Skipping macOS signing: {identity_env} is not set")',
        "endif()",
    ]
