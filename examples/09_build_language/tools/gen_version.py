"""Writes generated/version.cpp: the code-generation step project.add_command() runs.

Run by CMake through add_custom_command(), not directly; --out and --version
are supplied by cmakelessfile.py's project.add_command() call.
"""

from __future__ import annotations

import argparse
from pathlib import Path

_TEMPLATE = """\
#include "version.hpp"

auto build_language_demo_version() -> const char*
{{
    return "{version}";
}}
"""


def main() -> None:
    """Generate the version.cpp source at the requested output path."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="Output path for the generated .cpp file")
    parser.add_argument("--version", required=True, help="Version string to compile in")
    args = parser.parse_args()

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_TEMPLATE.format(version=args.version), encoding="utf-8")


if __name__ == "__main__":
    main()
