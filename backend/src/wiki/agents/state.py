"""WikiState TypedDict for LangGraph + ArchitectureModel.

Replaces hand-rolled WikiBlackboard with LangGraph's native state management.
All agents read from and write to this state as it flows through the graph.
"""

from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict

from operator import add


@dataclass
class ArchitectureModel:
    """ARCHITECT agent's output — shared understanding of the codebase.

    Stored as dict in WikiState['architecture'] for LangGraph serialization.
    """
    layers: list[dict] = field(default_factory=list)
    # [{name, purpose, key_files, key_entities}]

    components: list[dict] = field(default_factory=list)
    # [{name, purpose, public_interfaces, dependencies, files}]

    data_flows: list[dict] = field(default_factory=list)
    # [{source, destination, description}]

    key_abstractions: list[str] = field(default_factory=list)

    diagram_spec: dict = field(default_factory=dict)
    # {overview: {nodes, edges}, per_component: [...]}

    component_map: dict = field(default_factory=dict)
    # {file_path → component_name}

    def to_dict(self) -> dict:
        return {
            "layers": self.layers,
            "components": self.components,
            "data_flows": self.data_flows,
            "key_abstractions": self.key_abstractions,
            "diagram_spec": self.diagram_spec,
            "component_map": self.component_map,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ArchitectureModel":
        if not data:
            return cls()
        return cls(
            layers=data.get("layers", []),
            components=data.get("components", []),
            data_flows=data.get("data_flows", []),
            key_abstractions=data.get("key_abstractions", []),
            diagram_spec=data.get("diagram_spec", {}),
            component_map=data.get("component_map", {}),
        )


class WikiState(TypedDict, total=False):
    """LangGraph state flowing through the agent graph.

    Immutable inputs are set once at graph entry.
    Progressive outputs are updated by each agent node.
    """
    # ── Immutable inputs (set once at graph entry) ──
    entities: list                # ParsedEntity objects
    entity_index: dict            # qname → {file_path, line_start, name, entity_type, signature}
    call_graph: dict              # caller → [callees]
    reverse_call_graph: dict
    import_graph: dict            # importer_rel_path → [imported_rel_paths]
    compressed: dict              # CompressedCodebase as dict
    fingerprint: dict             # RepoFingerprint as dict
    dossier: dict                 # Dossier findings
    repo_path: str
    repo_url: str
    commit_hash: str
    scored_entities: list
    all_files: list
    name_to_qname: dict

    # ── Derived inputs (set before agent pipeline) ──
    domain_entities: dict         # DomainEntitySummary: {agents, tools, guardrails, all_names}

    # ── Progressive agent outputs ──
    architecture: dict            # ArchitectureModel (set by ARCHITECT)
    plan: dict                    # WikiPlan as dict (set by PLANNER)
    system_narrative: str         # (set by WRITER)
    narrated_sections: dict       # {section_id: NarratedSection-dict} (set by WRITER)
    annotated_sections: dict      # {section_id: prose_with_markers} (set by ANNOTATOR)
    section_diagrams: dict        # {section_id: [diagrams]} (set by DIAGRAMMER)
    section_tables: dict          # {section_id: [tables]} (set by TABULATOR)
    overview_diagram: dict        # (set by DIAGRAMMER)
    # enriched_sections contains segments of type: 'text', 'source_link', 'code_block', 'section_link', 'heading', 'diagram', 'table'
    enriched_sections: Annotated[list, add]  # (appended by ASSEMBLER)
    agent_results: Annotated[list, add]      # AgentResult telemetry
