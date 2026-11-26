"""Ninja logs, Clang time traces, clang-tidy to SARIF, and CTest JUnit events."""

from __future__ import annotations

import json
from pathlib import Path

from cmakeless.driver.cmake_driver import read_junit
from cmakeless.driver.insight import chrome_trace, header_costs, read_ninja_log
from cmakeless.driver.sarif import parse_clang_tidy, to_sarif

NINJA_LOG = (
    "# ninja log v6\n"
    "0\t900\t0\told.obj\tdeadbeef\n"
    "0\t1500\t0\ta.obj\tcafe\n"
    "100\t400\t0\tb.obj\tbabe\n"
    "1500\t1800\t0\tapp.exe\tf00d\n"
)


def test_only_the_latest_build_is_read_from_the_ninja_log(tmp_path: Path) -> None:
    """A clock reset starts a new build; steps come out slowest first."""
    (tmp_path / ".ninja_log").write_text(
        "0\t5000\t0\tstale.obj\tx\n9000\t9100\t0\tz\tx\n" + NINJA_LOG[14:], encoding="utf-8"
    )
    steps = read_ninja_log(tmp_path)
    assert [step.output for step in steps] == ["a.obj", "old.obj", "b.obj", "app.exe"]
    assert steps[0].duration_ms == 1500


def test_parallel_steps_land_in_separate_trace_lanes(tmp_path: Path) -> None:
    """Overlapping steps never share a lane in the Chrome trace."""
    (tmp_path / ".ninja_log").write_text(NINJA_LOG, encoding="utf-8")
    events = chrome_trace(read_ninja_log(tmp_path))["traceEvents"]
    lanes = {event["name"]: event["tid"] for event in events}
    assert lanes["a.obj"] != lanes["b.obj"]


def test_header_costs_total_across_translation_units(tmp_path: Path) -> None:
    """The same header parsed by two TUs counts twice."""
    trace = {
        "traceEvents": [{"name": "Source", "dur": 2_500_000, "args": {"detail": "Eigen/Dense"}}]
    }
    for name in ("a.cpp.json", "b.cpp.json"):
        (tmp_path / name).write_text(json.dumps(trace), encoding="utf-8")
    (tmp_path / "other.json").write_text("[1, 2]", encoding="utf-8")
    costs = header_costs(tmp_path)
    assert (costs[0].header, costs[0].total_us, costs[0].count) == ("Eigen/Dense", 5_000_000, 2)


def test_clang_tidy_findings_are_parsed_once_and_rendered_as_sarif(tmp_path: Path) -> None:
    """A header diagnostic repeated per TU becomes one SARIF result."""
    source = tmp_path / "src" / "a.cpp"
    line = f"{source}:3:5: warning: use auto [modernize-use-auto]\n"
    findings = parse_clang_tidy(line + line + "noise\n")
    assert len(findings) == 1 and findings[0].check == "modernize-use-auto"
    sarif = to_sarif(findings, root=tmp_path, tool_version="1.1.0")
    result = sarif["runs"][0]["results"][0]
    assert result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "src/a.cpp"
    assert sarif["version"] == "2.1.0"


def test_junit_cases_become_test_finished_events(tmp_path: Path) -> None:
    """Passed, failed, and skipped cases are told apart."""
    report = tmp_path / "junit.xml"
    report.write_text(
        '<testsuite><testcase name="a" time="0.5"/>'
        '<testcase name="b" time="1"><failure/></testcase>'
        '<testcase name="c" status="notrun"/></testsuite>',
        encoding="utf-8",
    )
    events = read_junit(report)
    assert [(event.name, event.status) for event in events] == [
        ("a", "passed"),
        ("b", "failed"),
        ("c", "skipped"),
    ]
    assert read_junit(tmp_path / "missing.xml") == []
