"""DependencyAuditor — heuristic agent that parses lock files (zero LLM calls).

Reads: requirements*.txt, package-lock.json, go.sum, Cargo.lock, pom.xml
Writes: Dossier.dependencies (DependencyAnalysis)
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional

from src.dossier.manager import DossierManager
from src.dossier.schema import (
    DependencyAnalysis,
    DependencyEntry,
    DependencyVulnerability,
    Severity,
)

logger = logging.getLogger(__name__)

AGENT_NAME = "dependency_auditor"


def run(repo_path: str, dossier_manager: DossierManager) -> None:
    """Parse dependency manifests and write findings to Dossier."""
    root = Path(repo_path)
    packages: list[DependencyEntry] = []

    packages.extend(_parse_requirements(root))
    packages.extend(_parse_package_json(root))
    packages.extend(_parse_go_mod(root))
    packages.extend(_parse_cargo_toml(root))

    total_vulns = sum(len(p.vulnerabilities) for p in packages)
    high_risk = [p.name for p in packages if any(
        v.severity in (Severity.CRITICAL, Severity.HIGH) for v in p.vulnerabilities
    )]

    analysis = DependencyAnalysis(
        packages=packages,
        total_vulnerabilities=total_vulns,
        high_risk_packages=high_risk,
    )
    dossier_manager.write_section("dependencies", analysis)
    dossier_manager.mark_agent_complete(AGENT_NAME)
    logger.info("DependencyAuditor: found %d packages, %d vulns", len(packages), total_vulns)


def _parse_requirements(root: Path) -> list[DependencyEntry]:
    entries: list[DependencyEntry] = []
    for req_file in root.glob("requirements*.txt"):
        try:
            for line in req_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Handle pinned (==), minimum (>=), ranges
                match = re.match(r"^([\w\-\.]+)\s*([>=<!~^]+.*)?$", line)
                if match:
                    name = match.group(1)
                    version = (match.group(2) or "").strip()
                    entries.append(DependencyEntry(name=name, version=version or "unknown"))
        except OSError:
            pass
    return entries


def _parse_package_json(root: Path) -> list[DependencyEntry]:
    pkg_json = root / "package.json"
    if not pkg_json.exists():
        return []
    try:
        data = json.loads(pkg_json.read_text())
        entries: list[DependencyEntry] = []
        for dep_type, is_direct in [("dependencies", True), ("devDependencies", False)]:
            for name, version in data.get(dep_type, {}).items():
                entries.append(DependencyEntry(name=name, version=version, is_direct=is_direct))
        return entries
    except Exception:
        return []


def _parse_go_mod(root: Path) -> list[DependencyEntry]:
    go_mod = root / "go.mod"
    if not go_mod.exists():
        return []
    entries: list[DependencyEntry] = []
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
    cargo = root / "Cargo.toml"
    if not cargo.exists():
        return []
    entries: list[DependencyEntry] = []
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
