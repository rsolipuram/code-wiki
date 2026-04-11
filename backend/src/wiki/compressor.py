"""Phase 0: Hierarchical code summarization.

Compresses a codebase to fit in LLM context windows.
Two strategies based on repo size:
  - "flat"    (<1000 files): LLM per-file + per-dir + repo summary (flat aggregation)
  - "pyramid" (1000+ files): file → dir → repo (3-level progressive rollup)

Within "flat", parallelism is tuned by file count:
  < 100 files  → 4 parallel workers
  100-999 files → 2 parallel workers
"""

import hashlib
import json
import logging
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from src.llm.client import chat
from src.parsers.base import ParsedEntity
from src.recon.fingerprint import RepoFingerprint
from src.wiki.interestingness import ScoredEntity, score_entities
from src.wiki.compression_types import (
    CompressedCodebase,
    DirectorySummary,
    FileSummary,
)

if TYPE_CHECKING:
    from src.cache.index_cache import IndexCache

logger = logging.getLogger(__name__)


def _extract_json_object(text: str) -> Optional[dict]:
    """Extract first valid JSON object from LLM output.

    Handles thinking-model output that wraps JSON in a markdown code block
    after a reasoning preamble, e.g.:
        Here's my thinking...
        ```json
        {"summary": "...", "nav_topic": "...", "nav_role": "..."}
        ```
    Also handles bare JSON with a preamble containing stray braces.
    """
    raw = (text or "").strip()

    # Extract content from ALL markdown code fences (not just leading ones)
    fence_contents: list[str] = []
    fence_re = re.compile(r"```(?:json|jsonc)?\s*\n?(.*?)```", re.DOTALL)
    for m in fence_re.finditer(raw):
        fence_contents.append(m.group(1).strip())

    # Strip all fences from raw for the bare-JSON search below
    raw_no_fence = fence_re.sub(" ", raw).strip()

    # Try each fenced block first (most reliable when model uses code blocks)
    for block in fence_contents:
        try:
            data = json.loads(block)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    # Try whole defenced string (fast path for clean bare-JSON responses)
    try:
        data = json.loads(raw_no_fence)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass

    # Walk every { position — handles preambles with stray braces
    for i, ch in enumerate(raw_no_fence):
        if ch != "{":
            continue
        depth = 0
        for j, c in enumerate(raw_no_fence[i:], i):
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    candidate = raw_no_fence[i : j + 1]
                    try:
                        data = json.loads(candidate)
                        if isinstance(data, dict):
                            return data
                    except json.JSONDecodeError:
                        break
                    break
    return None


# ── Cache serialization helpers ──────────────────────────────────────────────

def _file_summary_to_dict(fs: FileSummary) -> dict:
    """Convert a FileSummary to a plain dict for cache storage."""
    return {
        "file_path": fs.file_path,
        "language": fs.language,
        "line_count": fs.line_count,
        "summary": fs.summary,
        "entity_count": fs.entity_count,
        "key_entities": fs.key_entities,
        "exported_symbols": fs.exported_symbols,
        "dependencies": fs.dependencies,
        "nav_topic": fs.nav_topic,
        "nav_role": fs.nav_role,
        "function_calls": fs.function_calls,
    }


def _dict_to_file_summary(d: dict) -> FileSummary:
    """Reconstruct a FileSummary from a cached dict."""
    return FileSummary(
        file_path=d.get("file_path", ""),
        language=d.get("language", ""),
        line_count=d.get("line_count", 0),
        summary=d.get("summary", ""),
        entity_count=d.get("entity_count", 0),
        key_entities=d.get("key_entities", []),
        exported_symbols=d.get("exported_symbols", []),
        dependencies=d.get("dependencies", []),
        nav_topic=d.get("nav_topic", ""),
        nav_role=d.get("nav_role", ""),
        function_calls=d.get("function_calls", {}),
    )


def _dir_summary_to_dict(ds: DirectorySummary) -> dict:
    """Convert a DirectorySummary to a plain dict for cache storage."""
    return {
        "dir_path": ds.dir_path,
        "file_count": ds.file_count,
        "summary": ds.summary,
        "child_files": ds.child_files,
        "key_entities": ds.key_entities,
        "nav_items": ds.nav_items,
    }


class CodebaseCompressor:
    """Compress a codebase into an LLM-digestible representation."""

    @staticmethod
    def _ancestor_dirs(file_path: str) -> list[str]:
        """Return all non-root ancestor directories for a relative file path.

        Example:
          ui/desktop/src/main.ts -> ["ui", "ui/desktop", "ui/desktop/src"]
        """
        parts = [p for p in Path(file_path).parts if p not in {"", "."}]
        if not parts:
            return []
        if len(parts) == 1:
            # Keep root-level files visible in directory-level aggregation.
            return ["."]
        return ["/".join(parts[:i]) for i in range(1, len(parts))]

    @staticmethod
    def _to_repo_relative(file_path: str, repo_path: str) -> str:
        """Normalize parser file paths to repo-relative form.

        Handles absolute and relative values emitted by different parsers.
        Returns empty string for paths that cannot be safely mapped to repo root.
        """
        raw = str(file_path or "").replace("\\", "/")
        if not raw:
            return ""

        if not repo_path:
            return raw.lstrip("./")

        root = Path(repo_path).resolve()
        root_prefix = str(root).replace("\\", "/").rstrip("/") + "/"
        if raw.startswith(root_prefix):
            return raw[len(root_prefix):]

        rel_prefix = str(Path(repo_path)).replace("\\", "/").rstrip("/") + "/"
        if raw.startswith(rel_prefix):
            return raw[len(rel_prefix):]

        p = Path(file_path)
        if p.is_absolute():
            try:
                return str(p.resolve().relative_to(root)).replace("\\", "/")
            except ValueError:
                logger.warning("Skipping non-repo absolute path during compression: %s", file_path)
                return ""

        return raw.lstrip("./")

    @staticmethod
    def _top_level_dir(file_path: str, assume_directory: bool = False) -> str:
        parts = [p for p in Path(file_path).parts if p not in {"", "."}]
        if not parts:
            return "."
        if len(parts) == 1 and not assume_directory:
            return "."
        return parts[0]

    def _stratified_file_sample(
        self,
        file_summaries: dict[str, FileSummary],
        budget: int,
    ) -> list[tuple[str, FileSummary]]:
        """Sample file summaries proportionally across top-level directories."""
        if not file_summaries or budget <= 0:
            return []

        items = list(file_summaries.items())
        if budget >= len(items):
            return sorted(items, key=lambda kv: kv[0])

        buckets: dict[str, list[tuple[str, FileSummary]]] = {}
        for path, fs in items:
            buckets.setdefault(self._top_level_dir(path), []).append((path, fs))

        for bucket in buckets.values():
            bucket.sort(key=lambda kv: (-kv[1].entity_count, kv[0]))

        total = len(items)
        allocations: dict[str, int] = {}
        remainders: list[tuple[float, str]] = []
        for top, bucket in buckets.items():
            frac = (len(bucket) / total) * budget
            base = int(frac)
            allocations[top] = base
            remainders.append((frac - base, top))

        selected = sum(allocations.values())
        guaranteed = [top for top in sorted(buckets) if allocations[top] == 0 and buckets[top]]
        for top in guaranteed:
            if selected >= budget:
                break
            allocations[top] += 1
            selected += 1

        if selected < budget:
            for _, top in sorted(remainders, reverse=True):
                if selected >= budget:
                    break
                if allocations[top] < len(buckets[top]):
                    allocations[top] += 1
                    selected += 1

        if selected > budget:
            for top in sorted(allocations.keys(), key=lambda k: allocations[k], reverse=True):
                while selected > budget and allocations[top] > 0:
                    allocations[top] -= 1
                    selected -= 1

        chosen: list[tuple[str, FileSummary]] = []
        for top in sorted(buckets):
            take = min(allocations.get(top, 0), len(buckets[top]))
            chosen.extend(buckets[top][:take])

        seen = {path for path, _ in chosen}
        if len(chosen) < budget:
            leftovers: list[tuple[str, FileSummary]] = []
            for top in sorted(buckets):
                leftovers.extend([(p, fs) for p, fs in buckets[top] if p not in seen])
            leftovers.sort(key=lambda kv: (-kv[1].entity_count, kv[0]))
            chosen.extend(leftovers[: budget - len(chosen)])

        return chosen[:budget]

    def compress(
        self,
        repo_path: str,
        entities: list[ParsedEntity],
        fingerprint: RepoFingerprint,
        scored_entities: list[ScoredEntity],
        cache: Optional["IndexCache"] = None,
    ) -> CompressedCodebase:
        level = self._decide_compression_level(fingerprint)
        logger.info(
            "Compression level: %s (files=%d, loc=%d)",
            level, fingerprint.file_count, fingerprint.loc,
        )

        if level == "flat":
            return self._compress_flat(repo_path, entities, scored_entities, fingerprint, cache=cache)
        else:
            return self._compress_pyramid(repo_path, entities, scored_entities, fingerprint, cache=cache)

    def _decide_compression_level(self, fingerprint: RepoFingerprint) -> str:
        if fingerprint.file_count < 1000:
            return "flat"
        else:
            return "pyramid"

    def _workers_for(self, file_count: int) -> int:
        """Tune parallelism to repo size — avoid overwhelming local LM Studio."""
        if file_count < 100:
            return 4
        return 2

    def _compress_flat(
        self,
        repo_path: str,
        entities: list[ParsedEntity],
        scored: list[ScoredEntity],
        fingerprint: RepoFingerprint,
        cache: Optional["IndexCache"] = None,
    ) -> CompressedCodebase:
        """Flat aggregation: LLM per-file + per-dir + repo summary.

        Used for repos < 1000 files. Parallelism scales with file count:
          < 100 files  → 4 workers
          100-999 files → 2 workers
        """
        workers = self._workers_for(fingerprint.file_count)

        # ── Check cache settings ─────────────────────────────────────────────
        from src.config import get_settings
        cache_reads_enabled = cache is not None and get_settings().index_cache_enabled

        # ── Step 1: extract structural metadata from AST (no LLM) ────────────
        file_summaries = self._extract_file_metadata(entities, repo_path)

        # ── Step 2: upgrade each file's summary prose via LLM ────────────────
        # Rebuild file→entities map using normalised relative paths (same as
        # _extract_file_metadata) so keys match.
        file_entities: dict[str, list[ParsedEntity]] = {}
        for e in entities:
            rel = self._to_repo_relative(e.file_path, repo_path)
            if not rel:
                continue
            file_entities.setdefault(rel, []).append(e)

        # Compute content hashes for cache invalidation
        file_hashes: dict[str, str] = {}
        for rel_path in file_entities:
            full_path = Path(repo_path) / rel_path
            try:
                if full_path.is_file():
                    file_hashes[rel_path] = hashlib.sha256(
                        full_path.read_bytes()
                    ).hexdigest()
            except OSError:
                pass

        # Determine cache hits/misses when cache is available
        cache_hit_paths: set[str] = set()
        if cache_reads_enabled:
            diff = cache.diff_against_tree(file_hashes)
            cache_hit_paths = set(diff.hits)
            if diff.stale:
                cache.cleanup_stale(diff.stale)
            logger.info(
                "Cache diff: %d hits, %d misses, %d stale",
                len(diff.hits), len(diff.misses), len(diff.stale),
            )

        # Restore cached file summaries (cache hits)
        for rel_path in list(cache_hit_paths):
            if cache is not None:
                cached = cache.get_file_summary(rel_path)
                if cached and rel_path in file_summaries:
                    meta = cached.get("_cache_meta", {})
                    logger.info("Cache HIT for %s", rel_path)
                    fs = file_summaries[rel_path]
                    file_summaries[rel_path] = FileSummary(
                        file_path=fs.file_path,
                        language=cached.get("language", fs.language),
                        line_count=cached.get("line_count", fs.line_count),
                        summary=cached.get("summary", fs.summary),
                        entity_count=cached.get("entity_count", fs.entity_count),
                        key_entities=cached.get("key_entities", fs.key_entities),
                        exported_symbols=cached.get("exported_symbols", fs.exported_symbols),
                        dependencies=cached.get("dependencies", fs.dependencies),
                        nav_topic=cached.get("nav_topic", fs.nav_topic),
                        nav_role=cached.get("nav_role", fs.nav_role),
                    )
                else:
                    # Cache file missing despite manifest entry — treat as miss
                    cache_hit_paths.discard(rel_path)

        # LLM calls only for cache misses
        llm_targets = {
            rel_path: ents for rel_path, ents in file_entities.items()
            if rel_path not in cache_hit_paths
        }
        if llm_targets:
            logger.info("Cache MISS for %d files — calling LLM", len(llm_targets))

        # Track which files have valid cache entries (hits + successful writes)
        cached_paths: set[str] = set(cache_hit_paths)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(self._summarize_file, rel_path, ents, repo_path): rel_path
                for rel_path, ents in llm_targets.items()
            }
            for future in as_completed(futures):
                rel_path = futures[future]
                try:
                    result = future.result(timeout=60)
                    if result and rel_path in file_summaries:
                        fs = file_summaries[rel_path]
                        file_summaries[rel_path] = FileSummary(
                            file_path=fs.file_path,
                            language=fs.language,
                            line_count=fs.line_count,
                            summary=result.summary,
                            entity_count=fs.entity_count,
                            key_entities=result.key_entities,  # scored, not positional
                            exported_symbols=fs.exported_symbols,
                            dependencies=fs.dependencies,
                            nav_topic=result.nav_topic,
                            nav_role=result.nav_role,
                        )
                        # Persist to cache
                        if cache is not None:
                            content_hash = file_hashes.get(rel_path, "")
                            cache.put_file_summary(
                                rel_path,
                                _file_summary_to_dict(file_summaries[rel_path]),
                                content_hash=content_hash,
                                model=get_settings().llm_model,
                            )
                            cached_paths.add(rel_path)
                except Exception as exc:
                    logger.warning("LLM file summary failed for %s: %s", rel_path, exc)

        # Update manifest — only include files that have valid cache entries
        # to avoid marking failed LLM calls as cached.
        if cache is not None:
            manifest_hashes = {
                p: h for p, h in file_hashes.items() if p in cached_paths
            }
            try:
                cache.save_manifest({"file_hashes": manifest_hashes})
            except Exception as exc:
                logger.warning("Failed to save cache manifest: %s", exc)

        # ── Step 3: LLM directory summaries ───────────────────────────────────
        dir_groups: dict[str, list[str]] = {}
        for fp in file_summaries:
            for anc in self._ancestor_dirs(fp):
                dir_groups.setdefault(anc, []).append(fp)

        directory_summaries: dict[str, DirectorySummary] = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    self._summarize_directory_cached, dp, files, file_summaries,
                    file_hashes, cache, cache_reads_enabled,
                ): dp
                for dp, files in dir_groups.items()
            }
            for future in as_completed(futures):
                dp = futures[future]
                try:
                    ds = future.result(timeout=60)
                    if ds:
                        directory_summaries[dp] = ds
                except Exception as exc:
                    logger.warning("LLM dir summary failed for %s: %s", dp, exc)

        # ── Step 4: repo summary from all file summaries ──────────────────────
        repo_summary = self._generate_repo_summary(file_summaries, fingerprint, entities)

        key_entities = self._build_key_entities_list(scored, limit=50)
        call_graph = self._build_call_graph_text(entities)
        import_graph = self._build_import_graph_text(entities, repo_path)

        # ── Step 5: consolidate navigation from file/dir nav hints ────────────
        nav_plan = self._consolidate_navigation(
            file_summaries, directory_summaries, repo_summary,
            fingerprint.project_name or "project",
        )

        # Persist aggregated artifacts to cache
        if cache is not None:
            cache.put_top_entities(key_entities)
            cache.put_wiki_nav(nav_plan)

        return CompressedCodebase(
            repo_summary=repo_summary,
            file_summaries=file_summaries,
            directory_summaries=directory_summaries,
            key_entities=key_entities,
            call_graph_summary=call_graph,
            import_graph_summary=import_graph,
            compression_level="flat",
            nav_plan=nav_plan,
        )

    def _compress_pyramid(
        self,
        repo_path: str,
        entities: list[ParsedEntity],
        scored: list[ScoredEntity],
        fingerprint: RepoFingerprint,
        cache: Optional["IndexCache"] = None,
    ) -> CompressedCodebase:
        """3-level progressive rollup: file → directory → repo.

        Used for repos >= 1000 files where flat aggregation would overflow
        context when generating the repo summary.
        """
        from src.config import get_settings
        cache_reads_enabled = cache is not None and get_settings().index_cache_enabled

        # Level 0: file summaries
        file_entities: dict[str, list[ParsedEntity]] = {}
        for e in entities:
            rel = self._to_repo_relative(e.file_path, repo_path)
            if not rel:
                continue
            file_entities.setdefault(rel, []).append(e)

        # Compute content hashes for cache invalidation
        file_hashes: dict[str, str] = {}
        for rel_path in file_entities:
            full_path = Path(repo_path) / rel_path
            try:
                if full_path.is_file():
                    file_hashes[rel_path] = hashlib.sha256(
                        full_path.read_bytes()
                    ).hexdigest()
            except OSError:
                pass

        # Determine cache hits
        cache_hit_paths: set[str] = set()
        if cache_reads_enabled:
            diff = cache.diff_against_tree(file_hashes)
            cache_hit_paths = set(diff.hits)
            if diff.stale:
                cache.cleanup_stale(diff.stale)
            logger.info(
                "Pyramid cache diff: %d hits, %d misses, %d stale",
                len(diff.hits), len(diff.misses), len(diff.stale),
            )

        # Restore cached file summaries
        file_summaries: dict[str, FileSummary] = {}
        for rel_path in list(cache_hit_paths):
            if cache is not None:
                cached = cache.get_file_summary(rel_path)
                if cached:
                    logger.info("Cache HIT for %s", rel_path)
                    file_summaries[rel_path] = _dict_to_file_summary(cached)
                else:
                    cache_hit_paths.discard(rel_path)

        # LLM calls only for misses
        llm_targets = {
            fp: ents for fp, ents in file_entities.items()
            if fp not in cache_hit_paths
        }
        if llm_targets:
            logger.info("Cache MISS for %d files — calling LLM", len(llm_targets))

        # Track which files have valid cache entries (hits + successful writes)
        cached_paths: set[str] = set(cache_hit_paths)

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                pool.submit(self._summarize_file, fp, ents, repo_path): fp
                for fp, ents in llm_targets.items()
            }
            for future in as_completed(futures):
                fp = futures[future]
                try:
                    summary = future.result(timeout=30)
                    if summary:
                        file_summaries[fp] = summary
                        # Persist to cache
                        if cache is not None:
                            cache.put_file_summary(
                                fp,
                                _file_summary_to_dict(summary),
                                content_hash=file_hashes.get(fp, ""),
                                model=get_settings().llm_model,
                            )
                            cached_paths.add(fp)
                except Exception as exc:
                    logger.warning("File summary failed for %s: %s", fp, exc)

        # Update manifest — only include successfully cached files
        if cache is not None:
            manifest_hashes = {
                p: h for p, h in file_hashes.items() if p in cached_paths
            }
            try:
                cache.save_manifest({"file_hashes": manifest_hashes})
            except Exception as exc:
                logger.warning("Failed to save cache manifest: %s", exc)

        # Level 1: directory summaries
        dir_groups: dict[str, list[str]] = {}
        for fp in file_summaries:
            for anc in self._ancestor_dirs(fp):
                dir_groups.setdefault(anc, []).append(fp)

        dir_summaries: dict[str, DirectorySummary] = {}
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                pool.submit(
                    self._summarize_directory_cached, dp, files, file_summaries,
                    file_hashes, cache, cache_reads_enabled,
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
        import_graph = self._build_import_graph_text(entities, repo_path)

        # Consolidate navigation from file/dir nav hints
        nav_plan = self._consolidate_navigation(
            file_summaries, dir_summaries, repo_summary,
            fingerprint.project_name or "project",
        )

        # Persist aggregated artifacts to cache
        if cache is not None:
            cache.put_top_entities(key_entities)
            cache.put_wiki_nav(nav_plan)

        return CompressedCodebase(
            repo_summary=repo_summary,
            file_summaries=file_summaries,
            directory_summaries=dir_summaries,
            key_entities=key_entities,
            call_graph_summary=call_graph,
            import_graph_summary=import_graph,
            compression_level="pyramid",
            nav_plan=nav_plan,
        )

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _extract_file_metadata(
        self,
        entities: list[ParsedEntity],
        repo_path: str,
    ) -> dict[str, "FileSummary"]:
        """Extract structural metadata per file from AST — no LLM.

        Handles mixed absolute/relative file_path values across parsers.
        Summary prose is left as docstring placeholder; LLM replaces it later.
        key_entities are scored by interestingness, not positional.
        """
        from pathlib import Path as _Path

        file_entities: dict[str, list[ParsedEntity]] = {}
        for e in entities:
            rel = self._to_repo_relative(e.file_path, repo_path)
            if not rel:
                continue
            file_entities.setdefault(rel, []).append(e)

        lang_map = {".py": "Python", ".ts": "TypeScript", ".js": "JavaScript",
                    ".tsx": "TypeScript", ".jsx": "JavaScript", ".java": "Java",
                    ".go": "Go", ".rs": "Rust"}

        summaries: dict[str, FileSummary] = {}
        for rel_path, ents in file_entities.items():
            ext = _Path(rel_path).suffix
            language = lang_map.get(ext, ext.lstrip(".") or "unknown")

            # Line count from file on disk
            full_path = _Path(repo_path) / rel_path if repo_path else _Path(rel_path)
            line_count = 0
            try:
                if full_path.is_file():
                    line_count = sum(1 for _ in full_path.open(errors="replace"))
            except Exception:
                pass

            # Docstring placeholder — overwritten by LLM in compress steps
            top_ent = next((e for e in ents if e.docstring), None)
            summary = (top_ent.docstring or "").strip()[:300] if top_ent else ""

            exported_symbols = [
                e.name for e in ents
                if e.entity_type in ("class", "function", "variable")
                and e.name and not e.name.startswith("_")
            ]

            # Dependencies from module-level imports
            dependencies: list[str] = []
            module_ents = [e for e in ents if e.entity_type == "module"]
            if module_ents:
                seen_deps: set[str] = set()
                for imp in (module_ents[0].imports or []):
                    top = imp.split(".")[0] if imp else ""
                    if top and not top.startswith("_") and top not in seen_deps:
                        seen_deps.add(top)
                        dependencies.append(top)

            # Key entities: top 5 by interestingness score (not positional)
            scored_ents = score_entities(ents)
            key_ents = [se.entity.qualified_name for se in scored_ents[:5]]

            # Per-entity outbound calls (exclude self-calls and module-level noise)
            function_calls: dict[str, list[str]] = {}
            for e in ents:
                if e.entity_type == "module" or not e.calls:
                    continue
                # Keep up to 20 callees per entity; strip fully-qualified prefix noise
                short_callees = [c.split(".")[-1] if "." in c else c for c in e.calls[:20]]
                if short_callees:
                    function_calls[e.name] = short_callees

            summaries[rel_path] = FileSummary(
                file_path=rel_path,
                language=language,
                line_count=line_count,
                summary=summary,
                entity_count=len(ents),
                key_entities=key_ents,
                exported_symbols=exported_symbols[:30],
                dependencies=dependencies[:20],
                function_calls=function_calls,
            )
        return summaries

    def _extract_directory_metadata(
        self,
        file_summaries: dict[str, "FileSummary"],
    ) -> dict[str, "DirectorySummary"]:
        """Build DirectorySummary stubs per directory from file metadata — no LLM.

        Used as fallback when LLM directory summarization fails or is skipped.
        """
        from pathlib import Path as _Path

        dir_files: dict[str, list[str]] = {}
        for rel_path in file_summaries:
            parent = str(_Path(rel_path).parent)
            dir_files.setdefault(parent, []).append(rel_path)

        summaries: dict[str, DirectorySummary] = {}
        for dir_path, file_paths in dir_files.items():
            all_key_ents: list[str] = []
            for fp in file_paths:
                fs = file_summaries.get(fp)
                if fs:
                    all_key_ents.extend(fs.key_entities)

            child_files = [_Path(fp).name for fp in file_paths]

            summaries[dir_path] = DirectorySummary(
                dir_path=dir_path,
                file_count=len(file_paths),
                summary="",
                child_files=child_files,
                key_entities=list(dict.fromkeys(all_key_ents))[:10],
            )
        return summaries

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
            f"Analyze this {language} file. Return ONLY a JSON object:\n"
            f'{{"summary": "<100-150 word summary: purpose, design decisions, '
            f'error handling, integration>",\n'
            f' "nav_topic": "<2-4 word wiki section this file belongs to, '
            f'e.g. Agent Architecture, API Layer, Data Models>",\n'
            f' "nav_role": "<primary|supporting|config|test>"}}\n\n'
            f"File: {file_path}\n"
            f"Entities:\n{entity_text}\n\n"
            f"Code preview:\n{file_preview[:3000]}"
        )

        system_msg = (
            "You are a code analysis assistant. "
            "Respond with ONLY a valid JSON object — no explanation, "
            "no reasoning, no markdown, no preamble. "
            "Start your response with `{` and end with `}`."
        )

        nav_topic = ""
        nav_role = ""
        try:
            raw_response = chat(
                [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=600,
                temperature=0.1,
            )
            parsed = _extract_json_object(raw_response)
            if parsed and "summary" in parsed:
                summary = parsed["summary"]
                nav_topic = parsed.get("nav_topic") or ""
                nav_role = parsed.get("nav_role") or ""
            else:
                # JSON extraction failed — take first non-empty paragraph of
                # response (avoids storing an entire chain-of-thought blob).
                first_para = next(
                    (p.strip() for p in raw_response.split("\n\n") if p.strip()
                     and not p.strip().lower().startswith("here")),
                    "",
                )
                summary = first_para[:500] if first_para else ""
        except Exception as exc:
            logger.warning("LLM summary failed for %s: %s", file_path, exc)
            summary = file_entities[0].docstring or "" if file_entities else ""

        # Key entities: top 5 by interestingness score, not positional order
        scored_ents = score_entities(file_entities)
        key_ents = [se.entity.qualified_name for se in scored_ents[:5]]

        # Extract exported symbols (non-private names for classes, functions, variables)
        exported_symbols = [
            e.name for e in file_entities
            if e.entity_type in ("class", "function", "variable")
            and e.name and not e.name.startswith("_")
        ]

        # Extract dependencies from module-level imports
        dependencies: list[str] = []
        module_entities = [e for e in file_entities if e.entity_type == "module"]
        if module_entities:
            raw_imports = module_entities[0].imports or []
            # Normalize to top-level package name (e.g. "openai.types" → "openai")
            seen_deps: set[str] = set()
            for imp in raw_imports:
                top = imp.split(".")[0] if imp else ""
                if top and not top.startswith("_") and top not in seen_deps:
                    seen_deps.add(top)
                    dependencies.append(top)

        return FileSummary(
            file_path=file_path,
            language=language,
            line_count=line_count,
            summary=summary.strip(),
            entity_count=len(file_entities),
            key_entities=key_ents,
            exported_symbols=exported_symbols[:30],
            dependencies=dependencies[:20],
            nav_topic=nav_topic.strip(),
            nav_role=nav_role.strip(),
        )

    def _summarize_directory_cached(
        self,
        dir_path: str,
        child_files: list[str],
        file_summaries: dict[str, FileSummary],
        file_hashes: dict[str, str],
        cache: Optional["IndexCache"],
        cache_reads_enabled: bool,
    ) -> Optional[DirectorySummary]:
        """Cache-aware wrapper around ``_summarize_directory``.

        Checks cache first (if enabled), delegates to LLM on miss, and
        persists the result back to cache.
        """
        # Build child hash fingerprint for this directory
        child_hashes = {fp: file_hashes.get(fp, "") for fp in child_files}
        composite_hash = hashlib.sha256(
            json.dumps(child_hashes, sort_keys=True).encode()
        ).hexdigest()

        if cache_reads_enabled and cache is not None:
            cached = cache.get_dir_summary(dir_path)
            if cached:
                cached_meta = cached.get("_cache_meta", {})
                if cached_meta.get("content_hash") == composite_hash:
                    logger.info("Cache HIT for dir %s", dir_path)
                    return DirectorySummary(
                        dir_path=cached.get("dir_path", dir_path),
                        file_count=cached.get("file_count", len(child_files)),
                        summary=cached.get("summary", ""),
                        child_files=cached.get("child_files", child_files),
                        key_entities=cached.get("key_entities", []),
                        nav_items=cached.get("nav_items", []),
                    )

        logger.info("Cache MISS for dir %s — calling LLM", dir_path)
        result = self._summarize_directory(dir_path, child_files, file_summaries)
        if result and cache is not None:
            try:
                from src.config import get_settings
                cache.put_dir_summary(
                    dir_path,
                    _dir_summary_to_dict(result),
                    child_hashes=child_hashes,
                    model=get_settings().llm_model,
                )
            except Exception as exc:
                logger.warning("Cache write failed for dir %s: %s", dir_path, exc)
        return result

    def _summarize_directory(
        self,
        dir_path: str,
        child_files: list[str],
        file_summaries: dict[str, FileSummary],
    ) -> Optional[DirectorySummary]:
        """1 LLM call → directory summary + nav_items."""
        file_summary_lines = []
        all_key_entities: list[str] = []
        for fp in child_files:
            fs = file_summaries.get(fp)
            if fs:
                nav_tag = f" [nav: {fs.nav_topic}]" if fs.nav_topic else ""
                file_summary_lines.append(f"  - {fp}{nav_tag}: {fs.summary}")
                all_key_entities.extend(fs.key_entities)

        # Detect child subdirectories from file paths
        child_dirs: set[str] = set()
        prefix = dir_path.rstrip("/") + "/"
        for fp in file_summaries:
            if fp.startswith(prefix):
                remainder = fp[len(prefix):]
                if "/" in remainder:
                    child_dirs.add(remainder.split("/")[0])

        child_dir_note = ""
        if child_dirs:
            child_dir_note = f"\nSubdirectories: {', '.join(sorted(child_dirs))}\n"

        prompt = (
            f"Analyze this directory. Return ONLY a JSON object:\n"
            f'{{"summary": "<200-250 word summary: purpose, patterns, '
            f'file relationships, integration points>",\n'
            f' "nav_items": [{{"section": "<proposed wiki section title>", '
            f'"subsections": ["<sub1>", "<sub2>"], '
            f'"importance": "<core|supporting|peripheral>", '
            f'"seed_files": ["<top file1>", "<top file2>"]}}]}}\n\n'
            f"Directory: {dir_path}\n"
            f"{child_dir_note}"
            f"Files:\n" + "\n".join(file_summary_lines)
        )

        nav_items: list[dict] = []
        try:
            raw_response = chat(
                [{"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=0.1,
            )
            parsed = _extract_json_object(raw_response)
            if parsed and "summary" in parsed:
                summary = parsed["summary"] or raw_response
                nav_items = parsed.get("nav_items") or []
                if not isinstance(nav_items, list):
                    nav_items = []
            else:
                # Fallback: strip markdown fences so raw JSON doesn't leak as summary
                cleaned = raw_response.strip()
                if cleaned.startswith("```"):
                    cleaned = "\n".join(
                        line for line in cleaned.splitlines()
                        if not line.strip().startswith("```")
                    ).strip()
                summary = cleaned
        except Exception as exc:
            logger.warning("LLM dir summary failed for %s: %s", dir_path, exc)
            summary = f"Contains {len(child_files)} files."

        return DirectorySummary(
            dir_path=dir_path,
            file_count=len(child_files),
            summary=summary.strip(),
            child_files=child_files,
            key_entities=all_key_entities[:10],
            nav_items=nav_items,
        )

    def _generate_repo_summary(
        self,
        file_summaries: dict[str, FileSummary],
        fingerprint: RepoFingerprint,
        entities: list[ParsedEntity],
    ) -> str:
        """Single LLM call: aggregate file summaries into repo overview."""
        summary_lines = []
        budget = min(len(file_summaries), max(50, min(120, fingerprint.file_count // 10)))
        sampled = self._stratified_file_sample(file_summaries, budget)
        for fp, fs in sampled:
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

    def _build_import_graph_text(self, entities: list[ParsedEntity], repo_path: str = "") -> str:
        """Build text representation of import graph with relative file paths."""
        import os as _os
        imports: list[str] = []
        seen: set[str] = set()
        abs_prefix = _os.path.abspath(repo_path).rstrip("/") + "/" if repo_path else ""
        rel_prefix = repo_path.rstrip("/") + "/" if repo_path else ""

        def _to_rel(fp: str) -> str:
            if abs_prefix and fp.startswith(abs_prefix):
                return fp[len(abs_prefix):]
            if rel_prefix and fp.startswith(rel_prefix):
                return fp[len(rel_prefix):]
            return fp

        for e in entities:
            rel = _to_rel(e.file_path)
            for imp in e.imports:
                key = f"{rel} imports {imp}"
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

    def _consolidate_navigation(
        self,
        file_summaries: dict[str, FileSummary],
        directory_summaries: dict[str, DirectorySummary],
        repo_summary: str,
        repo_name: str,
    ) -> dict:
        """One LLM call: merge all nav hints into a consolidated navigation plan.

        Input: all dir nav_items + file topic distribution.
        Output: dict with sections for WikiNav consumption.
        """
        # Build topic distribution from file nav_topics
        topic_counter: Counter = Counter()
        for fs in file_summaries.values():
            if fs.nav_topic:
                topic_counter[fs.nav_topic] += 1

        topic_lines = [
            f"- {topic}: {count} files"
            for topic, count in topic_counter.most_common(40)
        ]

        # Collect dir nav_items (sanitize LLM output)
        dir_nav_lines: list[str] = []
        for dp in sorted(directory_summaries):
            ds = directory_summaries[dp]
            for item in ds.nav_items:
                if not isinstance(item, dict):
                    continue
                section = item.get("section", "")
                if not section:
                    continue
                raw_subs = item.get("subsections") or []
                subs = ", ".join(str(s) for s in raw_subs if s) if isinstance(raw_subs, list) else ""
                importance = item.get("importance", "supporting")
                raw_seeds = item.get("seed_files") or []
                seeds = ", ".join(str(s) for s in raw_seeds[:5]) if isinstance(raw_seeds, list) else ""
                dir_nav_lines.append(
                    f"- {dp}/ ({importance}): \"{section}\" → [{subs}] "
                    f"(seeds: {seeds})"
                )

        # Build file tree for hierarchy reconstruction
        all_dirs: set[str] = set()
        for fp in file_summaries:
            parts = Path(fp).parts
            for i in range(1, len(parts)):
                all_dirs.add("/".join(parts[:i]))
        tree_lines = [f"  {d}/" for d in sorted(all_dirs)]

        if not dir_nav_lines and not topic_lines:
            logger.info("No nav hints collected — using structural fallback")
            return self._structural_nav_fallback(
                file_summaries, directory_summaries, repo_name
            )

        prompt = (
            f"You are organizing a code wiki's navigation. Below are navigation "
            f"items extracted from every directory and file in the repository.\n"
            f"Produce the FINAL navigation structure: merge duplicates, establish "
            f"hierarchy, remove peripheral topics.\n\n"
            f"## Repository: {repo_name}\n\n"
            f"## Summary\n{repo_summary[:500]}\n\n"
            f"## Directory Tree\n" + "\n".join(tree_lines[:80]) + "\n\n"
            f"## Directory Navigation Proposals\n"
            + "\n".join(dir_nav_lines) + "\n\n"
            f"## File Topic Distribution\n"
            + "\n".join(topic_lines) + "\n\n"
            f"## Instructions\n"
            f"1. Merge overlapping sections from different directories\n"
            f"2. Nest subsections under parent sections using path hierarchy\n"
            f"3. Drop peripheral topics with <2 files (unless architecturally significant)\n"
            f"4. Order for learning: overview → architecture → core → supporting → reference\n"
            f"5. Every section needs at least 2 seed_files\n"
            f"6. First section MUST be type=home (project overview)\n\n"
            f"Return ONLY JSON:\n"
            f'{{"sections": [{{"slug": "url-slug", "title": "Section Title", '
            f'"type": "concept|architecture|workflow|reference|home", '
            f'"subsections": ["Sub 1"], "seed_files": ["path/file.py"], '
            f'"importance": "core|supporting"}}]}}'
        )

        try:
            raw = chat(
                [{"role": "user", "content": prompt}],
                max_tokens=4000,
                temperature=0.2,
            )
            parsed = _extract_json_object(raw)
            if parsed and "sections" in parsed:
                logger.info(
                    "Nav consolidation produced %d sections",
                    len(parsed["sections"]),
                )
                return parsed
            logger.warning("Nav consolidation returned invalid JSON, using structural fallback")
            return self._structural_nav_fallback(
                file_summaries, directory_summaries, repo_name
            )
        except Exception as exc:
            logger.warning("Nav consolidation LLM call failed: %s", exc)
            return self._structural_nav_fallback(
                file_summaries, directory_summaries, repo_name
            )

    def _structural_nav_fallback(
        self,
        file_summaries: dict[str, FileSummary],
        directory_summaries: dict[str, DirectorySummary],
        repo_name: str,
    ) -> dict:
        """Deterministic nav skeleton from directory/file structure (no LLM)."""
        if not file_summaries and not directory_summaries:
            return {
                "sections": [
                    {
                        "slug": "overview",
                        "title": "Overview",
                        "type": "home",
                        "subsections": [],
                        "seed_files": [],
                        "importance": "core",
                    }
                ]
            }

        top_files: dict[str, list[str]] = {}
        for fp in sorted(file_summaries):
            top = self._top_level_dir(fp)
            top_files.setdefault(top, []).append(fp)

        ranked = sorted(
            top_files.items(),
            key=lambda kv: len(kv[1]),
            reverse=True,
        )
        if not ranked and directory_summaries:
            for dp in sorted(directory_summaries):
                top = self._top_level_dir(dp, assume_directory=True)
                top_files.setdefault(top, [])
            ranked = sorted(top_files.items(), key=lambda kv: kv[0])

        sections: list[dict] = [
            {
                "slug": "overview",
                "title": "Overview",
                "type": "home",
                "subsections": [],
                "seed_files": [],
                "importance": "core",
            }
        ]
        max_count = max((len(files) for _, files in ranked), default=1)
        for top, files in ranked:
            if top == ".":
                title = "Root Files"
                slug = "root-files"
            else:
                title = f"{top} Subsystem"
                slug = re.sub(r"[^a-z0-9]+", "-", top.lower()).strip("-") or "section"
            importance = "core" if len(files) >= max(5, max_count // 2) else "supporting"
            sections.append(
                {
                    "slug": slug,
                    "title": title,
                    "type": "architecture" if importance == "core" else "concept",
                    "subsections": [],
                    "seed_files": files[:5],
                    "importance": importance,
                }
            )

        logger.info(
            "Structural nav fallback produced %d sections", len(sections)
        )
        return {"sections": sections}
