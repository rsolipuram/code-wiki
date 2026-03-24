"""TechnicalDebtAssessor — scans TODO/FIXME comments and code smells (1 LLM call)."""

import logging
import re
from pathlib import Path

from src.dossier.manager import DossierManager
from src.dossier.schema import AgentResponse, Severity, TechnicalDebt, TechnicalDebtItem

logger = logging.getLogger(__name__)

AGENT_NAME = "technical_debt_assessor"
TAGS = ["quality", "technical-debt"]

_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "dist", "build"}
_TODO_PATTERN = re.compile(r"#\s*(TODO|FIXME|HACK|XXX|NOTE):\s*(.+)", re.IGNORECASE)


def run(repo_path: str, dossier_manager: DossierManager, compressed=None) -> None:
    """Scan for TODO/FIXME/HACK comments (no LLM call — pure pattern matching)."""
    root = Path(repo_path)
    items: list[TechnicalDebtItem] = []
    total_loc = 0

    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        if any(skip in file_path.parts for skip in _SKIP_DIRS):
            continue
        if file_path.suffix not in {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".java", ".rb"}:
            continue

        try:
            lines = file_path.read_text(errors="replace").splitlines()
        except OSError:
            continue

        total_loc += len(lines)
        rel = str(file_path.relative_to(root))

        for i, line in enumerate(lines, 1):
            match = _TODO_PATTERN.search(line)
            if match:
                marker = match.group(1).upper()
                description = match.group(2).strip()
                severity = Severity.HIGH if marker in ("FIXME", "HACK") else Severity.LOW
                items.append(TechnicalDebtItem(
                    type=marker.lower(),
                    file_path=rel,
                    line_number=i,
                    description=description,
                    severity=severity,
                ))

    todo_count = sum(1 for i in items if i.type == "todo")
    fixme_count = sum(1 for i in items if i.type == "fixme")
    smell_density = (len(items) / total_loc * 1000) if total_loc > 0 else 0.0

    debt = TechnicalDebt(
        agent_name=AGENT_NAME,
        items=items,
        todo_count=todo_count,
        fixme_count=fixme_count,
        smell_density=smell_density,
    )
    dossier_manager.write_response(AgentResponse(
        agent_name=AGENT_NAME,
        tags=TAGS,
        confidence=debt.confidence,
        output=debt.model_dump(),
        output_type="TechnicalDebt",
    ))
    dossier_manager.mark_agent_complete(AGENT_NAME)
    logger.info("TechnicalDebtAssessor: %d items (%.1f/kloc)", len(items), smell_density)
