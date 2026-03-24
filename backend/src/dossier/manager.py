"""DossierManager — thread-safe operations on the shared Dossier blackboard."""

import logging
import threading
from typing import Any, Optional

from src.dossier.schema import (
    AgentOutput,
    AgentResponse,
    ConflictAnalysis,
    Dossier,
    SecurityFinding,
    Severity,
    TechnicalDebtItem,
    _SECTION_REGISTRY,
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

    # ─── Primary write (tag-based) ───────────────────────────────────────────

    def write_response(self, response: AgentResponse) -> None:
        """Append an AgentResponse to the Dossier.

        Also dual-writes to legacy fields (sections/security/conflicts) so
        existing consumers continue working during migration.
        """
        with self._lock:
            self._dossier.responses.append(response)
            # Propagate tags to legacy emitted_tags
            for tag in response.tags:
                if tag not in self._dossier.emitted_tags:
                    self._dossier.emitted_tags.append(tag)
            # Dual-write to legacy fields
            self._legacy_write(response)

    def _legacy_write(self, response: AgentResponse) -> None:
        """Populate legacy Dossier fields from an AgentResponse.

        Maps output_type to the appropriate legacy storage:
        - SecurityFinding → security list
        - ConflictAnalysis → conflicts list
        - AgentOutput subclasses → sections dict (using _SECTION_REGISTRY reverse lookup)

        Called under lock — no additional locking needed.
        """
        otype = response.output_type

        if otype == "SecurityFinding":
            try:
                finding = SecurityFinding(**response.output)
                self._dossier.security.append(finding)
            except Exception:
                logger.debug("Legacy write skipped for SecurityFinding: invalid output")
            return

        if otype == "ConflictAnalysis":
            try:
                conflict = ConflictAnalysis(**response.output)
                self._dossier.conflicts.append(conflict)
            except Exception:
                logger.debug("Legacy write skipped for ConflictAnalysis: invalid output")
            return

        # For AgentOutput subclasses, find the section key from the registry
        for section_key, model_cls in _SECTION_REGISTRY.items():
            if model_cls.__name__ == otype:
                try:
                    self._dossier.sections[section_key] = model_cls(**response.output)
                except Exception:
                    logger.debug("Legacy write skipped for %s: invalid output", otype)
                return

        # Unregistered output type — store in extra as fallback
        if otype:
            logger.debug("No legacy mapping for output_type=%r, storing in extra", otype)

    # ─── Legacy write operations (kept during migration) ─────────────────────

    def write_security_finding(self, finding: SecurityFinding) -> None:
        with self._lock:
            self._dossier.security.append(finding)
            for tag in finding.tags:
                if tag not in self._dossier.emitted_tags:
                    self._dossier.emitted_tags.append(tag)

    def write_conflict(self, conflict: ConflictAnalysis) -> None:
        with self._lock:
            self._dossier.conflicts.append(conflict)

    def write_section(self, section: str, value: Any) -> None:
        """Set a Dossier section by name (e.g. 'architecture').

        For registry-known sections, validates the value type.
        For 'extra', merges into the extra dict.
        """
        with self._lock:
            if section == "extra":
                if isinstance(value, dict):
                    self._dossier.extra.update(value)
                else:
                    self._dossier.extra = value
                return
            if section in _SECTION_REGISTRY:
                expected = _SECTION_REGISTRY[section]
                if not isinstance(value, expected):
                    raise TypeError(
                        f"write_section({section!r}): expected {expected.__name__}, "
                        f"got {type(value).__name__}"
                    )
            else:
                logger.warning(
                    "write_section: unregistered section key %r — consider adding to _SECTION_REGISTRY",
                    section,
                )
            self._dossier.sections[section] = value

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
        """Query findings from a Dossier section with optional filters."""
        if section == "security":
            items = self._dossier.security
        else:
            items = self.get_section(section)
        if items is None:
            return []
        if not isinstance(items, list):
            return [items]

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
        if section == "extra":
            return self._dossier.extra
        return self._dossier.sections.get(section)

    def has_tag(self, tag: str) -> bool:
        """Check for tag in both new responses and legacy emitted_tags."""
        if tag in self._dossier.emitted_tags:
            return True
        return any(tag in r.tags for r in self._dossier.responses)

    def clear(self) -> None:
        """Reset the Dossier to empty state (useful for testing)."""
        with self._lock:
            self._dossier = Dossier()
