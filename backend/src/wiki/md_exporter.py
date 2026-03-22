"""Markdown artifact exporter — writes pipeline artifacts to disk.

After wiki generation, this module writes all intermediate artifacts as
human-readable Markdown files in a folder tree that **directly mirrors the
analyzed repository's structure**. No wrapper subdirectories.

Output layout (relative to wiki_artifacts_dir):
    {repo_name}/
      _repo.md                      # Top-level repo overview
      _compressor.md                # Full compressor dump (call graph, import graph, all file stats)
      {dir}/
        _dir.md                     # Directory rollup
        {file}.md                   # One .md per source file (mirrors repo tree exactly)
      _meta/
        domain_entities.json        # LLM domain recon output
        architecture_model.json     # ARCHITECT output
        wiki_plan.json              # PLANNER output
        critic_result.json          # CRITIC quality gate result
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def export_wiki_artifacts(
    repo_name: str,
    wiki_artifacts_dir: str,
    compressed: dict,
    domain_entities: dict,
    architecture: dict,
    plan: dict,
    critic_result: dict,
    rendered_pages: list[dict[str, Any]],
) -> Path:
    """Write all wiki pipeline artifacts to disk.

    Args:
        repo_name:           Human-readable repo name (used as the top-level directory).
        wiki_artifacts_dir:  Root output directory (e.g. "./cache/wiki_artifacts").
        compressed:          CompressedCodebase serialized as dict.
        domain_entities:     LLM domain recon output (agents, tools, guardrails).
        architecture:        ARCHITECT output dict.
        plan:                PLANNER output dict (WikiPlan).
        critic_result:       CRITIC result dict.
        rendered_pages:      Final rendered pages list (each with slug, title, content).

    Returns:
        Path to the repo-level output directory.
    """
    safe_name = re.sub(r"[^\w\-]", "_", repo_name)
    root = Path(wiki_artifacts_dir) / safe_name
    root.mkdir(parents=True, exist_ok=True)

    try:
        _write_meta(root, domain_entities, architecture, plan, critic_result)
    except Exception as exc:
        logger.warning("MD export: _meta write failed: %s", exc)

    try:
        _write_repo_tree(root, compressed)
    except Exception as exc:
        logger.warning("MD export: repo tree write failed: %s", exc)

    try:
        _write_compressor_dump(root, compressed)
    except Exception as exc:
        logger.warning("MD export: compressor dump write failed: %s", exc)

    logger.info("MD export: artifacts written to %s", root)
    return root


# ── _meta ─────────────────────────────────────────────────────────────────────

def _write_meta(
    root: Path,
    domain_entities: dict,
    architecture: dict,
    plan: dict,
    critic_result: dict,
) -> None:
    meta_dir = root / "_meta"
    meta_dir.mkdir(exist_ok=True)

    def _dump(name: str, data: Any) -> None:
        (meta_dir / name).write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    _dump("domain_entities.json", domain_entities)
    _dump("architecture_model.json", architecture)
    _dump("wiki_plan.json", plan)
    _dump("critic_result.json", critic_result)


# ── repo tree (direct mirror) ─────────────────────────────────────────────────

def _write_repo_tree(root: Path, compressed: dict) -> None:
    """Write _repo.md, per-file .md files, and _dir.md rollups directly at the
    mirrored repo path — no wrapper subdirectory."""

    # _repo.md at root
    repo_summary = compressed.get("repo_summary", "")
    if repo_summary:
        _safe_write(root / "_repo.md", f"# Repository Overview\n\n{repo_summary}\n")

    # Per-file summaries — directly at root/{rel_path}.md
    file_summaries: dict[str, dict] = compressed.get("file_summaries") or {}
    for rel_path, fs in file_summaries.items():
        if isinstance(fs, dict):
            _write_file_summary_md(root, rel_path, fs)

    # Per-directory rollups — directly at root/{dir_path}/_dir.md
    dir_summaries: dict[str, dict] = compressed.get("directory_summaries") or {}
    for dir_path, ds in dir_summaries.items():
        if isinstance(ds, dict):
            _write_dir_md(root, dir_path, ds)


def _write_file_summary_md(root: Path, rel_path: str, fs: dict) -> None:
    """Write one .md file at root/{dir}/{stem}.md — directly mirrors the repo tree."""
    p = Path(rel_path)
    out_path = root / p.parent / (p.stem + ".md")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    language = fs.get("language", "")
    line_count = fs.get("line_count", 0)
    summary = fs.get("summary", "")
    entity_count = fs.get("entity_count", 0)
    exported_symbols = fs.get("exported_symbols") or []
    dependencies = fs.get("dependencies") or []
    key_entities = fs.get("key_entities") or []

    lines = [
        f"# `{rel_path}`",
        "",
        f"**Language**: {language} | **Lines**: {line_count} | **Entities**: {entity_count}",
        "",
    ]

    if summary:
        lines += ["## Summary", "", summary, ""]

    if exported_symbols:
        symbols_str = ", ".join(f"`{s}`" for s in exported_symbols)
        lines += ["## Exported Symbols", "", symbols_str, ""]

    if dependencies:
        deps_str = ", ".join(f"`{d}`" for d in dependencies)
        lines += ["## Dependencies", "", deps_str, ""]

    if key_entities:
        lines += ["## Key Entities", ""]
        for qname in key_entities:
            lines.append(f"- `{qname}`")
        lines.append("")

    _safe_write(out_path, "\n".join(lines))


def _write_dir_md(root: Path, dir_path: str, ds: dict) -> None:
    """Write _dir.md at root/{dir_path}/_dir.md."""
    out_path = root / dir_path / "_dir.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    file_count = ds.get("file_count", 0)
    summary = ds.get("summary", "")
    child_files = ds.get("child_files") or []
    key_entities = ds.get("key_entities") or []

    lines = [
        f"# `{dir_path}/`",
        "",
        f"**Files**: {file_count}",
        "",
    ]

    if summary:
        lines += ["## Overview", "", summary, ""]

    if child_files:
        lines += ["## Files", ""]
        for f in child_files:
            lines.append(f"- [`{f}`]({f.split('/')[-1].rsplit('.', 1)[0] + '.md'})")
        lines.append("")

    if key_entities:
        lines += ["## Key Entities", ""]
        for qname in key_entities:
            lines.append(f"- `{qname}`")
        lines.append("")

    _safe_write(out_path, "\n".join(lines))


# ── compressor dump ───────────────────────────────────────────────────────────

def _write_compressor_dump(root: Path, compressed: dict) -> None:
    """Write _compressor.md — full dump of everything the compressor produced."""
    lines = ["# Compressor Output Dump", ""]

    compression_level = compressed.get("compression_level", "unknown")
    lines += [f"**Compression level**: `{compression_level}`", ""]

    # Call graph summary
    cg = compressed.get("call_graph_summary", "")
    if cg:
        lines += ["## Call Graph Summary", "", cg, ""]

    # Import graph summary
    ig = compressed.get("import_graph_summary", "")
    if ig:
        lines += ["## Import Graph Summary", "", ig, ""]

    # Key entities
    key_entities = compressed.get("key_entities") or []
    if key_entities:
        lines += ["## Key Entities (Ranked by Centrality)", ""]
        for i, qname in enumerate(key_entities[:50], 1):
            lines.append(f"{i}. `{qname}`")
        lines.append("")

    # File summary table
    file_summaries: dict[str, dict] = compressed.get("file_summaries") or {}
    if file_summaries:
        lines += [
            "## File Summaries",
            "",
            "| File | Language | Lines | Entities | Exported Symbols | Dependencies |",
            "|------|----------|-------|----------|------------------|--------------|",
        ]
        for rel_path, fs in sorted(file_summaries.items()):
            if not isinstance(fs, dict):
                continue
            lang = fs.get("language", "")
            lc = fs.get("line_count", 0)
            ec = fs.get("entity_count", 0)
            syms = ", ".join(f"`{s}`" for s in (fs.get("exported_symbols") or [])[:5])
            deps = ", ".join(f"`{d}`" for d in (fs.get("dependencies") or [])[:5])
            lines.append(f"| `{rel_path}` | {lang} | {lc} | {ec} | {syms} | {deps} |")
        lines.append("")

    # Per-file detail blocks
    lines += ["## File Details", ""]
    for rel_path, fs in sorted(file_summaries.items()):
        if not isinstance(fs, dict):
            continue
        summary = fs.get("summary", "")
        key_ents = fs.get("key_entities") or []
        if not summary and not key_ents:
            continue
        lines += [f"### `{rel_path}`", ""]
        if summary:
            lines += [summary, ""]
        if key_ents:
            lines += ["**Key entities**: " + ", ".join(f"`{q}`" for q in key_ents), ""]

    # Directory summaries
    dir_summaries: dict[str, dict] = compressed.get("directory_summaries") or {}
    if dir_summaries:
        lines += ["## Directory Summaries", ""]
        for dir_path, ds in sorted(dir_summaries.items()):
            if not isinstance(ds, dict):
                continue
            summary = ds.get("summary", "")
            fc = ds.get("file_count", 0)
            lines += [f"### `{dir_path}/` ({fc} files)", ""]
            if summary:
                lines += [summary, ""]

    _safe_write(root / "_compressor.md", "\n".join(lines))


# ── helpers ───────────────────────────────────────────────────────────────────

def _safe_write(path: Path, content: str) -> None:
    """Write content to path, creating parent directories as needed."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except Exception as exc:
        logger.warning("MD export: failed to write %s: %s", path, exc)
