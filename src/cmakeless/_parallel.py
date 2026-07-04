# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Free-threaded helpers: detection and a small parallel-map primitive.

The immutable model layer is what makes parallelism safe here: frozen
dataclasses are shared across threads with no locks and no copies. On a
standard GIL build these helpers still work, degrading to interleaved I/O
concurrency, which is where most of the benefit lives anyway.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor


def gil_enabled() -> bool:
    """Report whether the running interpreter still holds the GIL.

    Returns:
        True on a standard build, False on a free-threaded interpreter;
        True as well on versions predating the detection hook.
    """
    is_enabled: Callable[[], bool] | None = getattr(sys, "_is_gil_enabled", None)
    if is_enabled is None:
        return True
    return is_enabled()


def parallel_map[T, R](function: Callable[[T], R], items: Sequence[T]) -> list[R]:
    """Apply a function to every item concurrently, preserving input order.

    Args:
        function: The work to run per item; must be thread-safe.
        items: The inputs; an empty sequence returns an empty list without
            starting a pool.

    Returns:
        The results in the same order as ``items``.
    """
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=len(items)) as pool:
        results: Iterable[R] = pool.map(function, items)
        return list(results)
