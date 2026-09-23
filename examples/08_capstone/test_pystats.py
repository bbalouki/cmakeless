"""Import the freshly built pystats extension and check it against the CLI math.

Run 'cmakeless build' first; the module is copied into the current environment,
so this plain import works.
"""

import pystats

series = pystats.Series([3.0, 1.0, 4.0, 1.0, 5.0, 9.0, 2.0, 6.0])
assert series.count() == 8
assert series.mean() == 3.875
assert series.minimum() == 1.0
assert series.maximum() == 9.0

# An empty series is rejected in C++ and surfaces as a Python ValueError.
try:
    pystats.Series([])
except ValueError as error:
    print("empty series raised ValueError:", error)
else:  # pragma: no cover - the call above must raise
    raise AssertionError("an empty series should raise ValueError")

print("pystats summary:", series.summary())
