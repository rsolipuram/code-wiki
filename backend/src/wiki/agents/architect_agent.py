"""ARCHITECT agent — creates shared codebase understanding.

Produces an ArchitectureModel that all downstream agents reference.
Uses the FULL compressed codebase context (repo_summary, file summaries,
directory summaries, key entities, call graph, dossier findings).
"""

import json
import logging
import time
from pathlib import Path

from src.config import get_settings
from src.llm.client import chat
from src.wiki.agents.graph import report_agent_progress
from src.wiki.agents.state import ArchitectureModel, WikiState

logger = logging.getLogger(__name__)

ARCHITECT_SYSTEM_PROMPT = """You are a senior software architect analyzing a codebase to create structured documentation.

Your task is to produce a JSON ArchitectureModel that captures the codebase's logical structure.
This model will be used by downstream agents to plan wiki sections, write prose, generate diagrams, and build tables.

You must output ONLY valid JSON with this exact structure:
{
  "layers": [
    {"name": "Layer Name", "purpose": "What this layer does", "key_files": ["path/to/file.py"], "key_entities": ["module.ClassName"]}
  ],
  "components": [
    {
      "name": "Component Name",
      "purpose": "1-2 sentence description of what this component does and WHY it exists",
      "public_interfaces": ["module.ClassName.method"],
      "dependencies": ["Other Component Name"],
      "files": ["path/to/file.py"]
    }
  ],
  "data_flows": [
    {"source": "Component A", "destination": "Component B", "description": "What data flows and why"}
  ],
  "key_abstractions": ["Core concept 1", "Core concept 2"],
  "diagram_spec": {
    "overview": {
      "nodes": [{"id": "comp_name", "label": "Human Readable Name"}],
      "edges": [{"from": "comp_a", "to": "comp_b", "label": "description"}]
    }
  },
  "component_map": {
    "path/to/file.py": "Component Name"
  }
}

CRITICAL RULES:
- Components are CODE modules — groups of source files that implement a feature or subsystem
- Every component MUST have at least 1 file in its "files" list — components with 0 files are INVALID
- The "files" list must contain EXACT, ABSOLUTE file paths from the source file list provided (copy-paste exact paths including /Users/ranjit/...)
- Do NOT truncate or modify the file paths in any way
- Do NOT create abstract/conceptual components like "Roadmap", "FAQ", "Support Policy", "Glossary", "Testing Strategy", etc.
- Do NOT create documentation-oriented sections — create CODE-oriented components
- Every source file from the provided list must appear in exactly one component's files list AND in component_map

Guidelines:
- Identify 5-15 logical components based on how a developer thinks about the system
- Group files by what they DO together, not by directory structure alone
- Use human-readable names (e.g., "Agent Orchestration" not "src_agents")
- public_interfaces should include specific method signatures and class names
- data_flows should capture major data pipelines (aim for 5-15 flows)
- key_abstractions are concepts someone needs to understand this codebase (aim for 8-15)
- diagram_spec.overview should have nodes for each component with clear labels
- Include design patterns detected (e.g., Observer, Factory, Strategy, Pipeline)"""


def architect_node(state: WikiState) -> dict:
    """ARCHITECT node — analyze codebase and produce ArchitectureModel."""
    t0 = time.monotonic()
    logger.info("ARCHITECT agent starting")
    report_agent_progress("architect", "running", "Analyzing codebase structure")

    # Build comprehensive context from state
    compressed = state.get("compressed", {})
    entity_index = state.get("entity_index", {})
    call_graph = state.get("call_graph", {})
    scored_entities = state.get("scored_entities", [])
    all_files = state.get("all_files", [])
    fingerprint = state.get("fingerprint", {})
    dossier = state.get("dossier", {})

    # Assemble context sections
    context_parts = []

    # 1. Repo summary
    repo_summary = compressed.get("repo_summary", "")
    if repo_summary:
        context_parts.append(f"## Repository Overview\n{repo_summary}")

    # 2. Directory summaries
    dir_summaries = compressed.get("directory_summaries", {})
    if dir_summaries:
        dir_lines = []
        for path, ds in sorted(dir_summaries.items()):
            summary = ds.get("summary", "") if isinstance(ds, dict) else str(ds)
            file_count = ds.get("file_count", 0) if isinstance(ds, dict) else 0
            dir_lines.append(f"  {path}/ ({file_count} files): {summary}")
        context_parts.append(
            f"## Directory Structure\n" + "\n".join(dir_lines[:30])
        )

    # 3. File summaries (include exported_symbols so architect knows what each file exposes)
    file_summaries = compressed.get("file_summaries", {})
    if file_summaries:
        file_lines = []
        for path, fs in sorted(file_summaries.items()):
            if isinstance(fs, dict):
                summary = fs.get("summary", "")
                symbols = fs.get("exported_symbols", [])
                deps = fs.get("dependencies", [])
                symbols_str = f"  exports=[{', '.join(symbols[:8])}]" if symbols else ""
                deps_str = f"  deps=[{', '.join(deps[:6])}]" if deps else ""
                file_lines.append(f"  {path}: {summary}{symbols_str}{deps_str}")
            else:
                file_lines.append(f"  {path}: {fs}")
        context_parts.append(
            f"## File Summaries ({len(file_summaries)} files)\n"
            + "\n".join(file_lines[:50])
        )

    # 4. Key entities with scores
    if scored_entities:
        entity_lines = []
        for se in scored_entities[:50]:
            if isinstance(se, dict):
                qn = se.get("qualified_name", se.get("name", "?"))
                score = se.get("score", 0)
                etype = se.get("entity_type", "")
                entity_lines.append(f"  {qn} ({etype}, score={score})")
            else:
                entity_lines.append(f"  {se}")
        context_parts.append(
            f"## Key Entities (top {len(entity_lines)})\n"
            + "\n".join(entity_lines)
        )

    # 5. Call graph summary
    cg_summary = compressed.get("call_graph_summary", "")
    if cg_summary:
        context_parts.append(f"## Call Graph\n{cg_summary}")

    # 6. Hub analysis from call graph
    if call_graph:
        # Find high-degree nodes
        callee_count: dict[str, int] = {}
        for caller, callees in call_graph.items():
            for callee in callees:
                callee_count[callee] = callee_count.get(callee, 0) + 1
        hubs = sorted(callee_count.items(), key=lambda x: x[1], reverse=True)[:15]
        if hubs:
            hub_lines = [f"  {qn} (called by {count} entities)" for qn, count in hubs]
            context_parts.append(
                f"## Hub Entities (most called)\n" + "\n".join(hub_lines)
            )

    # 7. All source files
    if all_files:
        context_parts.append(
            f"## All Source Files ({len(all_files)})\n"
            + "\n".join(f"  {f}" for f in all_files[:100])
        )

    # 8. Dossier architecture findings
    if dossier:
        arch = dossier.get("architecture", {})
        if arch:
            style = arch.get("primary_style", "")
            patterns = arch.get("patterns_detected", [])
            if style:
                context_parts.append(
                    f"## Architecture Analysis\nStyle: {style}\n"
                    f"Patterns: {', '.join(patterns[:10])}"
                )

    # 9. Fingerprint metadata
    if fingerprint:
        fp_info = []
        for key in ("system_type", "primary_language", "file_count", "loc"):
            val = fingerprint.get(key)
            if val:
                fp_info.append(f"{key}: {val}")
        if fp_info:
            context_parts.append(
                f"## Project Metadata\n" + "\n".join(fp_info)
            )

    full_context = "\n\n".join(context_parts)
    max_context_chars = max(8000, get_settings().architect_context_max_chars)
    if len(full_context) > max_context_chars:
        logger.info(
            "ARCHITECT context capped from %d to %d chars",
            len(full_context),
            max_context_chars,
        )
        full_context = full_context[:max_context_chars]

    prompt = f"""Analyze this codebase and produce a JSON ArchitectureModel.

{full_context}

Remember: Output ONLY valid JSON matching the ArchitectureModel schema.
Every source file must be mapped to a component in component_map.
Use human-readable component names."""

    try:
        response = chat(
            [
                {"role": "system", "content": ARCHITECT_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=8000,
            temperature=0.2,
            cache_ttl=3600,
        )

        architecture = _parse_architecture_response(response, all_files, state.get("repo_path", "."))
    except Exception as exc:
        logger.error("ARCHITECT agent failed: %s", exc)
        architecture = _fallback_architecture(all_files, entity_index, fingerprint, state.get("repo_path", "."))

    elapsed = time.monotonic() - t0
    n_components = len(architecture.get("components", []))
    logger.info(
        "ARCHITECT agent complete: %d components, %d data flows (%.1fs)",
        n_components,
        len(architecture.get("data_flows", [])),
        elapsed,
    )
    report_agent_progress("architect", "complete", f"{n_components} components identified")

    return {
        "architecture": architecture,
        "agent_results": [{
            "agent": "architect",
            "success": True,
            "elapsed": elapsed,
            "components": len(architecture.get("components", [])),
        }],
    }


def _parse_architecture_response(response: str, all_files: list, repo_path: str) -> dict:
    """Parse LLM JSON response into ArchitectureModel dict."""
    all_files_set = set(all_files)
    resolved_root = Path(repo_path).resolve()
    
    # Pre-build a lookup for short path -> normalized path
    short_to_abs = {}
    for f in all_files:
        p = Path(f)
        short_to_abs[f] = f
        short_to_abs[p.name] = f
        if len(p.parts) >= 2:
            short_to_abs["/".join(p.parts[-2:])] = f
        if len(p.parts) >= 3:
            short_to_abs["/".join(p.parts[-3:])] = f
        if len(p.parts) >= 4:
            short_to_abs["/".join(p.parts[-4:])] = f

    # Strip markdown code fences if present
    text = response.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove first and last fence lines
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in response
        import re
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                logger.warning("ARCHITECT: Could not parse JSON response")
                return _fallback_architecture(all_files, {}, {}, repo_path)
        else:
            logger.warning("ARCHITECT: No JSON found in response")
            return _fallback_architecture(all_files, {}, {}, repo_path)

    # Validate required keys
    arch = ArchitectureModel.from_dict(data)

    # Drop components with 0 files — these are abstract/conceptual, not code-based
    valid_components = []
    for comp in arch.components:
        files = comp.get("files", [])
        
        # Normalize files using short_to_abs map
        normalized_files = []
        for f in files:
            f_str = str(f)
            # 1. Try direct match
            if f_str in all_files_set:
                normalized_files.append(f_str)
                continue
            
            # 2. Try matching suffix (AI often gives relative paths from repo root)
            matched = False
            for real_path in all_files:
                if real_path.endswith(f_str.lstrip("./")):
                    normalized_files.append(real_path)
                    matched = True
                    break
            if matched:
                continue

            # 3. Try matching basename (last ditch effort)
            base = Path(f_str).name
            for real_path in all_files:
                if Path(real_path).name == base:
                    normalized_files.append(real_path)
                    matched = True
                    break
        
        # Ensure all paths in normalized_files are fully absolute from all_files_set
        # (This is already handled by the suffix/basename matching logic above,
        # but we'll ensure they are sorted and unique here)
        real_files = sorted(list(set(normalized_files)))
        if real_files:
            comp["files"] = real_files
            valid_components.append(comp)
        else:
            logger.warning(
                "ARCHITECT: Dropping component '%s' — 0 real source files",
                comp.get("name", "?"),
            )
    arch.components = valid_components

    if not arch.components:
        logger.warning("ARCHITECT: All components had 0 files, falling back to directory-based")
        return _fallback_architecture(all_files, {}, {})

    # Rebuild component_map from validated components (ALWAYS using repo-relative paths)
    arch.component_map = {}
    resolved_root = Path(repo_path).resolve()
    
    for comp in arch.components:
        normalized_comp_files = []
        for f in comp.get("files", []):
            rel_f = f
            try:
                rel_f = str(Path(f).resolve().relative_to(resolved_root))
            except ValueError:
                pass
            normalized_comp_files.append(rel_f)
            arch.component_map[rel_f] = comp["name"]
        comp["files"] = normalized_comp_files

    # Ensure component_map covers all files
    mapped_files = set(arch.component_map.keys())
    unmapped = [f for f in all_files if f not in mapped_files]
    if unmapped and arch.components:
        # Assign unmapped files to nearest component by directory
        for f in unmapped:
            best_comp = _find_best_component(f, arch.components)
            arch.component_map[f] = best_comp

    logger.info(
        "ARCHITECT: %d valid components, %d/%d files mapped",
        len(arch.components), len(arch.component_map), len(all_files),
    )

    return arch.to_dict()


def _find_best_component(file_path: str, components: list[dict]) -> str:
    """Find the best matching component for a file by directory overlap."""
    from pathlib import PurePosixPath

    file_dir = str(PurePosixPath(file_path).parent)
    best_name = components[0]["name"] if components else "Other"
    best_overlap = -1

    for comp in components:
        for comp_file in comp.get("files", []):
            comp_dir = str(PurePosixPath(comp_file).parent)
            # Count shared path components
            overlap = len(
                set(PurePosixPath(file_dir).parts)
                & set(PurePosixPath(comp_dir).parts)
            )
            if overlap > best_overlap:
                best_overlap = overlap
                best_name = comp["name"]

    return best_name


def _fallback_architecture(
    all_files: list,
    entity_index: dict,
    fingerprint: dict,
    repo_path: str,
) -> dict:
    """Generate a basic architecture from directory structure when LLM fails."""
    from pathlib import PurePosixPath

    # Group files by top-level directory
    dir_groups: dict[str, list[str]] = {}
    for f in all_files:
        parts = PurePosixPath(f).parts
        if len(parts) >= 2:
            group = parts[0] + "/" + parts[1] if parts[0] == "src" else parts[0]
        else:
            group = "root"
        dir_groups.setdefault(group, []).append(f)

    components = []
    component_map = {}
    for dir_name, files in sorted(dir_groups.items()):
        name = dir_name.replace("/", " - ").replace("_", " ").title()
        components.append({
            "name": name,
            "purpose": f"Files under {dir_name}/",
            "public_interfaces": [],
            "dependencies": [],
            "files": files,
        })
        for f in files:
            component_map[f] = name

    return ArchitectureModel(
        layers=[{"name": "Application", "purpose": "All code", "key_files": [], "key_entities": []}],
        components=components,
        data_flows=[],
        key_abstractions=[],
        diagram_spec={
            "overview": {
                "nodes": [{"id": c["name"].lower().replace(" ", "_"), "label": c["name"]} for c in components],
                "edges": [],
            }
        },
        component_map=component_map,
    ).to_dict()
