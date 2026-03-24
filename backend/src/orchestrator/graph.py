"""LangGraph StateGraph orchestration wiring the full analysis pipeline.

Execution order:
  Layer 0: RepoRecon → fingerprint
  Layer 1: Triage → parallel heuristic agents → ReAct agents (tag-triggered) → single-pass agents → ConflictSynthesizer
  Layer 2: Wiki generation pipeline

Dossier IS the shared state. Agents read from / write to it via DossierManager.

Agent discovery is descriptor-driven: each agent module exports a DESCRIPTOR
(AgentDescriptor) that declares its name, tier, tags, and resource needs.
The orchestrator collects these at import time — no hardcoded dicts.
"""

import concurrent.futures
import logging
import time
from typing import Callable, Optional

from src.agents import conflict_synthesizer
from src.agents.heuristic import (
    api_contract_extractor,
    ci_pipeline_analyzer,
    container_analyzer,
    dependency_auditor,
    feature_flag_mapper,
    iac_analyzer,
    ownership_extractor,
)
from src.agents.iterative import (
    auth_flow_tracer,
    data_flow_tracer,
    security_sentinel,
    vuln_chain_tracer,
)
from src.agents.single_pass import (
    architectural_classifier,
    business_rule_extractor,
    error_resilience_analyzer,
    observability_auditor,
    performance_hotspot_scanner,
    technical_debt_assessor,
)
from src.dossier.manager import DossierManager
from src.dossier.rag_index import index_dossier
from src.dossier.schema import Dossier
from src.dossier.serializer import dossier_output_path, serialize_dossier
from src.orchestrator.descriptor import AgentDescriptor
from src.recon import repo_recon
from src.recon.fingerprint import RepoFingerprint
from src.wiki.v2_types import CompressedCodebase

logger = logging.getLogger(__name__)

# ── Agent registry: collected from module DESCRIPTOR exports ──────────────
_ALL_AGENT_MODULES = [
    dependency_auditor, container_analyzer, ci_pipeline_analyzer,
    iac_analyzer, api_contract_extractor, ownership_extractor,
    feature_flag_mapper,
    security_sentinel, data_flow_tracer, auth_flow_tracer, vuln_chain_tracer,
    architectural_classifier, business_rule_extractor, observability_auditor,
    error_resilience_analyzer, technical_debt_assessor,
    performance_hotspot_scanner,
    conflict_synthesizer,
]

ALL_DESCRIPTORS: list[AgentDescriptor] = [
    m.DESCRIPTOR for m in _ALL_AGENT_MODULES
]

def _descriptors_by_tier(tier: str) -> list[AgentDescriptor]:
    return [d for d in ALL_DESCRIPTORS if d.tier == tier]


class AnalysisPipeline:
    """Full repository analysis pipeline.

    Not using the full LangGraph StateGraph API here to keep dependencies minimal;
    the orchestration logic matches the LangGraph conceptual model:
    - Dossier is the shared state
    - Agents are nodes discovered via DESCRIPTOR exports
    - Tiers define execution order and parallelism
    """

    def __init__(
        self,
        repo_path: str,
        repository_id: str,
        fingerprint: Optional[RepoFingerprint] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        compressed: Optional["CompressedCodebase"] = None,
        repo_name: Optional[str] = None,
    ) -> None:
        self.repo_path = repo_path
        self.repository_id = repository_id
        self.fingerprint = fingerprint
        self.progress_callback = progress_callback
        self.compressed = compressed
        self.repo_name = repo_name
        self._agents_completed = 0
        self._agents_total = 0
        self.dossier_manager = DossierManager(Dossier(
            repository_id=repository_id,
        ))

    def _report_agent_progress(self, agent_name: str) -> None:
        """Report agent completion via callback if configured."""
        self._agents_completed += 1
        if self.progress_callback:
            self.progress_callback(self._agents_completed, self._agents_total, agent_name)

    def run(self) -> Dossier:
        """Execute the full pipeline and return the populated Dossier."""
        layer1_start = time.monotonic()

        # ── Layer 0: Repo Reconnaissance ──────────────────────────────────────
        if self.fingerprint:
            logger.info("[Layer 0] Using pre-computed fingerprint (skipping duplicate recon)")
            fingerprint = self.fingerprint
        else:
            logger.info("[Layer 0] Running RepoRecon on %s", self.repo_path)
            fingerprint = repo_recon.run(self.repo_path)
        self.dossier_manager.dossier.extra["fingerprint"] = fingerprint.to_dict()

        # ── Embed compact compressor summary so it appears in _dossier.json ──
        if self.compressed is not None:
            self.dossier_manager.dossier.extra["compressor"] = {
                "compression_level": self.compressed.compression_level,
                "repo_summary": self.compressed.repo_summary,
                "key_entity_count": len(self.compressed.key_entities),
                "file_summary_count": len(self.compressed.file_summaries),
                "call_graph_summary": self.compressed.call_graph_summary,
            }

        # ── Collect descriptors by tier ───────────────────────────────────────
        heuristic = _descriptors_by_tier("heuristic")
        react = _descriptors_by_tier("react")
        single_pass = _descriptors_by_tier("single_pass")
        synthesis = _descriptors_by_tier("synthesis")

        self._agents_total = len(heuristic) + len(react) + len(single_pass)
        self._agents_completed = 0

        # ── Layer 1a: Heuristic agents (parallel) ────────────────────────────
        logger.info("[Layer 1a] Running %d heuristic agents in parallel", len(heuristic))
        self._run_tier(heuristic, parallel=True)

        # ── Layer 1b: ReAct agents (sequential — they share Dossier state) ───
        logger.info("[Layer 1b] Running %d ReAct agents", len(react))
        self._run_tier(react, parallel=False)

        # ── Layer 1c: Single-pass agents (parallel) ──────────────────────────
        logger.info("[Layer 1c] Running %d single-pass agents", len(single_pass))
        self._run_tier(single_pass, parallel=True)

        # ── Dossier summary after Layer 1 ────────────────────────────────────
        dossier = self.dossier_manager.dossier
        logger.info(
            "[Layer 1 summary] responses=%d, agents_completed=%d, tags=%s",
            len(dossier.responses),
            len(dossier.agents_completed),
            sorted(dossier.all_tags()),
        )
        layer1_elapsed = time.monotonic() - layer1_start
        logger.info("[Layer 1] Total elapsed: %.1fs", layer1_elapsed)

        # ── Conflict synthesis ────────────────────────────────────────────────
        for desc in synthesis:
            logger.info("[Synthesis] Running %s", desc.name)
            try:
                desc.run(self.dossier_manager)
            except Exception as exc:
                logger.error("Synthesis agent %s failed: %s", desc.name, exc)
                self.dossier_manager.mark_agent_failed(desc.name)

        # ── Serialize Dossier to disk for inspection ──────────────────────────
        try:
            out_path = dossier_output_path(self.repo_path, repo_name=self.repo_name)
            serialize_dossier(self.dossier_manager.dossier, out_path)
        except Exception as exc:
            logger.warning("[Dossier] Serialization failed (non-fatal): %s", exc)

        # ── Index Dossier into Qdrant for RAG ─────────────────────────────────
        logger.info("[RAG] Indexing Dossier findings")
        try:
            indexed = index_dossier(self.dossier_manager.dossier, self.repository_id)
            logger.info("[RAG] Indexed %d findings", indexed)
        except Exception as exc:
            logger.warning("[RAG] Indexing failed: %s", exc)

        return self.dossier_manager.dossier

    def _run_tier(self, descriptors: list[AgentDescriptor], *, parallel: bool) -> None:
        """Run a tier of agents, building args from each descriptor's needs."""
        if parallel:
            self._run_tier_parallel(descriptors)
        else:
            self._run_tier_sequential(descriptors)

    def _build_args(self, desc: AgentDescriptor) -> tuple:
        """Build positional args for an agent based on its descriptor flags."""
        args: list = [self.repo_path, self.dossier_manager]
        if desc.needs_fingerprint:
            args.append(self.fingerprint)
        if desc.needs_compressed:
            args.append(self.compressed)
        return tuple(args)

    def _run_tier_parallel(self, descriptors: list[AgentDescriptor]) -> None:
        """Run agents in parallel using ThreadPoolExecutor."""
        max_workers = min(4, len(descriptors)) or 1
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for desc in descriptors:
                args = self._build_args(desc)
                futures[executor.submit(desc.run, *args)] = desc.name

            for future in concurrent.futures.as_completed(futures):
                agent_name = futures[future]
                try:
                    future.result()
                    logger.info("[%s] Agent %s completed", descriptors[0].tier, agent_name)
                    self._report_agent_progress(agent_name)
                except Exception as exc:
                    logger.error("Agent %s failed: %s", agent_name, exc)
                    self.dossier_manager.mark_agent_failed(agent_name)
                    self._report_agent_progress(agent_name)

    def _run_tier_sequential(self, descriptors: list[AgentDescriptor]) -> None:
        """Run agents sequentially (for tiers that share Dossier state)."""
        for desc in descriptors:
            if desc.name in self.dossier_manager.dossier.agents_completed:
                continue
            t0 = time.monotonic()
            logger.info("[%s] Starting agent %s", desc.tier, desc.name)
            try:
                args = self._build_args(desc)
                desc.run(*args)
                elapsed = time.monotonic() - t0
                logger.info("[%s] Agent %s completed (%.1fs)", desc.tier, desc.name, elapsed)
                self._report_agent_progress(desc.name)
            except Exception as exc:
                logger.error("Agent %s failed: %s", desc.name, exc)
                self.dossier_manager.mark_agent_failed(desc.name)
                self._report_agent_progress(desc.name)


def run_analysis(
    repo_path: str,
    repository_id: str,
    fingerprint: Optional[RepoFingerprint] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    compressed: Optional["CompressedCodebase"] = None,
    repo_name: Optional[str] = None,
) -> Dossier:
    """Entry point for the full analysis pipeline.

    Args:
        repo_path: Absolute local path to the cloned repository.
        repository_id: Repository UUID from PostgreSQL.
        progress_callback: Optional (completed, total, agent_name) callback.
        compressed: Optional pre-run CompressedCodebase to pass to agents.
        repo_name: Human-readable repo name for artifact output path alignment.

    Returns:
        Populated Dossier ready for wiki generation.
    """
    pipeline = AnalysisPipeline(
        repo_path=repo_path,
        repository_id=repository_id,
        fingerprint=fingerprint,
        progress_callback=progress_callback,
        compressed=compressed,
        repo_name=repo_name,
    )
    return pipeline.run()
