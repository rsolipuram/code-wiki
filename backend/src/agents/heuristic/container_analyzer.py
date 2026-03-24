"""ContainerAnalyzer — heuristic agent parsing Dockerfiles and docker-compose (zero LLM)."""

import logging
import re
from pathlib import Path

import yaml  # PyYAML

from src.dossier.manager import DossierManager
from src.dossier.schema import ContainerService, ContainerTopology

logger = logging.getLogger(__name__)

AGENT_NAME = "container_analyzer"

_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__"}


def _is_skipped(path: Path, root: Path) -> bool:
    return any(part in _SKIP_DIRS for part in path.relative_to(root).parts)


def run(repo_path: str, dossier_manager: DossierManager) -> None:
    root = Path(repo_path)
    services: list[ContainerService] = []
    base_images: list[str] = []
    is_multi_stage = False

    # Parse Dockerfiles recursively
    for dockerfile in root.rglob("Dockerfile"):
        if _is_skipped(dockerfile, root):
            continue
        try:
            content = dockerfile.read_text()
            froms = re.findall(r"^FROM\s+(\S+)", content, re.MULTILINE | re.IGNORECASE)
            if len(froms) > 1:
                is_multi_stage = True
            base_images.extend(froms)
        except OSError:
            pass

    for dockerfile in root.rglob("Dockerfile.*"):
        if _is_skipped(dockerfile, root):
            continue
        try:
            content = dockerfile.read_text()
            froms = re.findall(r"^FROM\s+(\S+)", content, re.MULTILINE | re.IGNORECASE)
            if len(froms) > 1:
                is_multi_stage = True
            base_images.extend(froms)
        except OSError:
            pass

    # Parse docker-compose files recursively
    compose_files = list(root.rglob("docker-compose*.yml")) + list(root.rglob("docker-compose*.yaml"))
    for compose_file in compose_files:
        if _is_skipped(compose_file, root):
            continue
        try:
            data = yaml.safe_load(compose_file.read_text()) or {}
            for svc_name, svc_config in (data.get("services") or {}).items():
                if not isinstance(svc_config, dict):
                    continue
                ports = svc_config.get("ports", [])
                volumes = svc_config.get("volumes", [])
                env = list((svc_config.get("environment") or {}).keys()) if isinstance(
                    svc_config.get("environment"), dict) else []
                services.append(ContainerService(
                    name=svc_name,
                    image=svc_config.get("image"),
                    ports=[str(p) for p in ports],
                    volumes=[str(v) for v in volumes],
                    environment_vars=env,
                ))
        except Exception as exc:
            logger.debug("Could not parse %s: %s", compose_file, exc)

    topology = ContainerTopology(
        agent_name=AGENT_NAME,
        services=services,
        base_images=list(set(base_images)),
        is_multi_stage=is_multi_stage,
    )
    dossier_manager.write_section("container_topology", topology)
    dossier_manager.mark_agent_complete(AGENT_NAME)
    logger.info("ContainerAnalyzer: %d services, %d base images", len(topology.services), len(topology.base_images))
