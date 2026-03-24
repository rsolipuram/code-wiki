"""DossierManager — thread-safe operations on the shared Dossier blackboard."""

import logging
import threading
from typing import Any, Optional

from src.dossier.schema import (
    AgentResponse,
    Dossier,
    Severity,
)

logger = logging.getLogger(__name__)


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

    def write_response(self, response: AgentResponse) -> None:
        """Append an AgentResponse to the Dossier."""
        with self._lock:
            self._dossier.responses.append(response)

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
        tag: str = "security",
        module: Optional[str] = None,
        severity: Optional[Severity] = None,
    ) -> list[AgentResponse]:
        """Query responses by tag with optional filters."""
        results = self._dossier.by_tag(tag)

        if module is not None:
            results = [
                r for r in results
                if module in r.output.get("related_modules", [])
            ]
        if severity is not None:
            severity_order = [s.value for s in Severity]
            min_idx = severity_order.index(severity.value)
            results = [
                r for r in results
                if severity_order.index(r.output.get("severity", "info")) <= min_idx
            ]
        return results

    def has_tag(self, tag: str) -> bool:
        """Check if any response carries the given tag."""
        return any(tag in r.tags for r in self._dossier.responses)

    def clear(self) -> None:
        """Reset the Dossier to empty state (useful for testing)."""
        with self._lock:
            self._dossier = Dossier()
