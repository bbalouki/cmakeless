"""The 1.1 build-description vocabulary, frozen and validated through the public API."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from cmakeless import (
    Cache,
    ConfigurationError,
    Cpu,
    Imported,
    Profile,
    Project,
    Rules,
    Signing,
    System,
    When,
    register_extension,
)
from cmakeless.model.nodes import LinkKind


@pytest.fixture
def project(project_dir: Path) -> Project:
    """A project rooted at the minimal on-disk layout."""
    return Project("demo", root=project_dir, cpp_std=20)


def test_typed_system_links_freeze_with_their_kinds(project: Project) -> None:
    """System and imported links become external edges of the right kind."""
    app = project.add_executable("app", sources=["src/main.cpp"])
    app.link(System.threads())
    app.link(System.library("dl"), when=When.platform("linux"))
    app.link(System.framework("Metal"))
    app.link(Imported("Vulkan::Vulkan"))
    kinds = {link.target: link.kind for link in project.freeze().executables[0].links}
    assert kinds == {
        "Threads::Threads": LinkKind.THREADS,
        "dl": LinkKind.SYSTEM,
        "Metal": LinkKind.FRAMEWORK,
        "Vulkan::Vulkan": LinkKind.IMPORTED,
    }


@pytest.mark.parametrize("bad", ["-lfoo", "../libfoo", "", "a b"])
def test_system_library_rejects_paths_and_flags(bad: str) -> None:
    """A system library name can never smuggle in a flag or a path."""
    with pytest.raises(ConfigurationError, match="not a bare library name"):
        System.library(bad)


def test_imported_targets_must_be_namespaced() -> None:
    """Imported() points at System.library() for plain names."""
    with pytest.raises(ConfigurationError, match=r"System.library"):
        Imported("vulkan")


def test_plugins_cannot_be_linked(project: Project) -> None:
    """A plugin is loaded at runtime, so linking it is refused at the call site."""
    plugin = project.add_library("strategy", sources=["src/main.cpp"], kind="plugin")
    app = project.add_executable("app", sources=["src/main.cpp"])
    with pytest.raises(ConfigurationError, match="loaded at runtime"):
        app.link(plugin)


def test_target_settings_freeze_into_properties(project: Project) -> None:
    """Every per-target setting reaches the model unchanged."""
    lib = project.add_library(
        "engine", sources=["src/main.cpp"], kind="shared", version="2.3.1", soversion="2"
    )
    lib.output_name = "engine2"
    lib.visibility = "hidden"
    lib.cpu = Cpu.x86_64(level="v3")
    lib.profile = Profile.low_latency()
    lib.post_build("strip", lib.file)
    properties = project.freeze().libraries[0].properties
    assert (properties.version, properties.soversion, properties.output_name) == (
        "2.3.1",
        "2",
        "engine2",
    )
    assert properties.post_build == (("strip", "$<TARGET_FILE:engine>"),)
    assert properties.profile is not None and properties.profile.ipo_release
    assert properties.declared_line is not None


@pytest.mark.parametrize(
    ("attribute", "value", "message"),
    [
        ("visibility", "secret", "visibility"),
        ("msvc_runtime", "shared", "msvc_runtime"),
        ("warnings", "loud", "warnings"),
        ("c_std", 98, "not a C standard"),
        ("output_name", "bin/app", "bare file name"),
        ("cuda_architectures", ["sm_86"], "cuda_architectures"),
        ("linker_script", "boards/missing.ld", "does not exist"),
    ],
)
def test_invalid_target_settings_fail_at_freeze(
    project: Project, attribute: str, value: object, message: str
) -> None:
    """Every invalid setting is a ConfigurationError naming the setting."""
    app = project.add_executable("app", sources=["src/main.cpp"])
    setattr(app, attribute, value)
    with pytest.raises(ConfigurationError, match=message):
        project.freeze()


def test_abi_versions_only_apply_to_shared_libraries(project: Project) -> None:
    """A static library has no ABI version in its file name."""
    project.add_library("core", sources=["src/main.cpp"], kind="static", version="1.0")
    with pytest.raises(ConfigurationError, match="only to shared libraries"):
        project.freeze()


def test_gui_applies_only_to_executables(project: Project) -> None:
    """A windowed subsystem means nothing on a library."""
    lib = project.add_library("core", sources=["src/main.cpp"])
    lib.gui = True
    with pytest.raises(ConfigurationError, match="only to executables"):
        project.freeze()


def test_test_properties_are_validated(project: Project) -> None:
    """A semicolon in a label would split in CTest, so it is refused."""
    test = project.add_test("t", sources=["src/main.cpp"], framework="none", labels=["a;b"])
    assert test.labels == ["a;b"]
    with pytest.raises(ConfigurationError, match="list"):
        project.freeze()


def test_test_timeout_must_be_positive(project: Project) -> None:
    """A zero timeout is a mistake, not 'no limit'."""
    project.add_test("t", sources=["src/main.cpp"], framework="none", timeout=0)
    with pytest.raises(ConfigurationError, match="positive"):
        project.freeze()


def test_install_and_package_options_freeze(project: Project) -> None:
    """Install options, files, metadata, export, and signing all reach the model."""
    (project.root / "assets").mkdir()
    (project.root / "assets" / "a.txt").write_text("x", encoding="utf-8")
    (project.root / "LICENSE").write_text("x", encoding="utf-8")
    app = project.add_executable("app", sources=["src/main.cpp"])
    project.install(app, component="runtime", rpath="relative", runtime_dependencies=True)
    project.install_files("assets/", destination="share/demo")
    project.export(cps=True)
    project.package(formats=["zip", "nsis"], vendor="Acme", license_file="LICENSE")
    project.sign(windows=Signing.signtool(cert_env="WIN_CERT"))
    model = project.freeze()
    assert model.installs[0].options.runtime_dependencies
    assert model.install_files[0].directory and model.install_files[0].contents_only
    assert model.export.cps and model.package_metadata.vendor == "Acme"
    assert model.signing is not None and model.signing.windows_cert_env == "WIN_CERT"


def test_install_files_refuses_mixed_kinds(project: Project) -> None:
    """Files and directories go in separate install_files() calls."""
    with pytest.raises(ConfigurationError, match="mixes files and directories"):
        project.install_files("src", "src/main.cpp", destination="share")


def test_signing_refuses_anything_but_a_variable_name() -> None:
    """A secret pasted in place of a variable name is refused."""
    with pytest.raises(ConfigurationError, match="never the secret"):
        Signing.signtool(cert_env="C:/certs/me.pfx")


def test_cache_backends_reference_the_environment() -> None:
    """sccache backends store a variable reference, never a value."""
    cache = Cache.sccache(backend="s3", bucket_env="BUILD_BUCKET")
    assert cache._freeze().env == (("SCCACHE_BUCKET", "$BUILD_BUCKET"),)
    with pytest.raises(ConfigurationError, match="Unknown sccache backend"):
        Cache.sccache(backend="ftp")
    with pytest.raises(ConfigurationError, match="20G"):
        Cache.ccache(max_size="lots")


def test_rules_compose_into_one_clang_tidy_command(project: Project) -> None:
    """Rule sets merge without duplicates into the project lint command."""
    project.lint(clang_tidy=Rules.cert() | Rules.misra_cpp_2023(), cppcheck=True)
    model = project.freeze()
    assert model.lint_clang_tidy[0] == "clang-tidy"
    assert model.lint_clang_tidy[1].count("cert-*") == 1
    assert model.lint_cppcheck == ("cppcheck",)


def test_supply_chain_mode_and_allowed_packages_are_validated(project: Project) -> None:
    """allow_system() must name a real dependency of the project."""
    project.supply_chain = "strict"
    project.allow_system("zlib")
    with pytest.raises(ConfigurationError, match="does not depend on"):
        project.freeze()


def test_a_config_condition_cannot_guard_a_subproject(project: Project) -> None:
    """Multi-config generators have no configuration at configure time."""
    child = project.root / "child"
    (child / "src").mkdir(parents=True)
    (child / "src" / "main.cpp").write_text("int main() { return 0; }\n", encoding="utf-8")
    (child / "cmakelessfile.py").write_text(
        "from cmakeless import Project\n"
        'p = Project("child")\n'
        'p.add_executable("tool", sources=["src/main.cpp"])\n'
        "p.build()\n",
        encoding="utf-8",
    )
    project.add_subproject("child", when=When.config("Debug"))
    with pytest.raises(ConfigurationError, match="multi-config"):
        project.freeze()


def test_shaders_become_one_command_per_source(project: Project) -> None:
    """Each shader is its own build step, rebuilt when it changes."""
    shaders = project.root / "shaders"
    shaders.mkdir()
    for name in ("a.hlsl", "b.hlsl"):
        (shaders / name).write_text("float4 main() : SV_Target { return 0; }\n", encoding="utf-8")
    commands = project.add_shaders(
        "shaders/*.hlsl", compiler="dxc", profile="ps_6_6", output="compiled"
    )
    assert [command.outputs for command in commands] == [
        ("compiled/a.hlsl.cso",),
        ("compiled/b.hlsl.cso",),
    ]
    with pytest.raises(ConfigurationError, match="needs a profile"):
        project.add_shaders("shaders/*.hlsl", compiler="dxc", output="compiled")


def test_fuzz_targets_carry_libfuzzer_flags(project: Project) -> None:
    """A fuzz target is guarded to the compilers that ship libFuzzer."""
    project.add_fuzz_target("fuzz_parse", sources=["src/main.cpp"])
    fuzz = project.freeze().fuzz_targets[0]
    assert any("-fsanitize=fuzzer" in options.flags[0] for options in fuzz.compile_options)


class _Banner:
    """A tiny in-process extension used to exercise the plugin protocol."""

    version = "9.9.9"

    def emit(self, target: str, options: Mapping[str, object]) -> str:
        """Return one comment naming the target and its option."""
        return f"# banner {target} {options.get('text', '')}"


def test_extensions_run_at_the_call_site_and_record_their_version(project: Project) -> None:
    """A registered extension's output is frozen with its name and version."""
    register_extension("banner", _Banner())
    app = project.add_executable("app", sources=["src/main.cpp"])
    app.extend("banner", text="hi")
    use = project.freeze().executables[0].properties.extensions[0]
    assert (use.name, use.version, use.snippet) == ("banner", "9.9.9", "# banner app hi")
    with pytest.raises(ConfigurationError, match="No extension named"):
        app.extend("missing")


def test_python_modules_configure_against_the_running_interpreter(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FindPython is pointed at this interpreter, so the extension ABI matches."""
    import subprocess
    import sys

    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        """Record the configure command instead of running CMake."""
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("cmakeless.driver.cmake_driver.subprocess.run", fake_run)
    monkeypatch.setattr("cmakeless.driver.cmake_driver.shutil.which", lambda tool: tool)
    project.add_python_module("core", sources=["src/main.cpp"])
    driver = project._driver(project.freeze())
    driver.configure()
    expected = f"-DPython_EXECUTABLE={Path(sys.executable).as_posix()}"
    assert expected in commands[0]
