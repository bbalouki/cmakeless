"""Import the freshly built extension and exercise the C++ Vec2 type.

Run 'python cmakelessfile.py' (or 'cmakeless build') first; the module lands in the
current environment, so this plain import just works.
"""

import math

import geometry

# Properties and methods come straight from the C++ class.
right_triangle = geometry.Vec2(3.0, 4.0)
assert right_triangle.x == 3.0
assert right_triangle.length() == 5.0

# Operators are bound too: arithmetic returns new Vec2 values.
assert geometry.Vec2(1.0, 2.0) + geometry.Vec2(3.0, 4.0) == geometry.Vec2(4.0, 6.0)
assert (geometry.Vec2(1.0, 0.0) * 2.0) == geometry.Vec2(2.0, 0.0)
assert math.isclose(right_triangle.normalized().length(), 1.0)

# A C++ std::domain_error surfaces in Python as a normal ValueError.
try:
    geometry.Vec2(0.0, 0.0).normalized()
except ValueError as error:
    print("normalizing a zero vector raised ValueError:", error)
else:  # pragma: no cover - the call above must raise
    raise AssertionError("normalizing a zero vector should raise ValueError")

print("geometry.Vec2(3, 4) =>", repr(right_triangle), "length", right_triangle.length())
