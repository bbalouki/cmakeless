# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Rewrite docs/benchmarks.md's `_to fill_` cells from benchmarks.yml JSON results.

Each result file's name encodes which table row it belongs to
(`<benchmark>__<os>__<python-version>.json`); its JSON body has the actual
numbers. Only cells that are still `_to fill_` are touched, so the
hand-verified Windows/CPython 3.13 rows (sourced from a real local run, not
CI) are never overwritten by an automated run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_TABLE_PATH = Path(__file__).resolve().parents[1] / "docs" / "benchmarks.md"
_BENCHMARK_LABELS = {
    "resolution": "Resolution (16 pkgs)",
    "presets": "Multi-preset configure (6)",
}
_OS_LABELS = {"ubuntu-latest": "Linux", "windows-latest": "Windows", "macos-latest": "macOS"}


def _parse_result_filename(path: Path) -> tuple[str, str, str]:
    """Split a `<benchmark>__<os>__<python-version>.json` filename into its parts."""
    benchmark, os_name, python_version = path.stem.split("__")
    return benchmark, os_name, python_version


def _row_labels(
    benchmark: str, os_name: str, gil_enabled: bool, python_version: str
) -> tuple[str, str, str] | None:
    """Compute the (benchmark, OS, interpreter) labels identifying a table row.

    Returns None for a result with no corresponding row: the table has a
    single "any"/CPython 3.14t row, sourced only from the ubuntu-latest
    matrix cell.
    """
    benchmark_label = _BENCHMARK_LABELS[benchmark]
    if not gil_enabled:
        return (benchmark_label, "any", "CPython 3.14t") if os_name == "ubuntu-latest" else None
    return benchmark_label, _OS_LABELS[os_name], f"CPython {python_version}"


def _matches_row(cells: list[str], labels: tuple[str, str, str]) -> bool:
    """Check whether a table row's first three cells match the target labels."""
    return len(cells) >= 3 and tuple(cells[:3]) == labels


def _fill_row(line: str, serial: float, parallel: float, speedup: float) -> str:
    """Replace a row's three `_to fill_` cells, in order, with formatted numbers."""
    line = line.replace("_to fill_", f"{serial:.3f}s", 1)
    line = line.replace("_to fill_", f"{parallel:.3f}s", 1)
    return line.replace("_to fill_", f"{speedup:.2f}x", 1)


def update_table(results_dir: Path) -> bool:
    """Rewrite docs/benchmarks.md in place from every JSON result under results_dir.

    Args:
        results_dir: Directory containing `<benchmark>__<os>__<version>.json` files.

    Returns:
        True if any table row changed.
    """
    lines = _TABLE_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    changed = False
    for result_path in sorted(results_dir.glob("*.json")):
        benchmark, os_name, python_version = _parse_result_filename(result_path)
        result = json.loads(result_path.read_text(encoding="utf-8"))
        labels = _row_labels(benchmark, os_name, result["gil_enabled"], python_version)
        if labels is None:
            continue
        for index, line in enumerate(lines):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if "_to fill_" in line and _matches_row(cells, labels):
                lines[index] = _fill_row(
                    line, result["serial_seconds"], result["parallel_seconds"], result["speedup"]
                )
                changed = True
                break
    if changed:
        _TABLE_PATH.write_text("".join(lines), encoding="utf-8")
    return changed


if __name__ == "__main__":
    if update_table(Path(sys.argv[1])):
        print("docs/benchmarks.md updated.")
    else:
        print("No _to fill_ cells matched; docs/benchmarks.md unchanged.")
