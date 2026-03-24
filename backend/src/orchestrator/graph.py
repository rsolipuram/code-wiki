"""LangGraph StateGraph orchestration wiring the full analysis pipeline.

Execution order:
  Layer 0: RepoRecon → fingerprint
  Layer 1: Triage → parallel heuristic agents → ReAct agents (tag-triggered) → single-pass agents → ConflictSynthesizer
  Layer 2: Wiki generation pipeline

Dossier IS the shared state. Agents read from / write to it via DossierManager.
"""

import concurrent.futures
import logging
import time
from typing import Any, Callable, Optional

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
from src.recon import repo_recon
from src.recon.fingerprint import RepoFingerprint
from src.wiki.v2_types import CompressedCodebase

logger = logging.getLogger(__name__)

# Maps agent name → callable (repo_path, dossier_manager) → None
_HEURISTIC_AGENTS = {
    "dependency_auditor": dependency_auditor.run,
    "container_analyzer": container_analyzer.run,
    "ci_pipeline_analyzer": ci_pipeline_analyzer.run,
    "iac_analyzer": iac_analyzer.run,
    "api_contract_extractor": api_contract_extractor.run,
    "ownership_extractor": ownership_extractor.run,
    "feature_flag_mapper": feature_flag_mapper.run,
}

_REACT_AGENTS = {
    "security_sentinel": security_sentinel.run,
    "data_flow_tracer": data_flow_tracer.run,
    "auth_flow_tracer": auth_flow_tracer.run,
    "vuln_chain_tracer": vuln_chain_tracer.run,
}

_SINGLE_PASS_AGENTS = {
    "architectural_classifier": architectural_classifier.run,
    "business_rule_extractor": business_rule_extractor.run,
    "observability_auditor": observability_auditor.run,
    "error_resilience_analyzer": error_resilience_analyzer.run,
    "technical_debt_assessor": technical_debt_assessor.run,
    "performance_hotspot_scanner": performance_hotspot_scanner.run,
}


class AnalysisPipeline:
    """Full repository analysis pipeline.

    Not using the full LangGraph StateGraph API here to keep dependencies minimal;
    the orchestration logic matches the LangGraph conceptual model:
    - Dossier is the shared state
    - Agents are nodes
    - TAG_TRIGGERS provides conditional edges
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

        # ── Layer 1a: Heuristic agents (parallel) ────────────────────────
        heuristic_to_run = _HEURISTIC_AGENTS
        react_to_run = list(_REACT_AGENTS.keys())
        single_to_run = _SINGLE_PASS_AGENTS

        # Compute total agent count for progress reporting
        self._agents_total = len(_HEURISTIC_AGENTS) + len(_REACT_AGENTS) + len(_SINGLE_PASS_AGENTS)
        self._agents_completed = 0

        logger.info("[Layer 1a] Running %d heuristic agents in parallel", len(heuristic_to_run))
        self._run_parallel(heuristic_to_run)

        # ── Layer 1b: ReAct agents (sequential) ─────────────────────────────
        logger.info("[Layer 1b] Running %d ReAct agents", len(react_to_run))
        self._run_react_agents(react_to_run, fingerprint)

        # ── Layer 1c: Single-pass agents (parallel) ───────────────────────────
        logger.info("[Layer 1c] Running %d single-pass agents", len(single_to_run))
        self._run_single_pass(single_to_run, fingerprint)

        # ── Dossier summary after Layer 1 ────────────────────────────────────
        dossier = self.dossier_manager.dossier
        logger.info(
            "[Layer 1 summary] security_findings=%d, agents_completed=%d, emitted_tags=%d",
            len(dossier.security),
            len(dossier.agents_completed),
            len(dossier.emitted_tags),
        )
        layer1_elapsed = time.monotonic() - layer1_start
        logger.info("[Layer 1] Total elapsed: %.1fs", layer1_elapsed)

        # ── Conflict synthesis ────────────────────────────────────────────────
        logger.info("[Conflict] Running ConflictSynthesizer")
        conflict_synthesizer.run(self.dossier_manager)

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

    def _run_parallel(self, agents: dict) -> None:
        """Run heuristic agents in parallel using ThreadPoolExecutor."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            futures = {
                executor.submit(fn, self.repo_path, self.dossier_manager): name
                for name, fn in agents.items()
            }
            for future in concurrent.futures.as_completed(futures):
                agent_name = futures[future]
                try:
                    future.result()
                    logger.info("[Heuristic] Agent %s completed", agent_name)
                    self._report_agent_progress(agent_name)
                except Exception as exc:
                    logger.error("Heuristic agent %s failed: %s", agent_name, exc)
                    self.dossier_manager.mark_agent_failed(agent_name)
                    self._report_agent_progress(agent_name)

    def _run_react_agents(self, agent_names: list[str], fingerprint: RepoFingerprint) -> None:
        """Run ReAct agents sequentially (they share Dossier state)."""
        for name in agent_names:
            if name not in _REACT_AGENTS:
                continue
            if name in self.dossier_manager.dossier.agents_completed:
                continue
            t0 = time.monotonic()
            logger.info("[ReAct] Starting agent %s", name)
            try:
                _REACT_AGENTS[name](self.repo_path, self.dossier_manager, self.compressed)
                elapsed = time.monotonic() - t0
                logger.info("[ReAct] Agent %s completed (%.1fs)", name, elapsed)
                self._report_agent_progress(name)
                # Log any tags emitted by this agent
                tags = self.dossier_manager.dossier.emitted_tags
                if tags:
                    logger.debug("[ReAct] Tags after %s: %s", name, tags)
            except Exception as exc:
                logger.error("ReAct agent %s failed: %s", name, exc)
                self.dossier_manager.mark_agent_failed(name)
                self._report_agent_progress(name)

    def _run_single_pass(self, agents: dict, fingerprint: RepoFingerprint) -> None:
        """Run single-pass agents (architectural_classifier also gets fingerprint; all get compressed)."""
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            futures = {}
            for name, fn in agents.items():
                if name == "architectural_classifier":
                    future = executor.submit(fn, self.repo_path, self.dossier_manager, fingerprint, self.compressed)
                else:
                    future = executor.submit(fn, self.repo_path, self.dossier_manager, self.compressed)
                futures[future] = name

            for future in concurrent.futures.as_completed(futures):
                agent_name = futures[future]
                try:
                    future.result()
                    logger.info("[SinglePass] Agent %s completed", agent_name)
                    self._report_agent_progress(agent_name)
                except Exception as exc:
                    logger.error("Single-pass agent %s failed: %s", agent_name, exc)
                    self.dossier_manager.mark_agent_failed(agent_name)
                    self._report_agent_progress(agent_name)


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
