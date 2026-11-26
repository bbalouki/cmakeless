"""A monorepo: two independent projects, one shared cmakeless.lock.

'cmakeless build' here builds every member; '--project editor' builds one,
and '--affected-since origin/main' builds only what changed.
"""

from cmakeless import Workspace

workspace = Workspace(lockfile="cmakeless.lock")
workspace.add("engine")
workspace.add("tools/editor")
workspace.build()
