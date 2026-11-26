"""Flag syntax follows the compiler frontend; linker flags follow the linker family."""

from __future__ import annotations

from pathlib import Path

from cmakeless.api.cpu import Cpu
from cmakeless.api.profiles import Profile
from cmakeless.emitter import emit_cmakelists
from cmakeless.emitter.flags import cpu_lines, flag_line, language_guard, warning_lines
from cmakeless.model.nodes import ExecutableModel, LibraryKind, LibraryModel, ProjectModel
from cmakeless.model.properties import TargetPropertiesModel

FIXED_VERSION = "1.2.3"
MSVC = "${CMAKELESS_MSVC_SYNTAX}"


def make_model(*targets: ExecutableModel, **settings: object) -> ProjectModel:
    """Build a frozen project around the given executables."""
    return ProjectModel(
        name="demo",
        version="1.0.0",
        cpp_std=20,
        root_dir=Path("/does/not/matter"),
        source_script="cmakelessfile.py",
        executables=targets,
        **settings,  # type: ignore[arg-type]
    )


def test_flag_line_combines_conditions_with_and() -> None:
    """Several conditions nest into one $<AND:...> guard."""
    assert flag_line(("-a", "-b")) == "-a;-b"
    assert flag_line(("-a",), "C1") == "$<C1:-a>"
    assert flag_line(("-a",), "C1", None, "C2") == "$<$<AND:C1,C2>:-a>"


def test_cxx_only_projects_need_no_language_guard() -> None:
    """A C++-only project leaves flags unguarded by language."""
    assert language_guard(("CXX",)) is None
    assert language_guard(("CXX", "C")) == "$<COMPILE_LANGUAGE:C,CXX>"
    assert language_guard(("CXX", "CUDA"), cxx_only=True) == "$<COMPILE_LANGUAGE:CXX>"


def test_strict_warnings_key_on_frontend_syntax_not_compiler_id() -> None:
    """clang-cl gets /W4 through the syntax variable, never GNU -Wall."""
    lines = warning_lines("strict", ("CXX",))
    assert lines[0] == f"$<{MSVC}:/W4;/permissive->"
    assert lines[1].startswith(f"$<$<NOT:{MSVC}>:-Wall")


def test_max_warnings_keep_cxx_only_flags_away_from_c_sources() -> None:
    """In a mixed C and C++ project, -Wold-style-cast is guarded to C++."""
    lines = warning_lines("max", ("CXX", "C"))
    cxx_only = [line for line in lines if "-Wold-style-cast" in line]
    assert cxx_only and "$<COMPILE_LANGUAGE:CXX>" in cxx_only[0]
    assert any("-Wshadow" in line and "$<COMPILE_LANGUAGE:C,CXX>" in line for line in lines)


def test_default_warnings_add_nothing() -> None:
    """The default preset leaves the compiler's own defaults alone."""
    assert warning_lines("default", ("CXX",)) == []


def test_x86_levels_translate_per_syntax() -> None:
    """v3 is -march=x86-64-v3 for GCC/Clang and /arch:AVX2 for cl."""
    compile_lines, link_lines = cpu_lines(Cpu.x86_64(level="v3")._freeze(), ("CXX",))
    assert any("-march=x86-64-v3" in line for line in compile_lines)
    assert any("/arch:AVX2" in line for line in compile_lines)
    assert link_lines == []


def test_arm_cores_reach_both_compile_and_link() -> None:
    """ARM flags also go to the link step so the driver picks the right multilib."""
    cpu = Cpu.arm(core="cortex-m7", fpu="fpv5-d16", float_abi="hard")._freeze()
    compile_lines, link_lines = cpu_lines(cpu, ("CXX",))
    assert "-mcpu=cortex-m7;-mfpu=fpv5-d16;-mfloat-abi=hard" in compile_lines[0]
    assert link_lines and "-mcpu=cortex-m7" in link_lines[0]


def test_a_project_profile_emits_preamble_checks_and_linker_flags() -> None:
    """A hardened profile brings PIE checks, x86 detection, and LINKER: flags."""
    app = ExecutableModel(name="app", sources=(Path("main.cpp"),))
    text = emit_cmakelists(
        make_model(app, profile=Profile.hardened()._freeze()), tool_version=FIXED_VERSION
    )
    assert "check_pie_supported()" in text
    assert "set(CMAKELESS_X86 ON)" in text
    assert "LINKER:-z,relro;LINKER:-z,now" in text
    assert "POSITION_INDEPENDENT_CODE ON" in text
    assert "_GLIBCXX_ASSERTIONS" in text


def test_a_target_profile_replaces_the_projects() -> None:
    """A target's own profile wins over the project-wide one."""
    own = TargetPropertiesModel(profile=Profile.reproducible()._freeze())
    app = ExecutableModel(name="app", sources=(Path("main.cpp"),), properties=own)
    model = make_model(app, profile=Profile.hardened()._freeze())
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert "-ffile-prefix-map=${CMAKE_SOURCE_DIR}=." in text
    assert "-fstack-protector-strong" not in text


def test_header_only_libraries_never_receive_compile_flags() -> None:
    """An INTERFACE library compiles nothing, so no profile flags land on it."""
    header_only = LibraryModel(
        name="hdr", kind=LibraryKind.HEADER_ONLY, sources=(), public_include_dirs=(Path("include"),)
    )
    model = ProjectModel(
        name="demo",
        version="1.0.0",
        cpp_std=20,
        root_dir=Path("/x"),
        source_script="cmakelessfile.py",
        libraries=(header_only,),
        profile=Profile.hardened()._freeze(),
    )
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert "CMAKELESS_MSVC_SYNTAX" not in text


def test_profiles_compose_and_deduplicate_names() -> None:
    """Composition keeps each name once and accumulates switches."""
    combined = Profile.hardened() | Profile.reproducible() | Profile.hardened()
    assert combined.names == ("hardened", "reproducible")
    assert combined._freeze().position_independent


def test_safety_critical_turns_warnings_into_errors() -> None:
    """The safety-critical profile implies COMPILE_WARNING_AS_ERROR."""
    app = ExecutableModel(name="app", sources=(Path("main.cpp"),))
    model = make_model(app, profile=Profile.safety_critical()._freeze())
    assert "COMPILE_WARNING_AS_ERROR ON" in emit_cmakelists(model, tool_version=FIXED_VERSION)
