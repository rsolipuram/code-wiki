"""OwnershipExtractor — reads CODEOWNERS files (zero LLM calls)."""

import logging
import re
from pathlib import Path

from src.dossier.manager import DossierManager

logger = logging.getLogger(__name__)

AGENT_NAME = "ownership_extractor"


def run(repo_path: str, dossier_manager: DossierManager) -> None:
    root = Path(repo_path)
    ownership: dict[str, list[str]] = {}

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
                        ownership[pattern] = owners
            except OSError:
                pass
            break  # Only one CODEOWNERS file

    extra = dossier_manager.get_section("extra") or {}
    dossier_manager.write_section("extra", {**extra, "ownership": ownership})
    dossier_manager.mark_agent_complete(AGENT_NAME)
    logger.info("OwnershipExtractor: %d ownership patterns", len(ownership))
