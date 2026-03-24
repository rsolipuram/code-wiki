"""Dossier Pydantic schema — the shared blackboard for all facet agents.

Agents NEVER communicate directly. All findings flow through the Dossier.
Each finding is an atomic, queryable unit (never a blob).
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ─── AgentOutput base ─────────────────────────────────────────────────────────

class AgentOutput(BaseModel):
    """Base class for all single-value Dossier section outputs."""
    agent_name: str = ""
    confidence: float = 1.0


class AgentResponse(BaseModel):
    """Uniform wrapper for any agent's analysis output.

    Every agent writes one or more AgentResponse objects to the Dossier.
    Tags are predetermined per agent and enable cross-agent querying
    (e.g. by_tag("security") spans security_sentinel + auth_flow_tracer).
    """
    agent_name: str
    tags: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    output: dict[str, Any] = Field(default_factory=dict)
    output_type: str = ""  # class name for typed reconstruction


def _new_id() -> str:
    return str(uuid.uuid4())


# ─── Severity ────────────────────────────────────────────────────────────────

class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


# ─── Security ────────────────────────────────────────────────────────────────

class SecurityFinding(BaseModel):
    id: str = Field(default_factory=_new_id)
    type: str  # e.g. "jwt-without-rotation", "sql-injection-risk", "secret-exposure"
    severity: Severity
    related_files: list[str] = Field(default_factory=list)
    related_modules: list[str] = Field(default_factory=list)
    description: str
    evidence_lines: list[str] = Field(default_factory=list)  # file:lineno snippets
    tags: list[str] = Field(default_factory=list)  # emitted tags (e.g. "risk:jwt-without-rotation")


# ─── Dependencies ────────────────────────────────────────────────────────────

class DependencyVulnerability(BaseModel):
    cve_id: str
    severity: Severity
    description: str
    fixed_in: Optional[str] = None


class DependencyEntry(BaseModel):
    name: str
    version: str
    license: Optional[str] = None
    vulnerabilities: list[DependencyVulnerability] = Field(default_factory=list)
    is_direct: bool = True


class DependencyAnalysis(AgentOutput):
    packages: list[DependencyEntry] = Field(default_factory=list)
    total_vulnerabilities: int = 0
    high_risk_packages: list[str] = Field(default_factory=list)


# ─── Infrastructure ───────────────────────────────────────────────────────────

class ContainerService(BaseModel):
    name: str
    image: Optional[str] = None
    ports: list[str] = Field(default_factory=list)
    volumes: list[str] = Field(default_factory=list)
    environment_vars: list[str] = Field(default_factory=list)


class ContainerTopology(AgentOutput):
    services: list[ContainerService] = Field(default_factory=list)
    base_images: list[str] = Field(default_factory=list)
    is_multi_stage: bool = False


# ─── CI/CD ───────────────────────────────────────────────────────────────────

class CIStep(BaseModel):
    name: str
    command: Optional[str] = None
    uses: Optional[str] = None  # GitHub Actions action


class CIJob(BaseModel):
    name: str
    runner: Optional[str] = None
    steps: list[CIStep] = Field(default_factory=list)


class CIPipeline(AgentOutput):
    provider: str  # github_actions | jenkins | circleci | etc.
    triggers: list[str] = Field(default_factory=list)  # push, pull_request, schedule
    jobs: list[CIJob] = Field(default_factory=list)
    has_tests: bool = False
    has_deploy: bool = False
    has_lint: bool = False


# ─── Architecture ─────────────────────────────────────────────────────────────

class ArchitectureStyle(AgentOutput):
    primary_style: str  # monolith | microservices | event-driven | serverless | hybrid
    patterns_detected: list[str] = Field(default_factory=list)  # MVC, Repository, CQRS, etc.
    layers: list[str] = Field(default_factory=list)  # api, service, repository, domain, etc.
    rationale: str = ""


# ─── Domain / Business ────────────────────────────────────────────────────────

class BusinessRule(BaseModel):
    id: str = Field(default_factory=_new_id)
    description: str
    related_files: list[str] = Field(default_factory=list)
    source: str = ""  # e.g. "docstring", "comment", "inferred"


class DomainModel(AgentOutput):
    entities: list[str] = Field(default_factory=list)  # detected business entities
    business_rules: list[BusinessRule] = Field(default_factory=list)
    ubiquitous_language: list[str] = Field(default_factory=list)  # domain terms


# ─── Technical Debt ───────────────────────────────────────────────────────────

class TechnicalDebtItem(BaseModel):
    id: str = Field(default_factory=_new_id)
    type: str  # todo | fixme | hack | complexity | smell
    file_path: str
    line_number: int
    description: str
    severity: Severity = Severity.LOW


class TechnicalDebt(AgentOutput):
    items: list[TechnicalDebtItem] = Field(default_factory=list)
    todo_count: int = 0
    fixme_count: int = 0
    smell_density: float = 0.0  # smells per 1000 LOC


# ─── Conflicts ────────────────────────────────────────────────────────────────

class ConflictAnalysis(BaseModel):
    id: str = Field(default_factory=_new_id)
    facet_a: str  # name of first facet
    finding_a: str  # what facet A claims
    facet_b: str  # name of second facet
    finding_b: str  # what facet B claims
    why_both_coexist: str  # neutral explanation of how both can be true
    developer_questions: list[str] = Field(default_factory=list)
    # NOTE: NEVER add a `winner` or `resolution` field — per Principle II


# ─── Observability ───────────────────────────────────────────────────────────

class ObservabilityProfile(AgentOutput):
    has_logging: bool = False
    has_metrics: bool = False
    has_tracing: bool = False
    logging_library: Optional[str] = None
    metrics_library: Optional[str] = None
    tracing_library: Optional[str] = None
    coverage_assessment: str = ""  # e.g. "good", "partial", "missing"


# ─── Error Handling ───────────────────────────────────────────────────────────

class ErrorResilienceProfile(AgentOutput):
    retry_patterns_detected: bool = False
    circuit_breaker_detected: bool = False
    global_error_handlers: list[str] = Field(default_factory=list)
    silent_failures: list[str] = Field(default_factory=list)  # file paths with bare except


# ─── Feature Flags ────────────────────────────────────────────────────────────

class FeatureFlag(BaseModel):
    name: str
    enabled_by_default: Optional[bool] = None
    file_path: str
    usage_count: int = 0


class FeatureFlagInventory(AgentOutput):
    flags: list[FeatureFlag] = Field(default_factory=list)
    provider: Optional[str] = None  # LaunchDarkly, custom, etc.


# ─── Auth Flow ───────────────────────────────────────────────────────────────

class AuthFlow(BaseModel):
    pattern: str  # e.g. "jwt", "session", "oauth", "api_key"
    token_storage: str = ""  # e.g. "header", "cookie", "localStorage"
    refresh_strategy: str = ""
    vulnerabilities: list[str] = Field(default_factory=list)


class AuthFlowAnalysis(AgentOutput):
    flows: list[AuthFlow] = Field(default_factory=list)
    has_mfa: bool = False
    auth_libraries: list[str] = Field(default_factory=list)


# ─── Data Flow ───────────────────────────────────────────────────────────────

class DataFlowEdge(BaseModel):
    source: str
    destination: str
    data_type: str = ""
    crosses_trust_boundary: bool = False


class DataFlowAnalysis(AgentOutput):
    flows: list[DataFlowEdge] = Field(default_factory=list)
    sensitive_fields: list[str] = Field(default_factory=list)
    external_calls: list[str] = Field(default_factory=list)


# ─── Performance ─────────────────────────────────────────────────────────────

class PerformanceHotspot(BaseModel):
    file_path: str
    line_number: int
    issue_type: str  # "n+1", "blocking_io", "unbounded_loop", "large_payload"
    description: str


class PerformanceProfile(AgentOutput):
    hotspots: list[PerformanceHotspot] = Field(default_factory=list)
    n_plus_one_detected: bool = False
    blocking_io_files: list[str] = Field(default_factory=list)


# ─── IaC ─────────────────────────────────────────────────────────────────────

class IaCResource(BaseModel):
    resource_type: str
    name: str
    provider: str = ""


class IaCAnalysis(AgentOutput):
    provider: str = ""  # terraform, pulumi, cdk, cloudformation
    resources: list[IaCResource] = Field(default_factory=list)
    environments: list[str] = Field(default_factory=list)
    has_state_backend: bool = False


# ─── Ownership ───────────────────────────────────────────────────────────────

class FileOwnership(BaseModel):
    file_path: str
    owner: str
    via: str = ""  # CODEOWNERS, git blame, package.json


class OwnershipMap(AgentOutput):
    owners: list[FileOwnership] = Field(default_factory=list)
    unowned_files: list[str] = Field(default_factory=list)
    owner_count: int = 0


# ─── Root Dossier ─────────────────────────────────────────────────────────────

class Dossier(BaseModel):
    """Shared blackboard for the entire analysis pipeline.

    All agent outputs live in the `responses` list — a flat log of AgentResponse
    objects queryable by tag or agent name.
    """

    # Repository identification
    repository_id: Optional[str] = None
    repository_url: Optional[str] = None
    commit_hash: Optional[str] = None

    # ── Primary storage (tag-based) ──────────────────────────────────────────
    responses: list[AgentResponse] = Field(default_factory=list)

    # Execution metadata
    agents_completed: list[str] = Field(default_factory=list)
    agents_failed: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)

    # ── Query interface ──────────────────────────────────────────────────────

    def by_tag(self, tag: str) -> list[AgentResponse]:
        """Return all responses that carry the given tag."""
        return [r for r in self.responses if tag in r.tags]

    def by_agent(self, name: str) -> list[AgentResponse]:
        """Return all responses from a specific agent."""
        return [r for r in self.responses if r.agent_name == name]

    def by_tags(self, tags: list[str]) -> list[AgentResponse]:
        """Return responses matching ANY of the given tags (union)."""
        tag_set = set(tags)
        return [r for r in self.responses if tag_set & set(r.tags)]

    def all_tags(self) -> set[str]:
        """Return the set of all tags across all responses."""
        return {t for r in self.responses for t in r.tags}

    def latest_by_tag(self, tag: str) -> Optional[AgentResponse]:
        """Return the most recent response with the given tag, or None."""
        matches = self.by_tag(tag)
        return matches[-1] if matches else None

    # ── Serialization ────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict with responses serialized."""
        d = self.model_dump(exclude={"responses"})
        d["responses"] = [r.model_dump() for r in self.responses]
        return d
