"""Cross-Link Resolver — V3 wiki pipeline post-processing step.

After all Deep Content Agents have written their sections, this module
resolves <cross-ref section="Section Title"> references to actual page slugs.

The slug map is stable before any agent runs (it comes from WikiNav),
so resolution is deterministic.
"""

import logging
from copy import deepcopy

logger = logging.getLogger(__name__)


def resolve_cross_refs(
    deep_sections: list[dict],
    wiki_nav_dict: dict,
) -> list[dict]:
    """Resolve all cross-ref segments in assembled sections.

    For each prose_segment of type "cross-ref":
      - Looks up section_title in the wiki_nav slug map
      - Fills in section_slug (leaves empty string if title not found)
      - Adds unresolved=True flag if slug not found

    Args:
        deep_sections: List of V3Section dicts (with prose_segments assembled).
        wiki_nav_dict: WikiNav.to_dict() — provides the slug map.

    Returns:
        Deep copy of deep_sections with cross-ref segments resolved.
    """
    # Build slug map: {title_lower: slug, title: slug}
    slug_map: dict[str, str] = {}
    for section in wiki_nav_dict.get("sections", []):
        title = section.get("title", "")
        slug = section.get("slug", "")
        if title and slug:
            slug_map[title] = slug
            slug_map[title.lower()] = slug

    resolved = []
    total_refs = 0
    resolved_count = 0

    for section in deep_sections:
        section = deepcopy(section)
        segments = section.get("prose_segments", [])

        for seg in segments:
            if seg.get("type") != "cross-ref":
                continue

            total_refs += 1
            section_title = seg.get("section_title", "")
            if not section_title:
                seg["section_slug"] = ""
                seg["unresolved"] = True
                continue

            slug = slug_map.get(section_title) or slug_map.get(section_title.lower())
            if slug:
                seg["section_slug"] = slug
                seg["unresolved"] = False
                resolved_count += 1
            else:
                # Try partial match
                partial = next(
                    (s for t, s in slug_map.items() if section_title.lower() in t),
                    None,
                )
                if partial:
                    seg["section_slug"] = partial
                    seg["unresolved"] = False
                    resolved_count += 1
                    logger.debug(
                        "Cross-ref partial match: %r → %s", section_title, partial
                    )
                else:
                    seg["section_slug"] = ""
                    seg["unresolved"] = True
                    logger.debug("Cross-ref unresolved: %r", section_title)

        resolved.append(section)

    logger.info(
        "Cross-link resolution: %d/%d refs resolved",
        resolved_count, total_refs,
    )
    return resolved
