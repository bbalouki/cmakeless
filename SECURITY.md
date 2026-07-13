# Security Policy

## Supported Versions

CMakeless is pre-1.0 (currently in the `0.5.x` beta line, see
[ROADMAP](docs/ROADMAP.md)). Per the versioning policy already stated in
[CONTRIBUTING](CONTRIBUTING.md), backward compatibility is not guaranteed
before 1.0, and there is no long-term-support window for any pre-1.0 minor
line: only the latest released version receives security fixes.

| Version | Supported                   |
| ------- | --------------------------- |
| 0.5.x   | :white_check_mark: (latest) |
| < 0.5.0 | :x:                         |

Once CMakeless reaches 1.0, this table will be revised to reflect a real
support window across minor releases, per Semantic Versioning.

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Instead, email **bbsimyeli@gmail.com** with:

- A description of the vulnerability and its potential impact.
- Steps to reproduce it (a minimal `cmakelessfile.py`, if applicable, for
  example if the issue involves the driver layer shelling out to `cmake`,
  or unsafe handling of dependency sources).
- Any suggested fix or mitigation, if you have one.

You should expect an acknowledgement within **5 business days**
(best-effort; this project currently has a single maintainer, this window
is a placeholder and may be revised as the project grows). We will work
with you to understand and validate the issue, and to agree on a disclosure
timeline once a fix is available.

## Scope

CMakeless generates `CMakeLists.txt` and drives `cmake`/`ctest`/`cpack` as
subprocesses; it does not execute untrusted network input on its own. Of
particular interest are:

- Anything that could cause CMakeless to emit unsafe or attacker-controlled
  CMake code from a trusted `cmakelessfile.py` input.
- Unsafe handling of dependency resolution (vcpkg/Conan/URL sources) that
  could lead to fetching or executing unintended code.
- Path traversal or injection issues in generated build files.

Issues in CMake itself, or in third-party dependencies it fetches, should be
reported upstream to those projects.
