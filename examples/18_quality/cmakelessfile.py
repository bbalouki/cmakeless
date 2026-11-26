"""Quality as verbs: labeled tests, a fuzz target, asset cooking, compliance lint.

Try 'cmakeless test --label unit --junit report.xml', 'cmakeless coverage'
(with gcovr installed), 'cmakeless fuzz fuzz_parse --time 30' (Clang),
'cmakeless lint --report sarif -o lint.sarif', 'cmakeless profile', and
'cmakeless evidence' for an auditable bundle.
"""

import shutil
import sys

from cmakeless import Project, Rules

project = Project("quality", version="1.0.0", cpp_std=20, warnings="strict")

parser = project.add_library("parser", sources=["src/parser.cpp"], public_headers="src/")

tests = project.add_test("parser_tests", sources=["tests/*.cpp"], framework="none", timeout=30)
tests.labels = ["unit"]
tests.link(parser)

fuzz = project.add_fuzz_target("fuzz_parse", sources=["fuzz/fuzz_parse.cpp"])
fuzz.link(parser)

project.add_assets("assets", cook=[sys.executable, "tools/cook.py"], into="cooked")

if shutil.which("clang-tidy"):
    project.lint(clang_tidy=Rules.cert() | Rules.modern())

project.build()
