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


class DependencyAnalysis(BaseModel):
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


class ContainerTopology(BaseModel):
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


class CIPipeline(BaseModel):
    provider: str  # github_actions | jenkins | circleci | etc.
    triggers: list[str] = Field(default_factory=list)  # push, pull_request, schedule
    jobs: list[CIJob] = Field(default_factory=list)
    has_tests: bool = False
    has_deploy: bool = False
    has_lint: bool = False


# ─── Architecture ─────────────────────────────────────────────────────────────

class ArchitectureStyle(BaseModel):
    primary_style: str  # monolith | microservices | event-driven | serverless | hybrid
    confidence: float = 0.0  # 0.0–1.0
    patterns_detected: list[str] = Field(default_factory=list)  # MVC, Repository, CQRS, etc.
    layers: list[str] = Field(default_factory=list)  # api, service, repository, domain, etc.
    rationale: str = ""


# ─── Domain / Business ────────────────────────────────────────────────────────

class BusinessRule(BaseModel):
    id: str = Field(default_factory=_new_id)
    description: str
    related_files: list[str] = Field(default_factory=list)
    source: str = ""  # e.g. "docstring", "comment", "inferred"


class DomainModel(BaseModel):
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


class TechnicalDebt(BaseModel):
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

class ObservabilityProfile(BaseModel):
    has_logging: bool = False
    has_metrics: bool = False
    has_tracing: bool = False
    logging_library: Optional[str] = None
    metrics_library: Optional[str] = None
    tracing_library: Optional[str] = None
    coverage_assessment: str = ""  # e.g. "good", "partial", "missing"


# ─── Error Handling ───────────────────────────────────────────────────────────

class ErrorResilienceProfile(BaseModel):
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


class FeatureFlagInventory(BaseModel):
    flags: list[FeatureFlag] = Field(default_factory=list)
    provider: Optional[str] = None  # LaunchDarkly, custom, etc.


# ─── Root Dossier ─────────────────────────────────────────────────────────────

class Dossier(BaseModel):
    """Shared blackboard for the entire analysis pipeline.

    This IS the LangGraph TypedDict state (adapted to Pydantic for validation).
    Agents read from and write to sections of this object only.
    """

    # Repository identification
    repository_id: Optional[str] = None
    repository_url: Optional[str] = None
    commit_hash: Optional[str] = None

    # Layer 1 findings (one section per facet)
    security: list[SecurityFinding] = Field(default_factory=list)
    dependencies: Optional[DependencyAnalysis] = None
    container_topology: Optional[ContainerTopology] = None
    ci_pipeline: Optional[CIPipeline] = None
    architecture: Optional[ArchitectureStyle] = None
    domain_model: Optional[DomainModel] = None
    technical_debt: Optional[TechnicalDebt] = None
    observability: Optional[ObservabilityProfile] = None
    error_resilience: Optional[ErrorResilienceProfile] = None
    feature_flags: Optional[FeatureFlagInventory] = None

    # Cross-facet conflicts (produced by ConflictSynthesizer)
    conflicts: list[ConflictAnalysis] = Field(default_factory=list)

    # Emitted tags for downstream routing (e.g. "risk:sql-injection")
    emitted_tags: list[str] = Field(default_factory=list)

    # Execution metadata
    agents_completed: list[str] = Field(default_factory=list)
    agents_failed: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)  # overflow / future fields
