"""Shipping a real product: ABI-versioned library, components, RPATH, metadata.

'cmakeless install --prefix dist' lays out a tree that runs on a clean
machine (runtime DLLs bundled, relative RPATH), and 'cmakeless package'
produces archives that carry a vendor, a description, and a license.
"""

from cmakeless import Project

project = Project("mathx", version="1.2.0", cpp_std=20, warnings="strict")

lib = project.add_library(
    "mathx",
    sources=["src/mathx/*.cpp"],
    public_headers="include/",
    kind="shared",
    version="1.2.0",
    soversion="1",
)
lib.visibility = "hidden"

cli = project.add_executable("mathx-cli", sources=["src/main.cpp"])
cli.link(lib)

tests = project.add_test("mathx_tests", sources=["tests/*.cpp"], framework="none", timeout=30)
tests.labels = ["unit"]
tests.link(lib)

project.install(cli, component="runtime", rpath="relative", runtime_dependencies=True)
project.install(lib, headers=True, component="dev")
project.install_files("share/", destination="share/mathx", component="runtime")
project.export(cmake=True, pkg_config=True)
project.package(
    formats=["zip", "tgz"],
    vendor="Example Corp",
    description="A tiny shipped math library",
    license_file="share/LICENSE.txt",
)
project.build()
