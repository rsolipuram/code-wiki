"""DependencyAuditor — heuristic agent that parses lock files (zero LLM calls).

Reads: requirements*.txt, package.json, go.mod, Cargo.toml (searched recursively)
Writes: Dossier.dependencies (DependencyAnalysis)
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional

from src.dossier.manager import DossierManager
from src.dossier.schema import (
    AgentResponse,
    DependencyAnalysis,
    DependencyEntry,
    DependencyVulnerability,
    Severity,
)

logger = logging.getLogger(__name__)

AGENT_NAME = "dependency_auditor"
TAGS = ["dependencies", "supply-chain"]

_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__", ".mypy_cache"}


def _is_skipped(path: Path, root: Path) -> bool:
    """Return True if any path component is in the skip-list."""
    return any(part in _SKIP_DIRS for part in path.relative_to(root).parts)


def run(repo_path: str, dossier_manager: DossierManager) -> None:
    """Parse dependency manifests recursively and write findings to Dossier."""
    root = Path(repo_path)
    packages: list[DependencyEntry] = []

    packages.extend(_parse_requirements(root))
    packages.extend(_parse_package_json(root))
    packages.extend(_parse_go_mod(root))
    packages.extend(_parse_cargo_toml(root))

    # Deduplicate by (name, version) keeping first occurrence
    seen: set[tuple[str, str]] = set()
    unique: list[DependencyEntry] = []
    for pkg in packages:
        key = (pkg.name, pkg.version)
        if key not in seen:
            seen.add(key)
            unique.append(pkg)
    packages = unique

    total_vulns = sum(len(p.vulnerabilities) for p in packages)
    high_risk = [p.name for p in packages if any(
        v.severity in (Severity.CRITICAL, Severity.HIGH) for v in p.vulnerabilities
    )]

    analysis = DependencyAnalysis(
        agent_name=AGENT_NAME,
        packages=packages,
        total_vulnerabilities=total_vulns,
        high_risk_packages=high_risk,
    )
    dossier_manager.write_response(AgentResponse(
        agent_name=AGENT_NAME,
        tags=TAGS,
        confidence=1.0,
        output=analysis.model_dump(),
        output_type="DependencyAnalysis",
    ))
    dossier_manager.mark_agent_complete(AGENT_NAME)
    logger.info("DependencyAuditor: found %d packages, %d vulns", len(packages), total_vulns)


def _parse_requirements(root: Path) -> list[DependencyEntry]:
    entries: list[DependencyEntry] = []
    for req_file in root.rglob("requirements*.txt"):
        if _is_skipped(req_file, root):
            continue
        try:
            for line in req_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                match = re.match(r"^([\w\-\.]+)\s*([>=<!~^]+.*)?$", line)
                if match:
                    name = match.group(1)
                    version = (match.group(2) or "").strip()
                    entries.append(DependencyEntry(name=name, version=version or "unknown"))
        except OSError:
            pass
    return entries


def _parse_package_json(root: Path) -> list[DependencyEntry]:
    entries: list[DependencyEntry] = []
    for pkg_json in root.rglob("package.json"):
        if _is_skipped(pkg_json, root):
            continue
        # Skip deeply nested package.json (> 4 path components from root) to
        # avoid picking up transitive dependency manifests from vendor trees.
        if len(pkg_json.relative_to(root).parts) > 4:
            continue
        try:
            data = json.loads(pkg_json.read_text())
            for dep_type, is_direct in [("dependencies", True), ("devDependencies", False)]:
                for name, version in data.get(dep_type, {}).items():
                    entries.append(DependencyEntry(name=name, version=version, is_direct=is_direct))
        except Exception:
            pass
    return entries


def _parse_go_mod(root: Path) -> list[DependencyEntry]:
    entries: list[DependencyEntry] = []
    for go_mod in root.rglob("go.mod"):
        if _is_skipped(go_mod, root):
            continue
        try:
            in_require = False
            for line in go_mod.read_text().splitlines():
                line = line.strip()
                if line.startswith("require ("):
                    in_require = True
                    continue
                if in_require and line == ")":
                    in_require = False
                    continue
                if in_require or line.startswith("require "):
                    clean = line.replace("require ", "").strip()
                    parts = clean.split()
                    if len(parts) >= 2:
                        entries.append(DependencyEntry(name=parts[0], version=parts[1]))
        except OSError:
            pass
    return entries


def _parse_cargo_toml(root: Path) -> list[DependencyEntry]:
    entries: list[DependencyEntry] = []
    for cargo in root.rglob("Cargo.toml"):
        if _is_skipped(cargo, root):
            continue
        try:
            in_deps = False
            for line in cargo.read_text().splitlines():
                line = line.strip()
                if line == "[dependencies]":
                    in_deps = True
                    continue
                if line.startswith("[") and line != "[dependencies]":
                    in_deps = False
                    continue
                if in_deps and "=" in line:
                    name, _, version = line.partition("=")
                    entries.append(DependencyEntry(
                        name=name.strip(),
                        version=version.strip().strip('"'),
                    ))
        except OSError:
            pass
    return entries
