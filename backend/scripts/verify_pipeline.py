
import os
import sys
import json
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))

from src.wiki.agents.state import ArchitectureModel, WikiState
from src.wiki.agents.planner_agent import planner_node
from src.wiki.agents.writer_agent import writer_node
from src.wiki.agents.assembler_agent import assembler_node

def verify():
    print("🚀 Starting Independent Pipeline Verification...")
    
    # Mock Initial State
    state: WikiState = {
        "repo_path": ".",
        "repo_url": "https://github.com/test/test",
        "commit_hash": "test-hash",
        "entities": [],
        "entity_index": {"test.func": {"name": "test_func", "file_path": "test.py", "entity_type": "function"}},
        "call_graph": {},
        "reverse_call_graph": {},
        "compressed": {"repo_summary": "Test project for verification.", "file_summaries": {}},
        "fingerprint": {"system_type": "web-app", "primary_language": "Python"},
        "dossier": {},
        "scored_entities": {},
        "all_files": ["test.py"],
        "name_to_qname": {"test_func": "test.func"},
        "architecture": {
            "components": [
                {"name": "API", "purpose": "Entry point", "dependencies": ["Core"]},
                {"name": "Core", "purpose": "Logic", "dependencies": []}
            ]
        },
        "plan": {},
        "system_narrative": "",
        "narrated_sections": {},
        "annotated_sections": {},
        "section_diagrams": {"api": [{"mermaid_source": "graph TD\nA-->B", "caption": "Test Diagram"}]},
        "section_tables": {},
        "overview_diagram": {},
        "enriched_sections": [],
        "agent_results": [],
    }

    # 1. Test Planner (Logical Sequencing)
    print("\n[1/3] Testing Planner (Sequencing)...")
    plan_output = planner_node(state)
    sections = plan_output["plan"]["sections"]
    print(f"✅ Generated {len(sections)} sections.")
    for i, s in enumerate(sections):
        print(f"   {i+1}. {s['title']} ({s['id']})")

    # 2. Test Writer (Headings & Prose)
    print("\n[2/3] Testing Writer (Heading Conversion)...")
    state.update(plan_output)
    writer_output = writer_node(state)
    narrative = writer_output["system_narrative"]
    if "[[heading:" in narrative:
        print("✅ Success: System narrative contains converted [[heading:]] markers.")
    else:
        print("❌ Error: System narrative missing heading markers.")
    
    # 3. Test Assembler (Interleaving)
    print("\n[3/3] Testing Assembler (Interleaving)...")
    state.update(writer_output)
    section_id = sections[0]["id"]
    # Ensure diagram exists for this section ID
    state["section_diagrams"] = {section_id: [{"mermaid_source": "graph TD\nA-->B", "caption": "Test Diagram"}]}
    
    state["annotated_sections"] = {section_id: "[[heading:2:Sub-Section]]\nSome prose here."}

    assembler_output = assembler_node(state)
    enriched = assembler_output["enriched_sections"][0]

    # Debug: Print segment types
    seg_types = [seg.get("type") if isinstance(seg, dict) else getattr(seg, "type", "?") for seg in enriched["prose_segments"]]
    print(f"   Segment types: {seg_types}")

    has_interleaved = any(seg.get("type") == "diagram" for seg in enriched["prose_segments"])
    if has_interleaved:
        print("✅ Success: Diagram is interleaved within prose segments.")
    else:
        print("❌ Error: Diagram was not interleaved.")


    print("\n✨ Verification Complete.")

if __name__ == "__main__":
    verify()
