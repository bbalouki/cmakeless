"""Emitter coverage for custom build steps: add_command() and add_custom_target()."""

from __future__ import annotations

from pathlib import Path

from cmakeless.emitter import emit_cmakelists
from cmakeless.model.nodes import CommandModel, CustomTargetModel, ExecutableModel, ProjectModel

FIXED_VERSION = "1.2.3"
GOLDEN_DIR = Path(__file__).parent / "golden"


def make_model(**overrides: object) -> ProjectModel:
    """Build a frozen project with the given field overrides."""
    fields: dict[str, object] = {
        "name": "demo",
        "version": "1.0.0",
        "cpp_std": 17,
        "root_dir": Path("/does/not/matter"),
        "source_script": "cmakelessfile.py",
    }
    fields.update(overrides)
    return ProjectModel(**fields)  # type: ignore[arg-type]


def test_command_emits_custom_command_with_output_and_depends() -> None:
    """Command emits custom command with output and depends."""
    command = CommandModel(
        outputs=(Path("generated/version.cpp"),),
        command=("python", "tools/gen_version.py"),
        depends=(Path("tools/gen_version.py"),),
        comment="Generating version.cpp",
    )
    text = emit_cmakelists(make_model(commands=(command,)), tool_version=FIXED_VERSION)
    assert "add_custom_command(" in text
    assert "    OUTPUT\n        generated/version.cpp" in text
    # The script argument is anchored to the source dir: CMake runs a custom
    # command's argv with the build directory as its default CWD.
    assert "COMMAND python ${CMAKE_CURRENT_SOURCE_DIR}/tools/gen_version.py" in text
    assert "DEPENDS tools/gen_version.py" in text
    assert 'COMMENT "Generating version.cpp"' in text
    assert "VERBATIM" in text


def test_command_argument_matching_its_own_output_is_anchored_to_the_binary_dir() -> None:
    """A command argument matching its own declared output is anchored to the binary dir."""
    command = CommandModel(
        outputs=(Path("generated/version.cpp"),),
        command=("python", "tools/gen.py", "--out", "generated/version.cpp"),
        depends=(Path("tools/gen.py"),),
    )
    text = emit_cmakelists(make_model(commands=(command,)), tool_version=FIXED_VERSION)
    assert "--out ${CMAKE_CURRENT_BINARY_DIR}/generated/version.cpp" in text


def test_command_argument_matching_another_commands_output_is_anchored_too() -> None:
    """An argument matching a different command's output is also binary-dir anchored."""
    producer = CommandModel(outputs=(Path("assets/manifest.json"),), command=("gen-manifest",))
    consumer = CommandModel(
        outputs=(Path("cooked/done.marker"),),
        command=("python", "cook.py", "--manifest", "assets/manifest.json"),
        depends=(Path("assets/manifest.json"),),
    )
    text = emit_cmakelists(make_model(commands=(producer, consumer)), tool_version=FIXED_VERSION)
    assert "--manifest ${CMAKE_CURRENT_BINARY_DIR}/assets/manifest.json" in text


def test_command_flags_and_interpreter_name_are_left_untouched() -> None:
    """Plain flags and the interpreter name are never anchored."""
    command = CommandModel(outputs=(Path("out.txt"),), command=("python", "--version"))
    text = emit_cmakelists(make_model(commands=(command,)), tool_version=FIXED_VERSION)
    assert "COMMAND python --version" in text


def test_command_without_comment_or_depends_omits_those_lines() -> None:
    """Command without comment or depends omits those lines."""
    command = CommandModel(outputs=(Path("out.txt"),), command=("touch", "out.txt"))
    text = emit_cmakelists(make_model(commands=(command,)), tool_version=FIXED_VERSION)
    assert "COMMENT" not in text
    assert "DEPENDS" not in text


def test_command_feeds_a_targets_sources() -> None:
    """A command's output threads straight into a target's target_sources()."""
    command = CommandModel(outputs=(Path("generated/version.cpp"),), command=("gen",))
    app = ExecutableModel(name="app", sources=(Path("src/main.cpp"), Path("generated/version.cpp")))
    text = emit_cmakelists(
        make_model(commands=(command,), executables=(app,)), tool_version=FIXED_VERSION
    )
    assert "target_sources(app PRIVATE\n    generated/version.cpp\n    src/main.cpp\n)" in text


def test_custom_target_emits_add_custom_target_with_depends() -> None:
    """Custom target emits add custom target with depends."""
    target = CustomTargetModel(
        name="cook-assets", command=("python", "cook.py"), depends=(Path("assets/manifest.json"),)
    )
    text = emit_cmakelists(make_model(custom_targets=(target,)), tool_version=FIXED_VERSION)
    assert "add_custom_target(cook-assets" in text
    assert "COMMAND python cook.py" in text
    assert "DEPENDS assets/manifest.json" in text
    assert "VERBATIM" in text


def test_custom_target_without_depends_omits_the_line() -> None:
    """Custom target without depends omits the line."""
    target = CustomTargetModel(name="lint", command=("ruff", "check", "."))
    text = emit_cmakelists(make_model(custom_targets=(target,)), tool_version=FIXED_VERSION)
    assert "DEPENDS" not in text


def test_commands_and_custom_targets_are_sorted_deterministically() -> None:
    """Commands and custom targets are sorted deterministically."""
    first = CommandModel(outputs=(Path("b.txt"),), command=("touch", "b.txt"))
    second = CommandModel(outputs=(Path("a.txt"),), command=("touch", "a.txt"))
    model = make_model(commands=(first, second))
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert text.index("a.txt") < text.index("b.txt")


def test_golden_custom_commands_file() -> None:
    """Golden custom commands file."""
    gen = CommandModel(
        outputs=(Path("generated/version.cpp"),),
        command=("python", "tools/gen_version.py", "--out", "generated/version.cpp"),
        depends=(Path("tools/gen_version.py"),),
        comment="Generating version.cpp",
    )
    app = ExecutableModel(name="app", sources=(Path("src/main.cpp"), Path("generated/version.cpp")))
    cook = CustomTargetModel(
        name="cook-assets",
        command=("python", "tools/cook.py", "assets/", "--out", "cooked/"),
        depends=(Path("assets/manifest.json"),),
    )
    model = make_model(
        name="build_language_demo", executables=(app,), commands=(gen,), custom_targets=(cook,)
    )
    text = emit_cmakelists(model, tool_version=FIXED_VERSION)
    assert text == (GOLDEN_DIR / "custom_commands.cmake").read_text(encoding="utf-8")
