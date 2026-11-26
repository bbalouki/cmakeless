"""Typed CPU targeting, so a binary never silently requires the build machine's CPU."""

from __future__ import annotations

import re

from cmakeless.errors import ConfigurationError
from cmakeless.model.properties import ARM_FLOAT_ABIS, X86_64_LEVELS, CpuFamily, CpuModel

# Core and FPU names are passed straight to -mcpu and -mfpu, so they are held
# to the shape GCC and Clang document: lowercase words joined by hyphens,
# dots, or plus-separated extensions.
_ARM_TOKEN = re.compile(r"^[a-z0-9][a-z0-9.+-]*$")


class Cpu:
    """A CPU target, assigned to target.cpu.

    Construct through the factories; each validates its arguments at the
    call site, the way When.compiler() does.
    """

    def __init__(self, model: CpuModel) -> None:
        """Wrap an already-validated CPU description.

        Args:
            model: The frozen description the factories produce.
        """
        self._model = model

    @classmethod
    def x86_64(cls, *, level: str = "v2") -> Cpu:
        """Target an x86-64 microarchitecture level.

        Args:
            level: "v1" (any x86-64), "v2" (SSE4.2, 2009+), "v3" (AVX2,
                2015+), or "v4" (AVX-512).

        Returns:
            The CPU target.

        Raises:
            ConfigurationError: When the level is unknown.
        """
        if level not in X86_64_LEVELS:
            levels = ", ".join(repr(known) for known in sorted(X86_64_LEVELS))
            raise ConfigurationError(f"Unknown x86-64 level {level!r}. Pick one of: {levels}.")
        return cls(CpuModel(family=CpuFamily.X86_64, level=level))

    @classmethod
    def arm(cls, *, core: str, fpu: str | None = None, float_abi: str | None = None) -> Cpu:
        """Target one ARM core, with optional FPU and float ABI.

        Args:
            core: The core name, for example "cortex-m7" or "neoverse-n1".
            fpu: The FPU, for example "fpv5-d16"; None for the core default.
            float_abi: "soft", "softfp", or "hard"; None for the default.

        Returns:
            The CPU target.

        Raises:
            ConfigurationError: When a name is malformed or the ABI unknown.
        """
        for label, value in (("core", core), ("fpu", fpu)):
            if value is not None and not _ARM_TOKEN.match(value):
                raise ConfigurationError(
                    f"Cpu.arm({label}={value!r}) is not a valid ARM {label} name, "
                    f'for example "cortex-m7" or "fpv5-d16".'
                )
        if float_abi is not None and float_abi not in ARM_FLOAT_ABIS:
            abis = ", ".join(repr(known) for known in sorted(ARM_FLOAT_ABIS))
            raise ConfigurationError(f"Unknown float_abi {float_abi!r}. Pick one of: {abis}.")
        return cls(CpuModel(family=CpuFamily.ARM, core=core, fpu=fpu, float_abi=float_abi))

    @classmethod
    def native(cls) -> Cpu:
        """Target whatever CPU runs the build; for local benchmarking only.

        A binary built this way can crash with an illegal instruction on an
        older machine, so installing such a target prints a warning.

        Returns:
            The CPU target.
        """
        return cls(CpuModel(family=CpuFamily.NATIVE))

    def __repr__(self) -> str:
        """Developer-facing representation.

        Returns:
            The family and its settings.
        """
        return f"Cpu({self._model!r})"

    def _freeze(self) -> CpuModel:
        """Hand the validated description to the model.

        Returns:
            The frozen CPU description.
        """
        return self._model
