"""OwnershipExtractor — reads CODEOWNERS files (zero LLM calls)."""

import logging
import re
from pathlib import Path

from src.dossier.manager import DossierManager
from src.dossier.schema import FileOwnership, OwnershipMap

logger = logging.getLogger(__name__)

AGENT_NAME = "ownership_extractor"


def run(repo_path: str, dossier_manager: DossierManager) -> None:
    root = Path(repo_path)
    ownerships: list[FileOwnership] = []

    for codeowners_path in [root / "CODEOWNERS", root / ".github" / "CODEOWNERS", root / "docs" / "CODEOWNERS"]:
        if codeowners_path.exists():
            try:
                for line in codeowners_path.read_text().splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split()
                    if len(parts) >= 2:
                        pattern, owners = parts[0], parts[1:]
                        for owner in owners:
                            ownerships.append(FileOwnership(
                                file_path=pattern,
                                owner=owner,
                                via="CODEOWNERS",
                            ))
            except OSError:
                pass
            break  # Only one CODEOWNERS file

    unique_owners = list({fo.owner for fo in ownerships})

    dossier_manager.write_section(
        "ownership",
        OwnershipMap(
            agent_name=AGENT_NAME,
            owners=ownerships,
            owner_count=len(unique_owners),
        ),
    )
    dossier_manager.mark_agent_complete(AGENT_NAME)
    logger.info("OwnershipExtractor: %d ownership patterns", len(ownerships))
