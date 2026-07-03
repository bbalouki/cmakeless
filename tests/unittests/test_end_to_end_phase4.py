"""End-to-end Phase 4 flows against the real CMake engine.

targets_info() only needs CMake; the Python-module build additionally fetches
a binding backend, so it is double-gated behind CMAKELESS_NETWORK_TESTS=1 the
same way the dependency end-to-end tests are.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
from pathlib import Path

import pytest

from cmakeless import Project

requires_cmake = pytest.mark.skipif(shutil.which("cmake") is None, reason="cmake is not on PATH")
requires_cmake_and_network = pytest.mark.skipif(
    shutil.which("cmake") is None or os.environ.get("CMAKELESS_NETWORK_TESTS") != "1",
    reason="needs cmake on PATH and CMAKELESS_NETWORK_TESTS=1",
)

BINDINGS_CPP = """\
#include <pybind11/pybind11.h>

[[nodiscard]] auto add(int first, int second) -> int
{
    return first + second;
}

PYBIND11_MODULE(mymath_e2e, module)
{
    module.def("add", &add);
}
"""


@requires_cmake
def test_targets_info_returns_configured_targets(tmp_path: Path) -> None:
    """Targets info returns configured targets."""
    (tmp_path / "src").mkdir()
    main = tmp_path / "src" / "main.cpp"
    main.write_text("auto main() -> int { return 0; }\n", encoding="utf-8")
    project = Project("hello", version="1.0.0", cpp_std=20, root=tmp_path)
    project.add_executable("hello", sources=["src/main.cpp"])
    infos = project.targets_info()
    hello = next(info for info in infos if info.name == "hello")
    assert hello.type == "EXECUTABLE"
    assert any(source.name == "main.cpp" for source in hello.sources)


@requires_cmake_and_network
def test_python_module_builds_and_imports(tmp_path: Path) -> None:
    """Python module builds and imports."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "bindings.cpp").write_text(BINDINGS_CPP, encoding="utf-8")
    project = Project("mymath_e2e_demo", version="1.0.0", cpp_std=17, root=tmp_path)
    # install=False keeps the artifact in the build tree, out of site-packages.
    project.add_python_module(
        "mymath_e2e", sources=["src/bindings.cpp"], binding="pybind11", install=False
    )
    project.build()
    module = _import_from_build(tmp_path / "build", "mymath_e2e")
    assert module.add(2, 3) == 5


def _import_from_build(build_dir: Path, name: str) -> object:
    """Import a freshly built extension straight from the build tree.

    Args:
        build_dir: The build directory to search for the artifact.
        name: The module name.

    Returns:
        The imported module object.
    """
    suffixes = (".pyd", ".so", ".dylib")
    artifacts = [path for path in build_dir.rglob(f"{name}.*") if path.suffix in suffixes]
    assert artifacts, f"no built {name} extension under {build_dir}"
    spec = importlib.util.spec_from_file_location(name, artifacts[0])
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
