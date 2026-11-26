# Governance

CMakeless aims to be infrastructure that companies can bet products on, so
how decisions are made is written down rather than implied.

## Roles

- **Maintainers** merge changes, cut releases, and own the stability
  promise. They are listed in `.github/CODEOWNERS`. Today there is one; the
  project is actively recruiting co-maintainers, because a single maintainer
  is a risk every adopter rightly asks about.
- **Contributors** are everyone who opens an issue, a pull request, an RFC,
  or a review. See CONTRIBUTING.md.

## Decisions

- **Everyday changes** (fixes, docs, internal refactors, new registry
  entries) need one approving maintainer review and green CI.
- **Public API, CLI, or generated-format changes** need an RFC in
  `docs/rfcs/` that has been open for comment for at least seven days.
- **Breaking changes** need an RFC, a deprecation that has shipped for at
  least one minor release, and a major version (see docs/stability.md).
- Disagreements are settled by the values in CONTRIBUTING.md, in order. If
  that still does not settle it, the maintainers decide and record why in
  the RFC.

## Becoming a Maintainer

A contributor with a sustained record of careful reviews and merged work is
invited by the existing maintainers. Maintainers who step back keep their
place in the history and lose only merge rights.

## Releases and Support

Releases follow Semantic Versioning; the support windows, including the
long-term 1.x line, are in SECURITY.md.
