"""Configuration-management evidence and reproducibility verification.

Regulated industries (DO-178C, ISO 26262, IEC 62304, SOX) assemble the
same bundle by hand for every release: what went in, which tools built it,
what came out, and whether the tests passed. CMakeless already knows all of
it, so it writes it.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cmakeless._version import __version__
from cmakeless.api import _context
from cmakeless.api._runs import build_options, test_options
from cmakeless.deps.lockfile import LOCKFILE_NAME, read_lockfile
from cmakeless.deps.sbom import generate_cyclonedx, reproducible_timestamp
from cmakeless.driver.cmake_driver import CMakeDriver
from cmakeless.driver.file_api import CMakeInfo
from cmakeless.model.nodes import ProjectModel

if TYPE_CHECKING:
    from cmakeless.api.project import Project

_SLSA_PREDICATE = "https://slsa.dev/provenance/v1"
_IN_TOTO_STATEMENT = "https://in-toto.io/Statement/v1"
_BUILD_TYPE = "https://github.com/bbalouki/cmakeless/build/v1"
_HASH_CHUNK = 1 << 20
_VERIFY_TREES = ("verify-a", "verify-b")


def write_evidence(project: Project) -> None:
    """Build, test, stage, and write the evidence bundle for this configuration.

    Args:
        project: The project being built.
    """
    started = _utc_now()
    prepared = project._prepare()
    out_dir = _evidence_dir(project, prepared.build_dir)
    project._configure(prepared.driver)
    prepared.driver.build(build_options())
    if _tree_has_tests(prepared.model):
        prepared.driver.test(test_options(junit=out_dir / "tests.junit.xml"), build=build_options())
    outputs = _stage_outputs(prepared.driver, prepared.model, out_dir / "stage")
    _write_json(out_dir / "manifest.json", _manifest(project, prepared.model))
    _write_json(out_dir / "toolchain.json", _toolchain(prepared.driver, prepared.build_dir))
    lock_path = project.lock_path
    if lock_path.is_file():
        sbom = generate_cyclonedx(
            read_lockfile(lock_path),
            project_name=prepared.model.name,
            project_version=prepared.model.version,
            timestamp=reproducible_timestamp(project.root),
        )
        _write_json(out_dir / "sbom.cdx.json", sbom)
    lines = [f"{digest}  {name}" for name, digest in sorted(outputs.items())]
    (out_dir / "outputs.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    provenance = _provenance(project, prepared.model, outputs, started)
    _write_json(out_dir / "provenance.intoto.json", provenance)
    print(f"[cmakeless] Wrote evidence for {len(outputs)} output(s) to {out_dir}")


def _evidence_dir(project: Project, build_dir: Path) -> Path:
    """Choose and reset the bundle directory.

    Args:
        project: The project, for its root.
        build_dir: The build tree of this configuration.

    Returns:
        The empty bundle directory.
    """
    output = _context.active_run_options().output
    directory = Path(output).resolve() if output is not None else build_dir / "evidence"
    if directory.is_dir():
        shutil.rmtree(directory)
    directory.mkdir(parents=True)
    return directory


def _tree_has_tests(model: ProjectModel) -> bool:
    """Tell whether the project or any subproject declares tests.

    Args:
        model: The project node.

    Returns:
        True when there is anything for CTest to run.
    """
    return bool(model.tests) or any(_tree_has_tests(node.project) for node in model.subprojects)


def _stage_outputs(driver: CMakeDriver, model: ProjectModel, stage: Path) -> dict[str, str]:
    """Install into a staging prefix, or collect built artifacts, and hash them.

    Args:
        driver: The configured, built driver.
        model: The resolved project.
        stage: Where to install.

    Returns:
        Stage-relative (or build-relative) path to SHA256.
    """
    if model.installs or model.install_files:
        config = _context.active_run_options().config
        driver.install(prefix=str(stage), config=config)
        return _hash_tree(stage)
    digests: dict[str, str] = {}
    for info in driver.targets_info():
        for artifact in info.artifacts:
            path = artifact if artifact.is_absolute() else driver.build_dir / artifact
            if path.is_file():
                digests[artifact.as_posix()] = _sha256(path)
    return digests


def _hash_tree(root: Path) -> dict[str, str]:
    """Hash every file under a directory.

    Args:
        root: The directory.

    Returns:
        Root-relative POSIX path to SHA256, empty when the directory is absent.
    """
    if not root.is_dir():
        return {}
    return {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _sha256(path: Path) -> str:
    """Hash one file in chunks.

    Args:
        path: The file.

    Returns:
        The SHA256 hex digest.
    """
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK):
            hasher.update(chunk)
    return hasher.hexdigest()


def _manifest(project: Project, model: ProjectModel) -> dict[str, Any]:
    """Describe what went into this build.

    Args:
        project: The project, for its root.
        model: The resolved project.

    Returns:
        The manifest document.
    """
    inputs = {
        name: f"sha256:{_sha256(project.root / name)}"
        for name in (model.source_script, LOCKFILE_NAME)
        if (project.root / name).is_file()
    }
    return {
        "project": model.name,
        "version": model.version,
        "git": _git_state(project.root),
        "inputs": inputs,
        "cmakeless": __version__,
        "profile": list(model.profile.names) if model.profile is not None else [],
        "preset": _context.active_preset(),
        "supply_chain": model.supply_chain,
    }


def _git_state(root: Path) -> dict[str, object] | None:
    """Record the commit and whether the working tree had uncommitted changes.

    Args:
        root: The project root.

    Returns:
        {"commit": ..., "dirty": ...}, or None outside a git repository.
    """
    git = shutil.which("git")
    if git is None:
        return None
    head = subprocess.run([git, "rev-parse", "HEAD"], capture_output=True, text=True, cwd=root)
    if head.returncode != 0:
        return None
    status = subprocess.run(
        [git, "status", "--porcelain"], capture_output=True, text=True, cwd=root
    )
    return {"commit": head.stdout.strip(), "dirty": bool(status.stdout.strip())}


def _toolchain(driver: CMakeDriver, build_dir: Path) -> dict[str, Any]:
    """Describe the tools that built this configuration and how they were called.

    Args:
        driver: The configured driver.
        build_dir: The build tree, holding compile_commands.json.

    Returns:
        The generator, platform, compilers, and every compile command.
    """
    info: CMakeInfo = driver.cmake_info()
    database = build_dir / "compile_commands.json"
    commands = json.loads(database.read_text(encoding="utf-8")) if database.is_file() else []
    return {
        "cmake_generator": info.generator,
        "system": {"name": info.system_name, "processor": info.system_processor},
        "compilers": [
            {"language": c.language, "id": c.compiler_id, "version": c.compiler_version}
            for c in info.compilers
        ],
        "compile_commands": [
            {"file": entry["file"], "command": entry.get("command") or entry.get("arguments")}
            for entry in commands
        ],
    }


def _provenance(
    project: Project, model: ProjectModel, outputs: dict[str, str], started: str
) -> dict[str, Any]:
    """Write an unsigned SLSA v1 provenance statement for the staged outputs.

    Signing it is left to the release pipeline (for example GitHub artifact
    attestations), which owns the signing identity.

    Args:
        project: The project, for its root.
        model: The resolved project.
        outputs: Output path to SHA256.
        started: When the build started, RFC 3339.

    Returns:
        The in-toto statement.
    """
    lock_path = project.lock_path
    lock = read_lockfile(lock_path) if lock_path.is_file() else None
    dependencies = [
        {"uri": package.url, "digest": {"sha256": package.sha256}, "name": package.name}
        for package in (lock.packages.values() if lock is not None else ())
        if package.url is not None and package.sha256 is not None
    ]
    return {
        "_type": _IN_TOTO_STATEMENT,
        "subject": [
            {"name": name, "digest": {"sha256": digest}} for name, digest in sorted(outputs.items())
        ],
        "predicateType": _SLSA_PREDICATE,
        "predicate": {
            "buildDefinition": {
                "buildType": _BUILD_TYPE,
                "externalParameters": {"project": model.name, "preset": _context.active_preset()},
                "resolvedDependencies": dependencies,
            },
            "runDetails": {
                "builder": {"id": f"cmakeless@{__version__}"},
                "metadata": {"startedOn": started, "finishedOn": _utc_now()},
            },
        },
    }


def _write_json(path: Path, document: object) -> None:
    """Write one deterministic JSON document.

    Args:
        path: The file to write.
        document: The JSON-serializable value.
    """
    text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def _utc_now() -> str:
    """The current time, RFC 3339, second precision.

    Returns:
        The timestamp with a trailing "Z".
    """
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def verify_reproducible(project: Project) -> None:
    """Build twice in separate trees and report whether the outputs are identical.

    Args:
        project: The project being verified.
    """
    digests = []
    for tree in _VERIFY_TREES:
        build_dir = project._build_dir() / tree
        if build_dir.is_dir():
            shutil.rmtree(build_dir)
        prepared = project._prepare(build_dir=build_dir)
        project._configure(prepared.driver)
        prepared.driver.build(build_options())
        digests.append(_stage_outputs(prepared.driver, prepared.model, build_dir / "stage"))
    first, second = digests
    names = sorted(set(first) | set(second))
    different = [name for name in names if first.get(name) != second.get(name)]
    print(f"[cmakeless] {len(names) - len(different)}/{len(names)} output(s) are bit-identical.")
    for name in different:
        print(f"  differs: {name}")
    if different:
        print(
            "[cmakeless] hint: absolute paths and timestamps are the usual cause; "
            "try profile=Profile.reproducible()."
        )
        sys.exit(1)
