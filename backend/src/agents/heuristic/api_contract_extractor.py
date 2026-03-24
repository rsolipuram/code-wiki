"""APIContractExtractor — detects OpenAPI/Swagger, GraphQL, gRPC schemas (zero LLM)."""

import logging
import re
from pathlib import Path

from src.dossier.manager import DossierManager
from src.dossier.schema import AgentResponse

logger = logging.getLogger(__name__)

AGENT_NAME = "api_contract_extractor"
TAGS = ["api-contracts", "integration"]


def run(repo_path: str, dossier_manager: DossierManager) -> None:
    root = Path(repo_path)
    contracts: dict[str, list[str]] = {}

    # OpenAPI/Swagger
    openapi_files: list[str] = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in {".yaml", ".yml", ".json"}:
            try:
                content = p.read_text(errors="replace")[:500]
                if "openapi" in content or "swagger" in content:
                    openapi_files.append(str(p.relative_to(root)))
            except OSError:
                pass
    if openapi_files:
        contracts["openapi"] = openapi_files

    # GraphQL
    gql_files = [str(p.relative_to(root)) for p in root.rglob("*.graphql")] + \
                [str(p.relative_to(root)) for p in root.rglob("*.gql")]
    if gql_files:
        contracts["graphql"] = gql_files

    # gRPC / Protobuf
    proto_files = [str(p.relative_to(root)) for p in root.rglob("*.proto")]
    if proto_files:
        contracts["grpc"] = proto_files

    dossier_manager.write_response(AgentResponse(
        agent_name=AGENT_NAME,
        tags=TAGS,
        confidence=1.0,
        output={"openapi": contracts.get("openapi", []), "graphql": contracts.get("graphql", []), "grpc": contracts.get("grpc", [])},
        output_type="APIContracts",
    ))
    dossier_manager.mark_agent_complete(AGENT_NAME)
    logger.info("APIContractExtractor: found %s contract types", list(contracts.keys()))
