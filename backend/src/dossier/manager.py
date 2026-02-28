"""DossierManager — thread-safe operations on the shared Dossier blackboard."""

import threading
from typing import Any, Optional

from src.dossier.schema import (
    ConflictAnalysis,
    Dossier,
    SecurityFinding,
    Severity,
    TechnicalDebtItem,
)


class DossierManager:
    """Thread-safe wrapper around a Dossier instance.

    All write operations use a lock so concurrent facet agents can safely
    append findings without race conditions.
    """

    def __init__(self, dossier: Optional[Dossier] = None) -> None:
        self._dossier = dossier or Dossier()
        self._lock = threading.Lock()

    @property
    def dossier(self) -> Dossier:
        return self._dossier

    # ─── Write operations ────────────────────────────────────────────────────

    def write_security_finding(self, finding: SecurityFinding) -> None:
        with self._lock:
            self._dossier.security.append(finding)
            # Emit tags so downstream routing can pick up specialist agents
            for tag in finding.tags:
                if tag not in self._dossier.emitted_tags:
                    self._dossier.emitted_tags.append(tag)

    def write_conflict(self, conflict: ConflictAnalysis) -> None:
        with self._lock:
            self._dossier.conflicts.append(conflict)

    def write_section(self, section: str, value: Any) -> None:
        """Set a top-level Dossier section by name (e.g. 'architecture')."""
        with self._lock:
            if not hasattr(self._dossier, section):
                raise ValueError(f"Unknown Dossier section: {section!r}")
            object.__setattr__(self._dossier, section, value)

    def mark_agent_complete(self, agent_name: str) -> None:
        with self._lock:
            if agent_name not in self._dossier.agents_completed:
                self._dossier.agents_completed.append(agent_name)

    def mark_agent_failed(self, agent_name: str) -> None:
        with self._lock:
            if agent_name not in self._dossier.agents_failed:
                self._dossier.agents_failed.append(agent_name)

    # ─── Query operations ────────────────────────────────────────────────────

    def query_findings(
        self,
        section: str = "security",
        module: Optional[str] = None,
        severity: Optional[Severity] = None,
    ) -> list[Any]:
        """Query findings from a Dossier section with optional filters.

        Args:
            section: Dossier section name (default: "security").
            module: Filter by related_modules membership.
            severity: Filter by minimum severity level.

        Returns:
            Filtered list of findings from the requested section.
        """
        items = getattr(self._dossier, section, None)
        if items is None:
            return []
        if not isinstance(items, list):
            return [items]

        # Apply filters
        results = items
        if module is not None:
            results = [
                f for f in results
                if hasattr(f, "related_modules") and module in f.related_modules
            ]
        if severity is not None:
            severity_order = [s.value for s in Severity]
            min_idx = severity_order.index(severity.value)
            results = [
                f for f in results
                if hasattr(f, "severity") and severity_order.index(f.severity.value) <= min_idx
            ]
        return results

    def get_section(self, section: str) -> Any:
        """Return the full value of a Dossier section."""
        return getattr(self._dossier, section, None)

    def has_tag(self, tag: str) -> bool:
        return tag in self._dossier.emitted_tags

    def clear(self) -> None:
        """Reset the Dossier to empty state (useful for testing)."""
        with self._lock:
            self._dossier = Dossier()
