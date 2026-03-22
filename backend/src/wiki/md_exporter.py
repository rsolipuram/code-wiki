"""Markdown artifact exporter — writes pipeline artifacts to disk.

After wiki generation, this module writes all intermediate artifacts as
human-readable Markdown files in a folder tree that **mirrors the analyzed
repository's structure**. This lets you browse the summaries alongside the
source they describe.

Output layout (relative to wiki_artifacts_dir):
    {repo_name}/
      _meta/
        domain_entities.json      # LLM domain recon output
        architecture_model.json   # ARCHITECT output
        wiki_plan.json            # PLANNER output
        critic_result.json        # CRITIC quality gate result
      summaries/
        _repo_summary.md          # Top-level repo overview
        {file_path}.md            # One .md per source file (mirrors repo tree)
        {dir_path}/_dir_summary.md  # Directory-level rollup
      pages/
        {slug}.md                 # Rendered wiki pages as Markdown
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
        _write_summaries(root, compressed)
    except Exception as exc:
        logger.warning("MD export: summaries write failed: %s", exc)

    try:
        _write_pages(root, rendered_pages)
    except Exception as exc:
        logger.warning("MD export: pages write failed: %s", exc)

    logger.info("MD export: artifacts written to %s", root)
    return root


# ── _meta ────────────────────────────────────────────────────────────────────

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


# ── summaries ────────────────────────────────────────────────────────────────

def _write_summaries(root: Path, compressed: dict) -> None:
    summaries_dir = root / "summaries"
    summaries_dir.mkdir(exist_ok=True)

    # Top-level repo summary
    repo_summary = compressed.get("repo_summary", "")
    if repo_summary:
        _safe_write(summaries_dir / "_repo_summary.md", f"# Repository Overview\n\n{repo_summary}\n")

    # Per-file summaries — mirror the repo tree
    file_summaries: dict[str, dict] = compressed.get("file_summaries") or {}
    for rel_path, fs in file_summaries.items():
        if isinstance(fs, dict):
            _write_file_summary_md(summaries_dir, rel_path, fs)

    # Per-directory summaries
    dir_summaries: dict[str, dict] = compressed.get("directory_summaries") or {}
    for dir_path, ds in dir_summaries.items():
        if isinstance(ds, dict):
            _write_dir_summary_md(summaries_dir, dir_path, ds)


def _write_file_summary_md(summaries_dir: Path, rel_path: str, fs: dict) -> None:
    """Write one .md file for a source file summary, preserving directory structure."""
    # Convert rel_path like "airline/agents.py" → summaries_dir/airline/agents.md
    p = Path(rel_path)
    out_path = summaries_dir / p.parent / (p.stem + ".md")
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


def _write_dir_summary_md(summaries_dir: Path, dir_path: str, ds: dict) -> None:
    """Write _dir_summary.md for a directory."""
    out_path = summaries_dir / dir_path / "_dir_summary.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    file_count = ds.get("file_count", 0)
    summary = ds.get("summary", "")
    child_files = ds.get("child_files") or []
    key_entities = ds.get("key_entities") or []

    lines = [
        f"# `{dir_path}/` — Directory Summary",
        "",
        f"**Files**: {file_count}",
        "",
    ]

    if summary:
        lines += ["## Overview", "", summary, ""]

    if child_files:
        lines += ["## Files", ""]
        for f in child_files:
            lines.append(f"- `{f}`")
        lines.append("")

    if key_entities:
        lines += ["## Key Entities", ""]
        for qname in key_entities:
            lines.append(f"- `{qname}`")
        lines.append("")

    _safe_write(out_path, "\n".join(lines))


# ── pages ────────────────────────────────────────────────────────────────────

def _write_pages(root: Path, rendered_pages: list[dict[str, Any]]) -> None:
    """Write rendered wiki pages as .md files."""
    pages_dir = root / "pages"
    pages_dir.mkdir(exist_ok=True)

    for page in rendered_pages:
        slug = page.get("slug", "unknown")
        title = page.get("title", slug)
        content = page.get("content")

        md_text = _render_page_as_markdown(title, content)
        _safe_write(pages_dir / f"{slug}.md", md_text)


def _render_page_as_markdown(title: str, content: Any) -> str:
    """Convert a rendered page content dict to Markdown text."""
    lines = [f"# {title}", ""]

    if not isinstance(content, dict):
        if content:
            lines.append(str(content))
        return "\n".join(lines)

    page_type = content.get("page_type", "")

    # Top-level diagrams — HOME ONLY. Section pages have diagrams already interleaved
    # into prose_segments by the assembler; rendering content["diagrams"] there would
    # duplicate every diagram.
    for diag in (content.get("diagrams") or []) if page_type == "home" else []:
        if not isinstance(diag, dict):
            continue
        mermaid_src = diag.get("mermaid_source", "")
        caption = diag.get("caption", "")
        if mermaid_src:
            lines += ["```mermaid", mermaid_src, "```", ""]
        if caption:
            lines += [f"*{caption}*", ""]

    # Prose segments
    prose_segments = content.get("prose_segments") or []
    for seg in prose_segments:
        if not isinstance(seg, dict):
            lines += [str(seg), ""]
            continue
        seg_type = seg.get("type", "text")
        if seg_type == "heading":
            level = seg.get("level", 2)
            text = seg.get("text", "")
            lines += ["#" * level + f" {text}", ""]
        elif seg_type == "text":
            lines += [seg.get("content", ""), ""]
        elif seg_type == "diagram":
            src = seg.get("mermaid_source", "")
            caption = seg.get("caption", "")
            if src:
                lines += ["```mermaid", src, "```", ""]
            if caption:
                lines += [f"*{caption}*", ""]
        elif seg_type == "code_block":
            lang = seg.get("language", "")
            code = seg.get("code", "")
            fp = seg.get("file_path", "")
            if fp:
                lines += [f"**`{fp}`**", ""]
            lines += [f"```{lang}", code, "```", ""]
        elif seg_type in ("source_link", "section_link"):
            text = seg.get("text", "") or seg.get("entity_name", "")
            url = seg.get("url", "")
            if url and text:
                lines += [f"[{text}]({url})", ""]
            elif text:
                lines += [text, ""]

    # Tables
    tables = content.get("tables") or []
    for tbl in tables:
        if not isinstance(tbl, dict):
            continue
        headers = tbl.get("headers") or []
        rows = tbl.get("rows") or []
        if headers:
            lines += ["| " + " | ".join(str(h) for h in headers) + " |"]
            lines += ["| " + " | ".join(["---"] * len(headers)) + " |"]
            for row in rows:
                if isinstance(row, (list, tuple)):
                    lines += ["| " + " | ".join(str(c) for c in row) + " |"]
            lines += [""]

    return "\n".join(lines)


# ── helpers ──────────────────────────────────────────────────────────────────

def _safe_write(path: Path, content: str) -> None:
    """Write content to path, creating parent directories as needed."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except Exception as exc:
        logger.warning("MD export: failed to write %s: %s", path, exc)
