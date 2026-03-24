"""FeatureFlagMapper — detects feature flag patterns in source code (zero LLM calls)."""

import logging
import re
from pathlib import Path

from src.dossier.manager import DossierManager
from src.dossier.schema import AgentResponse, FeatureFlag, FeatureFlagInventory

logger = logging.getLogger(__name__)

AGENT_NAME = "feature_flag_mapper"
TAGS = ["feature-flags", "configuration"]

# Patterns to detect feature flag usage
_FLAG_PATTERNS = [
    re.compile(r'(?:feature_flags?|features?|flags?)\[[\'"]([\w\-]+)[\'"]\]'),
    re.compile(r'(?:isEnabled|isFeatureEnabled|getFlag)\([\'\"]([\w\-]+)[\'\"]\)'),
    re.compile(r'FEATURE_(?:FLAG_)?(\w+)\s*='),
    re.compile(r'ENABLE_(\w+)\s*='),
]

_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "dist", "build"}


def run(repo_path: str, dossier_manager: DossierManager) -> None:
    root = Path(repo_path)
    flags: dict[str, FeatureFlag] = {}

    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        if any(skip in file_path.parts for skip in _SKIP_DIRS):
            continue
        if file_path.suffix not in {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rb", ".java"}:
            continue
        try:
            content = file_path.read_text(errors="replace")
        except OSError:
            continue

        rel = str(file_path.relative_to(root))
        for pattern in _FLAG_PATTERNS:
            for match in pattern.finditer(content):
                name = match.group(1)
                if name in flags:
                    flags[name] = FeatureFlag(
                        name=flags[name].name,
                        file_path=flags[name].file_path,
                        usage_count=flags[name].usage_count + 1,
                    )
                else:
                    flags[name] = FeatureFlag(name=name, file_path=rel, usage_count=1)

    inventory = FeatureFlagInventory(agent_name=AGENT_NAME, flags=list(flags.values()))
    dossier_manager.write_response(AgentResponse(
        agent_name=AGENT_NAME,
        tags=TAGS,
        confidence=1.0,
        output=inventory.model_dump(),
        output_type="FeatureFlagInventory",
    ))
    dossier_manager.mark_agent_complete(AGENT_NAME)
    logger.info("FeatureFlagMapper: %d flags detected", len(flags))
