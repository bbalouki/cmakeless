"""Post-install code signing, with credentials only ever read from the environment."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from cmakeless.errors import ConfigurationError

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class WindowsSigning:
    """signtool settings: which environment variable names the certificate.

    Attributes:
        cert_env: The environment variable holding the certificate path.
        timestamp_url: The RFC 3161 timestamp server.
    """

    cert_env: str
    timestamp_url: str


@dataclass(frozen=True, slots=True)
class MacSigning:
    """codesign settings: which environment variable names the identity.

    Attributes:
        identity_env: The environment variable holding the signing identity.
    """

    identity_env: str


class Signing:
    """Factories for project.sign(windows=..., macos=...)."""

    @staticmethod
    def signtool(
        *, cert_env: str, timestamp: str = "http://timestamp.digicert.com"
    ) -> WindowsSigning:
        """Sign installed .exe and .dll files with signtool.

        Args:
            cert_env: The environment variable holding the certificate path.
            timestamp: The RFC 3161 timestamp server URL.

        Returns:
            The Windows signing settings.

        Raises:
            ConfigurationError: When cert_env is not a variable name or the
                timestamp server is not an http(s) URL.
        """
        _check_env_name(cert_env, "Signing.signtool(cert_env=...)")
        if urlsplit(timestamp).scheme not in ("http", "https"):
            raise ConfigurationError(
                f"Signing.signtool(timestamp={timestamp!r}) must be an http(s) URL."
            )
        return WindowsSigning(cert_env=cert_env, timestamp_url=timestamp)

    @staticmethod
    def codesign(*, identity_env: str) -> MacSigning:
        """Sign installed binaries and dylibs with codesign, hardened runtime on.

        Args:
            identity_env: The environment variable holding the identity.

        Returns:
            The macOS signing settings.

        Raises:
            ConfigurationError: When identity_env is not a variable name.
        """
        _check_env_name(identity_env, "Signing.codesign(identity_env=...)")
        return MacSigning(identity_env=identity_env)


def _check_env_name(name: str, where: str) -> None:
    """Refuse anything that is not an environment variable name.

    The name is written into a generated script, so it is held to the
    identifier shape that can never inject CMake code.

    Args:
        name: The proposed variable name.
        where: The call that received it, for the message.

    Raises:
        ConfigurationError: When the name is not an identifier.
    """
    if not _ENV_NAME.match(name):
        raise ConfigurationError(
            f"{where} got {name!r}; pass the name of an environment variable, for "
            f"example WIN_CERT, never the secret itself."
        )
