"""clang-tidy output to findings, and findings to SARIF 2.1.0 for code scanning."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"

_DIAGNOSTIC = re.compile(
    r"""
    ^(?P<file>.+?):(?P<line>\d+):(?P<column>\d+):\s+
    (?P<level>warning|error):\s+
    (?P<message>.*?)
    (?:\s+\[(?P<check>[\w.,-]+)\])?$
    """,
    re.VERBOSE | re.MULTILINE,
)


@dataclass(frozen=True, slots=True)
class Finding:
    """One static-analysis diagnostic.

    Attributes:
        file: The file as the tool printed it.
        line: 1-based line.
        column: 1-based column.
        level: "warning" or "error".
        message: The diagnostic text.
        check: The check that produced it, for example "bugprone-use-after-move".
    """

    file: str
    line: int
    column: int
    level: str
    message: str
    check: str


def parse_clang_tidy(output: str) -> list[Finding]:
    """Extract every located diagnostic from clang-tidy's output.

    Args:
        output: clang-tidy's combined output.

    Returns:
        The findings, in output order, without duplicates (a header's
        diagnostic repeats for every translation unit that includes it).
    """
    findings: dict[tuple[str, int, int, str], Finding] = {}
    for match in _DIAGNOSTIC.finditer(output):
        finding = Finding(
            file=match["file"],
            line=int(match["line"]),
            column=int(match["column"]),
            level=match["level"],
            message=match["message"],
            check=match["check"] or "clang-diagnostic",
        )
        findings.setdefault((finding.file, finding.line, finding.column, finding.check), finding)
    return list(findings.values())


def to_sarif(findings: list[Finding], *, root: Path, tool_version: str) -> dict[str, Any]:
    """Render findings as one SARIF run that GitHub code scanning ingests.

    Args:
        findings: The findings to report.
        root: The project root; paths under it are reported relative to it.
        tool_version: The cmakeless version, recorded as the driver version.

    Returns:
        The SARIF document.
    """
    rules = sorted({finding.check for finding in findings})
    return {
        "$schema": _SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "clang-tidy (via cmakeless)",
                        "version": tool_version,
                        "rules": [{"id": rule} for rule in rules],
                    }
                },
                "results": [_result(finding, root) for finding in findings],
            }
        ],
    }


def _result(finding: Finding, root: Path) -> dict[str, Any]:
    """Render one finding as a SARIF result.

    Args:
        finding: The finding.
        root: The project root.

    Returns:
        The result object.
    """
    path = Path(finding.file)
    uri = path.relative_to(root).as_posix() if path.is_relative_to(root) else path.as_posix()
    return {
        "ruleId": finding.check,
        "level": finding.level,
        "message": {"text": finding.message},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": uri},
                    "region": {"startLine": finding.line, "startColumn": finding.column},
                }
            }
        ],
    }
