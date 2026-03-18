"""ANNOTATOR agent — inserts entity and section markers into prose.

Takes WRITER's clean prose and inserts [[entity:QualifiedName]] and
[[section:slug]] markers at semantically correct positions.

Replaces: overloaded narrator prompt, _inject_missing_entity_markers(),
and auto_detect_entity_references() brute-force regex.
"""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.llm.client import chat
from src.wiki.agents.graph import report_agent_progress
from src.wiki.agents.state import WikiState

logger = logging.getLogger(__name__)

ANNOTATOR_SYSTEM_PROMPT = """You are a precision annotation agent for technical documentation.

Your task is to insert entity reference markers into existing prose WITHOUT changing the content.
You receive prose text and a list of code entities. Insert [[entity:QualifiedName]] markers
wrapping mentions of those entities in the prose.

RULES:
1. Insert [[entity:QualifiedName]] wrapping entity name mentions
   - Example: "The server class" → "The [[entity:server.AirlineServer]] class"
   - Example: "handles routing" → "handles routing via [[entity:api.router.setup_routes]]"
2. Insert [[section:slug]] for cross-section references
   - Example: "See the agent section" → "See [[section:agent-orchestration]]"
3. Reference at LEAST 85% of the provided entities — be thorough
4. Do NOT modify the prose content, headings, or code markers
5. Do NOT add new text or paragraphs — only insert markers
6. Each entity should be referenced 1-5 times based on importance
7. Place markers where they read naturally in the sentence
8. Return the COMPLETE annotated prose
9. For important entities (classes, key functions), add multiple references throughout"""


def annotator_node(state: WikiState) -> dict:
    """ANNOTATOR node — add entity markers to all sections in parallel."""
    t0 = time.monotonic()
    logger.info("ANNOTATOR agent starting")
    report_agent_progress("annotator", "running", "Adding entity references")

    narrated_sections = state.get("narrated_sections", {})
    plan = state.get("plan", {})
    entity_index = state.get("entity_index", {})

    # Build section slug → title map for cross-referencing
    section_map = {
        s.get("id", ""): s.get("title", "")
        for s in plan.get("sections", [])
    }

    annotated_sections = {}

    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {}
        for section_id, narrated in narrated_sections.items():
            section_plan = next(
                (s for s in plan.get("sections", []) if s.get("id") == section_id),
                {},
            )
            future = pool.submit(
                _annotate_section,
                narrated, section_plan, entity_index, section_map,
            )
            futures[future] = section_id

        for future in as_completed(futures):
            section_id = futures[future]
            try:
                result = future.result(timeout=120)
                annotated_sections[section_id] = result
            except Exception as exc:
                logger.error("ANNOTATOR: section '%s' failed: %s", section_id, exc)
                # Fall back to unannotated prose
                annotated_sections[section_id] = narrated_sections[section_id].get("prose", "")

    elapsed = time.monotonic() - t0
    n_sections = len(annotated_sections)
    logger.info("ANNOTATOR agent complete: %d sections (%.1fs)", n_sections, elapsed)
    report_agent_progress("annotator", "complete", f"{n_sections} sections annotated")

    return {
        "annotated_sections": annotated_sections,
        "agent_results": [{
            "agent": "annotator",
            "success": True,
            "elapsed": elapsed,
            "sections": len(annotated_sections),
        }],
    }


def _annotate_section(
    narrated: dict,
    section_plan: dict,
    entity_index: dict,
    section_map: dict[str, str],
) -> str:
    """Annotate a single section's prose with entity markers."""
    prose = narrated.get("prose", "")
    section_id = narrated.get("section_id", "")
    section_title = narrated.get("title", "")

    if not prose or prose.startswith("Documentation for"):
        return prose

    # Collect entities for this section
    section_files = set()
    for sub in section_plan.get("subsections", []):
        section_files.update(sub.get("relevant_files", []))
    for f in section_plan.get("_all_files", []):
        section_files.add(f)

    # Filter entities to those in this section's files
    section_entities: list[dict] = []
    for qname, info in entity_index.items():
        if info.get("file_path") in section_files:
            name = info.get("name", qname.rsplit(".", 1)[-1])
            if name.startswith("_"):
                continue
            section_entities.append({
                "qname": qname,
                "name": name,
                "entity_type": info.get("entity_type", ""),
            })

    if not section_entities:
        return prose

    # Limit to top entities to keep prompt manageable
    entity_list = section_entities[:400]
    entity_text = "\n".join(
        f"  - [[entity:{e['qname']}]] ({e['entity_type']}: {e['name']})"
        for e in entity_list
    )

    # Cross-section references
    other_sections = "\n".join(
        f"  - [[section:{slug}]] ({title})"
        for slug, title in section_map.items()
        if slug != section_id
    )

    prompt = f"""Annotate this prose by inserting entity markers and cross-section links.

PROSE TO ANNOTATE:
{prose}

AVAILABLE ENTITIES (insert [[entity:QualifiedName]] wrapping mentions):
{entity_text}

OTHER SECTIONS (insert [[section:slug]] for cross-references):
{other_sections}

RULES:
- Reference at least 85% of the available entities — be thorough
- Do NOT change the prose content — only ADD markers
- Place markers where they read naturally
- Important entities (classes, key functions): 2-5 references; minor entities: 1-2 references
- Preserve all existing [[heading:...]] and [[code:...]] markers exactly

Return the COMPLETE annotated prose."""

    try:
        result = chat(
            [
                {"role": "system", "content": ANNOTATOR_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=8192,
            temperature=0.1,
            cache_ttl=3600,
        ).strip()

        # Validate that markers are well-formed
        result = _fix_malformed_markers(result)

        # Check entity coverage
        referenced = set(re.findall(r"\[\[entity:([^\]]+)\]\]", result))
        entity_qnames = {e["qname"] for e in entity_list}
        coverage = len(referenced & entity_qnames) / max(len(entity_qnames), 1)
        logger.debug(
            "ANNOTATOR: section '%s' entity coverage: %.0f%% (%d/%d)",
            section_title, coverage * 100, len(referenced & entity_qnames), len(entity_qnames),
        )

        return result

    except Exception as exc:
        logger.error("ANNOTATOR: LLM call failed for '%s': %s", section_title, exc)
        return prose


def _fix_malformed_markers(text: str) -> str:
    """Fix common LLM marker errors."""
    # Fix unclosed markers
    text = re.sub(r"\[\[entity:([^\]]*?)(?=\[\[|$)", r"[[entity:\1]]", text)
    # Fix double-closed markers
    text = text.replace("]]]]", "]]")
    # Fix markers with extra spaces
    text = re.sub(r"\[\[\s*entity\s*:\s*", "[[entity:", text)
    text = re.sub(r"\[\[\s*section\s*:\s*", "[[section:", text)
    return text
