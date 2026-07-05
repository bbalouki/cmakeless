# CMakeless: Write Your C++ Builds in Python. Keep CMake. Lose the Pain.

> _"CMake gets the job done. Nobody said you have to enjoy it."_
> Every C++ developer, at some point, silently.

## The 11 PM Ritual

You know this moment. Everyone who writes C++ knows this moment.

It is 11 PM. Your code compiles. Your tests pass. You are done, except for one thing: the build. You open `CMakeLists.txt`, a file you copied from another project, which was copied from another project, which was copied from a Stack Overflow answer written in 2012 that starts with `cmake_minimum_required(VERSION 2.8)`.

You need to add one library. One. You type something plausible. You run CMake. It fails with an error message pointing at a line that looks perfectly fine. You quote a variable. Different error. You unquote it. The error disappears, but now your executable links against nothing and fails at runtime instead. You search the web. The top three answers contradict each other, and each one belongs to a different decade of CMake history.

At 1 AM it finally works. You do not know why. You are afraid to touch it. You commit it with the message `fix build` and you promise yourself never to open that file again.

That fear, the learned helplessness in front of your own build script, is not a personal failure. It is a design failure. And it is the problem CMakeless exists to solve.

## The Problem Has a Name: The CMake Language

Let us be honest and precise, because CMake deserves both.

The CMake _engine_ is a marvel. It configures builds for every compiler, every platform, every IDE that matters. It is the de facto standard of the C++ world, the thing vcpkg, Conan, CLion, Visual Studio, and thousands of libraries all agree on. Nobody sane wants to rebuild that.

The CMake _language_ is another story. It is the single most criticized part of the C++ toolchain, and the complaints have been remarkably consistent for over a decade:

**Everything is a string.** There are no integers, no booleans, no real lists. A "list" is a string with semicolons in it, which means `"a b c"` and `a b c` are entirely different things when passed to a function, and you discover the difference at configure time, or worse, at link time. The community has produced [entire articles just about when to quote a variable](https://crascit.com/2022/01/25/quoting-in-cmake/), and the [official documentation itself warns about legacy quoting behavior](https://cmake.org/cmake/help/latest/manual/cmake-language.7.html) that exists only for backward compatibility.

**Scoping is a trap.** Variables have dynamic scope. They flow down into functions and subdirectories but not back up, unless you use `PARENT_SCOPE`, and functions cannot simply return a value; they set magic prefixed variables in the caller's scope instead. As one widely shared critique put it, the language design "seems like a workaround introduced already at the design stage" ([Why CMake Sucks](https://twdev.blog/2021/08/cmake/), and the discussions it sparked on [Hacker News](https://news.ycombinator.com/item?id=34964152) and [Lobsters](https://lobste.rs/s/i2qnqj/why_cmake_sucks_2021)).

**The syntax cannot be memorized.** Is it `target_link_libraries(app PRIVATE fmt)` or `target_link_libraries(app fmt)`? When do you need `PUBLIC`, `PRIVATE`, `INTERFACE`? Why does `if(VAR)` dereference the variable but `if(${VAR})` sometimes double-dereferences it? Developers with fifteen years of experience still keep the documentation open in a permanent tab. That is not a learning curve. That is a learning cliff with no top.

**You cannot debug it.** There is no breakpoint. There is no inspector. There is `message(STATUS "WHY ARE YOU LIKE THIS: ${VAR}")` sprinkled through your build files like archaeological evidence of past suffering.

**Twenty years of legacy never dies.** Every historical mistake lives on behind a policy flag (`CMP0077`, anyone?). Every tutorial you find teaches a different era of CMake. "Modern CMake" is a genuinely good set of ideas that most projects have never adopted, because the old way still works and the old examples still rank first in search results.

None of this is controversial. It is the recurring theme of conference talks, blog posts, and forum threads year after year. People do not use CMake because they like it. People use CMake because [they feel they have no choice](https://www.incredibuild.com/blog/can-you-make-it-better-exploring-the-cmake-debate).

CMakeless gives you the choice.

## The Idea: Replace the Language, Keep the Engine

Every previous attempt to fix this pain tried to replace CMake entirely. Meson, xmake, premake, Bazel: all capable tools, and all of them ask you to walk away from the largest build ecosystem in C++. That price is why they remain the exception, not the rule.

CMakeless takes the opposite bet:

**CMake is not the enemy. Writing CMake is.**

CMakeless is a pure Python frontend for CMake. You describe your build in real Python, a language with real types, real scoping, real functions, a real debugger, and a real IDE experience. CMakeless validates your description, generates clean, modern, human-readable CMake from it, and drives the CMake engine for you. Every generator, every toolchain, every IDE, and every library that works with CMake keeps working, because underneath, it _is_ CMake.

The name is the promise. Like serverless, where the servers never went away, CMakeless still has CMake at its core. You just never write it again.

Here is what that feels like:

```python
# cmakelessfile.py
from cmakeless import Project

project = Project("mygame", version="1.0.0", cpp_std=23)

engine = project.add_library(
    "engine",
    sources=["src/engine/*.cpp"],
    public_headers="include/",
)

app = project.add_executable("mygame", sources=["src/main.cpp"])
app.link(engine)
app.depends("fmt/10.2.1")

project.build()
```

Then:

```console
$ python cmakelessfile.py
```

That is the whole thing. No `PARENT_SCOPE`. No semicolons pretending to be lists. No guessing whether a variable needs quotes. If you make a mistake, you get a Python exception with a real message and a real stack trace, at the moment you make it, not a cryptic configure-time failure three layers deep in someone else's module.

## Why Python, Specifically

Because C++ and Python are already best friends, and have been for years.

- **Your team already knows it.** Python is the second language of nearly every C++ developer: it runs your test scripts, your code generators, your CI glue. There is nothing new to learn.
- **The interop story is already written.** pybind11 and nanobind have made Python bindings a standard part of serious C++ projects. A Python-native build frontend makes `add_python_module("core")` a one-liner (pybind11 by default, nanobind on request) instead of a page of ritual.
- **Real tooling, for free.** Autocomplete on every function. Type checking on every argument. `breakpoint()` inside your build script. Unit tests for your build logic. Things the CMake language will never have, Python gives you on day one.
- **It is built for the free-threaded future.** Python's free-threaded interpreter ([PEP 703](https://docs.python.org/3/howto/free-threading-python.html)) is no longer experimental as of Python 3.14. CMakeless is designed for it from the start: dependency resolution, multi-configuration generation, and build orchestration all run in parallel threads, with no GIL in the way, and degrade gracefully on standard builds.

And to be clear about what CMakeless is _not_: tools like scikit-build-core and meson-python solve the reverse problem, using CMake to build Python packages. CMakeless is for C++ projects, full stop. Python is the pen, not the product.

## Who This Is For

- The developer who has written `fix build` as a commit message more than once.
- The team lead who watches every new hire lose their first week to the build system.
- The library author who wants users to build their project without a support thread.
- The educator who wants to teach C++, not CMake archaeology.
- The engineer shipping Python bindings who is tired of maintaining two build worlds.

If you have never suffered any of this, genuinely, we are happy for you. For everyone else: you should not need a second career in build engineering to compile your own code.

## The Promise

1. **A small API you can hold in your head.** A handful of classes. If you need the documentation open in a permanent tab, we have failed.
2. **Boring, readable output.** The generated CMake is modern, target-centric, and clean enough to commit and to leave behind if you ever stop using us.
3. **Errors at author time, in plain language.** Mistakes are caught in Python, before CMake ever runs.
4. **No lock-in, ever.** CMakeless delegates to CMake; it does not replace it. Walking away costs you nothing but the pleasure.

Your build script should be the most boring file in your repository. Let us make it boring together.

## Read Next

- [ARCHITECTURE](ARCHITECTURE.md): how CMakeless is designed, layer by layer.
- [FEATURES](FEATURES.md): everything the library does for you, with before/after comparisons.
- [ROADMAP](ROADMAP.md): where we are going and when.
- [CONTRIBUTING](CONTRIBUTING.md): why your scars from CMake make you exactly the contributor we need.
