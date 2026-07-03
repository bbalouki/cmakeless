"""Import the freshly built extension and check it works.

Run 'python build.py' (or 'cmakeless build') first; the module lands in the
current environment, so this plain import just works.
"""

import mymath

assert mymath.add(2, 3) == 5, "the C++ add() should sum its arguments"
print("mymath.add(2, 3) ==", mymath.add(2, 3))
