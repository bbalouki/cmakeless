"""Compiler caches with shared backends, configured in Python.

Only the launcher and its environment are configured here; the cache servers
(S3 buckets, Redis, GCS) stay the user's own infrastructure.
"""

from __future__ import annotations

import re

from cmakeless.errors import ConfigurationError
from cmakeless.model.properties import CacheModel

# sccache's remote backends, by name, mapped to the environment variable
# naming the bucket or endpoint; values come from the user's environment.
_SCCACHE_BACKENDS: dict[str, str] = {
    "s3": "SCCACHE_BUCKET",
    "gcs": "SCCACHE_GCS_BUCKET",
    "azure": "SCCACHE_AZURE_BLOB_CONTAINER",
    "redis": "SCCACHE_REDIS",
    "local": "SCCACHE_DIR",
}

_SIZE = re.compile(r"^[0-9]+(\.[0-9]+)?[KMGT]$")
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class Cache:
    """A compiler cache, assigned to project.cache."""

    def __init__(self, model: CacheModel) -> None:
        """Wrap an already-validated cache description.

        Args:
            model: The frozen description the factories produce.
        """
        self._model = model

    @classmethod
    def ccache(cls, *, remote: str | None = None, max_size: str | None = None) -> Cache:
        """Use ccache, optionally sharing results through a remote storage URL.

        Args:
            remote: A ccache remote_storage URL, for example
                "redis://cache.internal:6379"; None keeps the cache local.
            max_size: The local cache size limit, for example "20G".

        Returns:
            The cache configuration.

        Raises:
            ConfigurationError: When max_size is not a size like "20G".
        """
        env: list[tuple[str, str]] = []
        if remote is not None:
            env.append(("CCACHE_REMOTE_STORAGE", remote))
        if max_size is not None:
            if not _SIZE.match(max_size):
                raise ConfigurationError(
                    f'Cache.ccache(max_size={max_size!r}) must look like "500M" or "20G".'
                )
            env.append(("CCACHE_MAXSIZE", max_size))
        return cls(CacheModel(tool="ccache", env=tuple(sorted(env))))

    @classmethod
    def sccache(cls, *, backend: str = "local", bucket_env: str | None = None) -> Cache:
        """Use sccache with one of its storage backends.

        Args:
            backend: "local", "s3", "gcs", "azure", or "redis".
            bucket_env: The environment variable holding the bucket or
                endpoint; credentials themselves are never written anywhere.

        Returns:
            The cache configuration.

        Raises:
            ConfigurationError: When the backend is unknown or bucket_env is
                not a valid variable name.
        """
        if backend not in _SCCACHE_BACKENDS:
            known = ", ".join(repr(name) for name in sorted(_SCCACHE_BACKENDS))
            raise ConfigurationError(f"Unknown sccache backend {backend!r}. Pick one of: {known}.")
        if bucket_env is not None and not _ENV_NAME.match(bucket_env):
            raise ConfigurationError(
                f"Cache.sccache(bucket_env={bucket_env!r}) must be an environment "
                f"variable name, for example SCCACHE_BUCKET."
            )
        return cls(CacheModel(tool="sccache", env=_sccache_env(backend, bucket_env)))

    @property
    def tool(self) -> str:
        """The cache executable: "ccache" or "sccache"."""
        return self._model.tool

    def __repr__(self) -> str:
        """Developer-facing representation.

        Returns:
            The tool and its environment variable names (never their values
            when those come from the environment).
        """
        return f"Cache({self._model.tool}, env={[name for name, _ in self._model.env]})"

    def _freeze(self) -> CacheModel:
        """Hand the cache description to the model.

        Returns:
            The frozen cache configuration.
        """
        return self._model


def _sccache_env(backend: str, bucket_env: str | None) -> tuple[tuple[str, str], ...]:
    """Map an sccache backend onto the variables sccache itself reads.

    The bucket is passed by reference: the value is read from the user's
    environment at build time, so nothing secret lands in generated files.

    Args:
        backend: The validated backend name.
        bucket_env: The user's variable holding the bucket, or None.

    Returns:
        Sorted (name, value) pairs; a value of "$NAME" means "copy from NAME".
    """
    if backend == "local" or bucket_env is None:
        return ()
    return ((_SCCACHE_BACKENDS[backend], f"${bucket_env}"),)
