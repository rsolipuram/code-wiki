"""Phase 0: Hierarchical code summarization.

Compresses a codebase to fit in LLM context windows.
Three levels based on repo size:
  - "none"        (<100 files, <10k LOC): no LLM, use raw code
  - "file_only"   (100-999 files): per-file summaries → repo summary
  - "full_pyramid" (1000+ files): file → dir → repo summaries
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from src.llm.client import chat
from src.parsers.base import ParsedEntity
from src.recon.fingerprint import RepoFingerprint
from src.wiki.interestingness import ScoredEntity
from src.wiki.v2_types import (
    CompressedCodebase,
    DirectorySummary,
    FileSummary,
)

logger = logging.getLogger(__name__)


class CodebaseCompressor:
    """Compress a codebase into an LLM-digestible representation."""

    def compress(
        self,
        repo_path: str,
        entities: list[ParsedEntity],
        fingerprint: RepoFingerprint,
        scored_entities: list[ScoredEntity],
    ) -> CompressedCodebase:
        level = self._decide_compression_level(fingerprint)
        logger.info(
            "Compression level: %s (files=%d, loc=%d)",
            level, fingerprint.file_count, fingerprint.loc,
        )

        if level == "none":
            return self._compress_none(repo_path, entities, scored_entities, fingerprint)
        elif level == "file_only":
            return self._compress_file_level(repo_path, entities, scored_entities, fingerprint)
        else:
            return self._compress_full_pyramid(repo_path, entities, scored_entities, fingerprint)

    def _decide_compression_level(self, fingerprint: RepoFingerprint) -> str:
        if fingerprint.file_count < 100 and fingerprint.loc < 10_000:
            return "none"
        elif fingerprint.file_count < 1000:
            return "file_only"
        else:
            return "full_pyramid"

    def _compress_none(
        self,
        repo_path: str,
        entities: list[ParsedEntity],
        scored: list[ScoredEntity],
        fingerprint: RepoFingerprint,
    ) -> CompressedCodebase:
        """No LLM calls. Build key_entities and graphs from parsed data."""
        key_entities = self._build_key_entities_list(scored, limit=50)
        call_graph = self._build_call_graph_text(entities)
        import_graph = self._build_import_graph_text(entities)

        # Build repo summary from fingerprint metadata (no LLM)
        langs = ", ".join(fingerprint.languages[:5]) if fingerprint.languages else "unknown"
        desc = fingerprint.project_description or fingerprint.project_name or "a code repository"
        repo_summary = (
            f"{desc}. "
            f"Contains {fingerprint.file_count} files with {fingerprint.loc:,} lines of code. "
            f"Primary languages: {langs}. "
            f"System type: {fingerprint.system_type}."
        )

        return CompressedCodebase(
            repo_summary=repo_summary,
            key_entities=key_entities,
            call_graph_summary=call_graph,
            import_graph_summary=import_graph,
            compression_level="none",
        )

    def _compress_file_level(
        self,
        repo_path: str,
        entities: list[ParsedEntity],
        scored: list[ScoredEntity],
        fingerprint: RepoFingerprint,
    ) -> CompressedCodebase:
        """Per-file summaries → repo summary."""
        # Group entities by file
        file_entities: dict[str, list[ParsedEntity]] = {}
        for e in entities:
            file_entities.setdefault(e.file_path, []).append(e)

        # Summarize files in parallel
        file_summaries: dict[str, FileSummary] = {}
        with ThreadPoolExecutor(max_workers=1) as pool:
            futures = {
                pool.submit(self._summarize_file, fp, ents, repo_path): fp
                for fp, ents in file_entities.items()
            }
            for future in as_completed(futures):
                fp = futures[future]
                try:
                    summary = future.result(timeout=30)
                    if summary:
                        file_summaries[fp] = summary
                except Exception as exc:
                    logger.warning("File summary failed for %s: %s", fp, exc)

        # Single LLM call: all file summaries → repo summary
        repo_summary = self._generate_repo_summary(
            file_summaries, fingerprint, entities,
        )

        key_entities = self._build_key_entities_list(scored, limit=50)
        call_graph = self._build_call_graph_text(entities)
        import_graph = self._build_import_graph_text(entities)

        return CompressedCodebase(
            repo_summary=repo_summary,
            file_summaries=file_summaries,
            key_entities=key_entities,
            call_graph_summary=call_graph,
            import_graph_summary=import_graph,
            compression_level="file_only",
        )

    def _compress_full_pyramid(
        self,
        repo_path: str,
        entities: list[ParsedEntity],
        scored: list[ScoredEntity],
        fingerprint: RepoFingerprint,
    ) -> CompressedCodebase:
        """3-level: file → directory → repo summaries."""
        # Level 0: file summaries
        file_entities: dict[str, list[ParsedEntity]] = {}
        for e in entities:
            file_entities.setdefault(e.file_path, []).append(e)

        file_summaries: dict[str, FileSummary] = {}
        with ThreadPoolExecutor(max_workers=1) as pool:
            futures = {
                pool.submit(self._summarize_file, fp, ents, repo_path): fp
                for fp, ents in file_entities.items()
            }
            for future in as_completed(futures):
                fp = futures[future]
                try:
                    summary = future.result(timeout=30)
                    if summary:
                        file_summaries[fp] = summary
                except Exception as exc:
                    logger.warning("File summary failed for %s: %s", fp, exc)

        # Level 1: directory summaries
        dir_groups: dict[str, list[str]] = {}
        for fp in file_summaries:
            parent = str(Path(fp).parent)
            dir_groups.setdefault(parent, []).append(fp)

        dir_summaries: dict[str, DirectorySummary] = {}
        with ThreadPoolExecutor(max_workers=1) as pool:
            futures = {
                pool.submit(
                    self._summarize_directory, dp, files, file_summaries,
                ): dp
                for dp, files in dir_groups.items()
            }
            for future in as_completed(futures):
                dp = futures[future]
                try:
                    summary = future.result(timeout=30)
                    if summary:
                        dir_summaries[dp] = summary
                except Exception as exc:
                    logger.warning("Dir summary failed for %s: %s", dp, exc)

        # Level 2: repo summary
        repo_summary = self._generate_repo_summary_from_dirs(
            dir_summaries, fingerprint,
        )

        key_entities = self._build_key_entities_list(scored, limit=50)
        call_graph = self._build_call_graph_text(entities)
        import_graph = self._build_import_graph_text(entities)

        return CompressedCodebase(
            repo_summary=repo_summary,
            file_summaries=file_summaries,
            directory_summaries=dir_summaries,
            key_entities=key_entities,
            call_graph_summary=call_graph,
            import_graph_summary=import_graph,
            compression_level="full_pyramid",
        )

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _summarize_file(
        self,
        file_path: str,
        file_entities: list[ParsedEntity],
        repo_path: str,
    ) -> Optional[FileSummary]:
        """1 LLM call → ~150-word file summary."""
        # Build entity listing for prompt
        entity_lines = []
        for e in file_entities[:20]:
            sig = e.signature or e.name
            entity_lines.append(f"  - {e.entity_type} {e.qualified_name}: {sig}")
        entity_text = "\n".join(entity_lines)

        # Read first ~150 lines of file for context
        full_path = Path(repo_path) / file_path
        file_preview = ""
        line_count = 0
        try:
            if full_path.is_file():
                content = full_path.read_text(errors="replace")
                lines = content.splitlines()
                line_count = len(lines)
                file_preview = "\n".join(lines[:150])
        except Exception:
            pass

        ext = Path(file_path).suffix
        lang_map = {".py": "Python", ".ts": "TypeScript", ".js": "JavaScript",
                     ".tsx": "TypeScript", ".jsx": "JavaScript", ".java": "Java",
                     ".go": "Go", ".rs": "Rust"}
        language = lang_map.get(ext, ext.lstrip(".") or "unknown")

        prompt = (
            f"Summarize this {language} file in 100-150 words. "
            f"Include: purpose, key design decisions, error handling approach, "
            f"and how it integrates with other parts of the codebase.\n\n"
            f"File: {file_path}\n"
            f"Entities:\n{entity_text}\n\n"
            f"Code preview:\n{file_preview[:3000]}"
        )

        try:
            summary = chat(
                [{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.1,
            )
        except Exception as exc:
            logger.warning("LLM summary failed for %s: %s", file_path, exc)
            # Fallback: use first entity's docstring
            summary = file_entities[0].docstring or "" if file_entities else ""

        key_ents = [e.qualified_name for e in file_entities[:5]]
        return FileSummary(
            file_path=file_path,
            language=language,
            line_count=line_count,
            summary=summary.strip(),
            entity_count=len(file_entities),
            key_entities=key_ents,
        )

    def _summarize_directory(
        self,
        dir_path: str,
        child_files: list[str],
        file_summaries: dict[str, FileSummary],
    ) -> Optional[DirectorySummary]:
        """1 LLM call → ~250-word directory summary."""
        file_summary_lines = []
        all_key_entities: list[str] = []
        for fp in child_files:
            fs = file_summaries.get(fp)
            if fs:
                file_summary_lines.append(f"  - {fp}: {fs.summary}")
                all_key_entities.extend(fs.key_entities)

        prompt = (
            f"Summarize this directory's purpose in 200-250 words. "
            f"Include: what this module/package does, its design patterns, "
            f"how files relate to each other, and key integration points.\n\n"
            f"Directory: {dir_path}\n"
            f"Files:\n" + "\n".join(file_summary_lines)
        )

        try:
            summary = chat(
                [{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.1,
            )
        except Exception as exc:
            logger.warning("LLM dir summary failed for %s: %s", dir_path, exc)
            summary = f"Contains {len(child_files)} files."

        return DirectorySummary(
            dir_path=dir_path,
            file_count=len(child_files),
            summary=summary.strip(),
            child_files=child_files,
            key_entities=all_key_entities[:10],
        )

    def _generate_repo_summary(
        self,
        file_summaries: dict[str, FileSummary],
        fingerprint: RepoFingerprint,
        entities: list[ParsedEntity],
    ) -> str:
        """Single LLM call: aggregate file summaries into repo overview."""
        summary_lines = []
        for fp, fs in sorted(file_summaries.items())[:50]:
            summary_lines.append(f"  - {fp}: {fs.summary}")

        langs = ", ".join(fingerprint.languages[:5])
        desc = fingerprint.project_description or "a software project"

        prompt = (
            f"Write a 500-1000 word overview of this codebase. "
            f"Describe its purpose, architecture, key components, design decisions, and data flows.\n\n"
            f"Project: {fingerprint.project_name or 'unknown'}\n"
            f"Description: {desc}\n"
            f"Languages: {langs}\n"
            f"Files: {fingerprint.file_count}, LOC: {fingerprint.loc}\n"
            f"System type: {fingerprint.system_type}\n\n"
            f"File summaries:\n" + "\n".join(summary_lines)
        )

        try:
            return chat(
                [{"role": "user", "content": prompt}],
                max_tokens=3000,
                temperature=0.2,
            ).strip()
        except Exception:
            return (
                f"{desc}. Contains {fingerprint.file_count} files "
                f"with {fingerprint.loc:,} lines of code in {langs}."
            )

    def _generate_repo_summary_from_dirs(
        self,
        dir_summaries: dict[str, DirectorySummary],
        fingerprint: RepoFingerprint,
    ) -> str:
        """Single LLM call: aggregate directory summaries into repo overview."""
        summary_lines = []
        for dp, ds in sorted(dir_summaries.items())[:30]:
            summary_lines.append(f"  - {dp}/ ({ds.file_count} files): {ds.summary}")

        desc = fingerprint.project_description or "a software project"

        prompt = (
            f"Write a 500-1000 word overview of this codebase. "
            f"Describe its purpose, architecture, key components, design decisions, and data flows.\n\n"
            f"Project: {fingerprint.project_name or 'unknown'}\n"
            f"Description: {desc}\n"
            f"Languages: {', '.join(fingerprint.languages[:5])}\n"
            f"Files: {fingerprint.file_count}, LOC: {fingerprint.loc}\n\n"
            f"Directory summaries:\n" + "\n".join(summary_lines)
        )

        try:
            return chat(
                [{"role": "user", "content": prompt}],
                max_tokens=3000,
                temperature=0.2,
            ).strip()
        except Exception:
            return (
                f"{desc}. Contains {fingerprint.file_count} files "
                f"with {fingerprint.loc:,} lines in "
                f"{', '.join(fingerprint.languages[:3])}."
            )

    def _build_call_graph_text(self, entities: list[ParsedEntity]) -> str:
        """Build text representation of call graph."""
        edges: list[str] = []
        for e in entities:
            for callee in e.calls[:5]:
                edges.append(f"{e.name} calls {callee}")
        # Cap to avoid huge text
        return "; ".join(edges[:100])

    def _build_import_graph_text(self, entities: list[ParsedEntity]) -> str:
        """Build text representation of import graph."""
        imports: list[str] = []
        seen: set[str] = set()
        for e in entities:
            for imp in e.imports:
                key = f"{e.file_path} imports {imp}"
                if key not in seen:
                    seen.add(key)
                    imports.append(key)
        return "; ".join(imports[:100])

    def _build_key_entities_list(
        self,
        scored: list[ScoredEntity],
        limit: int = 50,
    ) -> list[dict]:
        """Top-N scored entities as dicts."""
        result = []
        for se in scored[:limit]:
            e = se.entity
            result.append({
                "qualified_name": e.qualified_name,
                "entity_type": e.entity_type,
                "signature": e.signature or "",
                "docstring": (e.docstring or "")[:200],
                "file_path": e.file_path,
                "score": se.score,
            })
        return result
