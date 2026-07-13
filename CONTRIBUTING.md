# Contributing to CMakeless

## Why Your Hands Are Needed Here

Think about the tools you used today without thinking. The compiler that turned your intent into machine code. The version control that let you experiment without fear. The editor that completed your thought halfway through typing it. Every one of them was, once, somebody's evenings. Somebody who was annoyed enough, and generous enough, to fix a problem for everyone instead of just for themselves.

That is the deal we all inherited: every generation of programmers builds the tools the next generation gets to take for granted. Someone absorbed the pain of linkers so you could ignore them. Someone tamed dependency hell in a dozen ecosystems so that `install` could be one word.

In C++, one tax remains stubbornly unpaid. Every C++ developer alive has lost hours, days, honest weeks of their one finite life to build scripts. Not to hard problems, not to interesting problems: to quoting rules, to scope leaks, to a language nobody chose and everybody endures. Multiply those hours by millions of developers and you are looking at one of the largest silent losses of creative energy in software.

CMakeless is an attempt to end that tax, not by conquering CMake but by making peace with it: keep the engine the whole world already agreed on, retire the language everyone already resents (the full argument is in [INTRODUCTION](docs/INTRODUCTION.md)). It is a small idea with enormous leverage. And leverage is the point: an hour you invest here is not an hour of work, it is an hour multiplied by every developer who never again has to learn what `PARENT_SCOPE` means.

## You Already Qualify

Here is the thing about this project: **your suffering is your resume.**

Have you ever stared at a CMake error at midnight? Then you know exactly what a good error message would have said, and our error messages need you. Have you ever spent a day integrating a dependency? Then you know what `depends()` must feel like to be worth it. Have you ever taught CMake to a junior and watched the light in their eyes dim? Then you know precisely which cliff our documentation must build stairs over.

There is no gatekeeping here about build-system expertise. The expertise this project runs on is _pain, accurately remembered._ Bring yours.

## The Contribution Ladder

Start wherever your energy is, every rung matters:

1. **Tell us where it hurts.** Open an issue describing a real CMake scenario that burned you, with the CMakeLists fragment if you have it. Each one becomes a test case and a design input. This is genuinely valuable and takes fifteen minutes.
2. **Try it and complain.** Build something small with CMakeless and report every moment of friction. A confused new user's honest transcript is worth more than a patch.
3. **Write an example.** Add a project under `examples/` (a game, a CLI tool, a library with bindings). Examples are how future users learn and how we catch API awkwardness early.
4. **Improve an error message.** Find an exception that fails our rule (every message must say what went wrong, where, and what to try next) and fix it. Small diff, outsized kindness.
5. **Teach the emitter a trick.** Pick a CMake construct we generate suboptimally and make the output more idiomatic. The Visitor structure ([ARCHITECTURE](docs/ARCHITECTURE.md#design-patterns-named)) keeps these changes local.
6. **Build an adapter.** A dependency provider (vcpkg, Conan), a test framework integration, a toolchain helper. The Strategy interfaces are designed to make this a contained, satisfying project.
7. **Take a roadmap item.** Phase items in [ROADMAP](docs/ROADMAP.md) are deliberately scoped to be ownable by one motivated person.

## The Values That Decide Arguments

When reviews disagree, these principles win, in this order:

1. **The user's `cmakelessfile.py` is sacred ground.** Every public class, method, and argument must justify its existence against the question: _does this make the common case simpler?_ We would rather lack a feature than grow a confusing one. Deleting from the public API is the most prestigious kind of contribution.
2. **Errors are a feature, not an apology.** We compete with CMake primarily on how it feels to fail. Any change that makes failure less clear is a regression, even if it makes success faster.
3. **Generated CMake is our face.** It must read like an expert wrote it by hand. If you would be embarrassed to commit the output to your own repository, it is not done.
4. **Delegate, never reimplement.** If CMake can do it, we drive CMake to do it. Cleverness that duplicates the engine is complexity we will pay interest on forever.
5. **Boring is the goal.** The highest compliment this project can receive is a user forgetting it exists.

## The Practical Part

**Setup:**

```console
$ git clone https://github.com/bbalouki/cmakeless
$ cd cmakeless
$ python -m venv .venv && .venv/Scripts/activate    # or bin/activate on POSIX
$ pip install -e ".[dev]"
$ pytest
```

You need Python 3.13+ (3.14 free-threaded to exercise the parallel paths) and CMake 3.25+ on PATH for the driver tests; everything above the driver layer runs without CMake installed.

**Code standards:**

- Type hints on everything; the package ships `py.typed` and CI runs mypy strict.
- Formatting and linting via ruff; CI enforces, so run it locally and forget about style debates forever.
- Tests live in `tests/unittests/`, mirroring `src/`. Use real implementations; mock only true externals (network, subprocess). Emitter changes come with golden-file tests; deterministic inputs only.
- Comments explain the _why_, as complete sentences. Well-named code covers the _what_.
- Public API changes require a matching documentation change and a `CHANGELOG.md` entry in the same PR.

**PR flow:**

1. Open or claim an issue first for anything larger than a typo, so nobody duplicates work.
2. Branch, commit in reviewable slices, and write commit messages that explain _why_.
3. CI must be green on Windows, Linux, and macOS. The build tool for a cross-platform language does not get to have a favorite platform.
4. One approving review merges it. Reviews here critique code, never people.

**Versioning:** Semantic Versioning 2.0.0. A breaking change is any backward-incompatible change to the public API, including the generated file formats and CLI. Deprecate with a warning and a migration path before removing.

**Conduct:** we follow the [Contributor Covenant](https://www.contributor-covenant.org/). The short version: the mission is to remove frustration from this ecosystem, starting with how we treat each other.

## A Closing Thought

There is a particular joy in tool-making that application work rarely offers: your users are your own people. When you improve CMakeless you are reaching back to help the next developer at 11 PM, staring at a build error, and handing them their evening back. Thousands of times. For years. Long after you have moved on.

The compiler devs gave you that gift. The git devs gave you that gift. The debugger devs gave you that gift.

Your turn.
