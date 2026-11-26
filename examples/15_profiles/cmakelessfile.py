"""Industry profiles and typed CPU targeting.

The project is hardened and reproducible; the pricing engine replaces that
with a low-latency profile of its own. The CPU level is chosen in plain
Python, so the same description never emits an x86 flag on an ARM machine.
"""

import platform

from cmakeless import Cpu, Profile, Project

project = Project(
    "profiles",
    version="1.0.0",
    cpp_std=20,
    warnings="strict",
    profile=Profile.hardened() | Profile.reproducible(),
)

pricer = project.add_executable("pricer", sources=["src/pricer.cpp"])
pricer.profile = Profile.low_latency() | Profile.hardened()
if platform.machine().lower() in ("x86_64", "amd64"):
    pricer.cpu = Cpu.x86_64(level="v2")

service = project.add_executable("service", sources=["src/service.cpp"])
service.map_file = True

project.build()
