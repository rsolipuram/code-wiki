import json
import logging
import sys
import time
import os

sys.path.append(os.path.dirname(__file__))

from src.storage.repo_cache import clone
from src.recon import repo_recon
from src.parsers.extractor import extract_entities
from src.wiki.v2_pipeline import _build_entity_index, _build_call_graph, _build_reverse_call_graph
from src.wiki.interestingness import score_entities
from src.wiki.compressor import CodebaseCompressor
from src.wiki.agents.architect_agent import architect_node

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_test():
    repo_url = "https://github.com/openai/openai-cs-agents-demo"
    branch = "main"

    logger.info(f"Cloning {repo_url}...")
    local_path = clone(repo_url, branch=branch)
    repo_path = str(local_path)
    
    logger.info("Running recon...")
    fingerprint = repo_recon.run(repo_path)
    
    logger.info("Extracting entities...")
    entities = extract_entities(repo_path, build_output_dirs=fingerprint.build_output_dirs)
    
    logger.info("Building indexes...")
    entity_index, name_to_qname = _build_entity_index(entities, repo_path)
    call_graph = _build_call_graph(entities, name_to_qname)
    reverse_call_graph = _build_reverse_call_graph(call_graph)
    scored_entities = score_entities(entities)
    all_files = sorted({e.file_path for e in entities if e.entity_type != "module"})
    
    logger.info("Compressing codebase...")
    compressor = CodebaseCompressor()
    compressed = compressor.compress(repo_path, entities, fingerprint, scored_entities)
    
    compressed_dict = {
        "repo_summary": compressed.repo_summary,
        "file_summaries": {
            k: {
                "file_path": v.file_path, "language": v.language,
                "line_count": v.line_count, "summary": v.summary,
                "entity_count": v.entity_count, "key_entities": v.key_entities,
            }
            for k, v in compressed.file_summaries.items()
        },
        "directory_summaries": {
            k: {
                "dir_path": v.dir_path, "file_count": v.file_count,
                "summary": v.summary, "child_files": v.child_files,
                "key_entities": v.key_entities,
            }
            for k, v in compressed.directory_summaries.items()
        },
        "key_entities": compressed.key_entities,
        "call_graph_summary": compressed.call_graph_summary,
        "import_graph_summary": compressed.import_graph_summary,
        "compression_level": compressed.compression_level,
    }
    
    fp_dict = fingerprint.to_dict() if hasattr(fingerprint, "to_dict") else {}
    
    state = {
        "entities": entities,
        "entity_index": entity_index,
        "call_graph": call_graph,
        "reverse_call_graph": reverse_call_graph,
        "compressed": compressed_dict,
        "fingerprint": fp_dict,
        "dossier": {},
        "repo_path": repo_path,
        "repo_url": repo_url,
        "commit_hash": "test",
        "scored_entities": scored_entities,
        "all_files": all_files,
        "name_to_qname": name_to_qname,
        "architecture": {},
    }
    
    logger.info("Running Architect agent...")
    result = architect_node(state)
    
    print("\\n\\n" + "="*80)
    print("ARCHITECT RESULTS:")
    print("="*80)
    print(json.dumps(result["architecture"], indent=2))

if __name__ == "__main__":
    run_test()