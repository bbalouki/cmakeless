# Security Policy

## Supported Versions

CMakeless follows Semantic Versioning, and the 1.x line is the long-term
line regulated users can standardize on.

| Version | Supported                                                  |
| ------- | ---------------------------------------------------------- |
| 1.1.x   | :white_check_mark: (latest; every fix lands here)          |
| 1.0.x   | :white_check_mark: security fixes until 1.1 has been out 6 months |
| < 1.0   | :x:                                                        |

**Long-term support.** When 2.0 ships, the last 1.x minor release keeps
receiving security fixes for 24 months, so a team that certified its build
on 1.x is never forced onto a new major version mid-program.

## Release Integrity

- Releases are published to PyPI through trusted publishing (OIDC, no
  long-lived API token), with the PEP 740 attestations the publishing action
  generates.
- Every GitHub Action in CI is pinned to a full commit SHA, and Dependabot
  proposes updates for a human to review.
- The `Security` workflow runs `pip-audit` over the installed dependency set
  and `bandit` over the package on every change and weekly.
- CMakeless itself has one runtime dependency (Typer, CLI only); importing
  `cmakeless` in a build description pulls in nothing but the standard
  library.

## Supply-Chain Features for Your Own Builds

`Project(supply_chain="strict")` refuses trust-on-first-use pins, plain-HTTP
archives, and system packages you have not allowed; `cmakeless audit` shows
how every pin was obtained; `cmakeless sbom` and `cmakeless evidence` write
reproducible bills of materials and SLSA provenance. See the cookbook's
"Supply Chain and Evidence" recipes.

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
- Anything that lets a credential named only by environment variable (signing,
  cache backends) end up written into a generated file or a log.
- A way to bypass `supply_chain="strict"`.

Issues in CMake itself, or in third-party dependencies it fetches, should be
reported upstream to those projects.
