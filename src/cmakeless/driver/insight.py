"""Where build time goes: Ninja's own log and Clang's -ftime-trace files.

Both are files the build already writes, so profiling needs no compiler
wrapper: any compiler under Ninja yields per-step times, and Clang adds a
per-header breakdown.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

NINJA_LOG_NAME = ".ninja_log"
_NINJA_FIELDS = 5
_MICROSECONDS_PER_MILLISECOND = 1000


@dataclass(frozen=True, slots=True)
class StepTime:
    """One build step's wall-clock span, as Ninja recorded it.

    Attributes:
        output: The file the step produced.
        start_ms: Milliseconds from the start of the build.
        end_ms: Milliseconds from the start of the build.
    """

    output: str
    start_ms: int
    end_ms: int

    @property
    def duration_ms(self) -> int:
        """The step's duration in milliseconds."""
        return self.end_ms - self.start_ms


@dataclass(frozen=True, slots=True)
class HeaderCost:
    """The total time spent parsing one header across every translation unit.

    Attributes:
        header: The header path Clang reported.
        total_us: Total microseconds across all inclusions.
        count: How many translation units parsed it.
    """

    header: str
    total_us: int
    count: int


def read_ninja_log(build_dir: Path) -> list[StepTime]:
    """Read the latest build's steps from Ninja's log.

    Ninja appends to the log across builds and restarts its clock each
    time, so only the entries after the last clock reset belong to the
    most recent build.

    Args:
        build_dir: The build tree Ninja ran in.

    Returns:
        The steps of the latest build, slowest first; empty without a log.
    """
    log = build_dir / NINJA_LOG_NAME
    if not log.is_file():
        return []
    latest: dict[str, StepTime] = {}
    previous_start = -1
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.split("\t")
        if line.startswith("#") or len(fields) < _NINJA_FIELDS:
            continue
        start, end, output = int(fields[0]), int(fields[1]), fields[3]
        if start < previous_start:
            latest = {}
        previous_start = start
        latest[output] = StepTime(output=output, start_ms=start, end_ms=end)
    return sorted(latest.values(), key=lambda step: step.duration_ms, reverse=True)


def header_costs(build_dir: Path) -> list[HeaderCost]:
    """Total the per-header parse time from every Clang time-trace file.

    Args:
        build_dir: The build tree compiled with -ftime-trace.

    Returns:
        Headers by total parse time, most expensive first.
    """
    totals: dict[str, int] = defaultdict(int)
    counts: dict[str, int] = defaultdict(int)
    for trace in build_dir.rglob("*.json"):
        for event in _trace_events(trace):
            if event.get("name") == "Source" and "dur" in event:
                header = str(event.get("args", {}).get("detail", "?"))
                totals[header] += int(event["dur"])
                counts[header] += 1
    costs = [HeaderCost(header, totals[header], counts[header]) for header in totals]
    return sorted(costs, key=lambda cost: cost.total_us, reverse=True)


def _trace_events(path: Path) -> list[dict[str, Any]]:
    """Load the events of one file if it is a Chrome trace, else nothing.

    Args:
        path: A JSON file under the build tree.

    Returns:
        Its traceEvents, or an empty list for any other JSON file.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    if not isinstance(document, dict):
        return []
    events = document.get("traceEvents")
    return (
        [event for event in events if isinstance(event, dict)] if isinstance(events, list) else []
    )


def chrome_trace(steps: list[StepTime]) -> dict[str, Any]:
    """Render build steps as a Chrome trace, viewable in Perfetto.

    Steps are packed into lanes so overlapping (parallel) steps never share
    one, which is how the trace viewer shows real build parallelism.

    Args:
        steps: The build steps.

    Returns:
        The trace document.
    """
    lane_ends: list[int] = []
    events = []
    for step in sorted(steps, key=lambda candidate: candidate.start_ms):
        lane = next((i for i, end in enumerate(lane_ends) if end <= step.start_ms), len(lane_ends))
        if lane == len(lane_ends):
            lane_ends.append(step.end_ms)
        else:
            lane_ends[lane] = step.end_ms
        events.append(
            {
                "name": step.output,
                "ph": "X",
                "ts": step.start_ms * _MICROSECONDS_PER_MILLISECOND,
                "dur": step.duration_ms * _MICROSECONDS_PER_MILLISECOND,
                "pid": 0,
                "tid": lane,
            }
        )
    return {"traceEvents": events, "displayTimeUnit": "ms"}
