"""Reset Neo4j database for testing - removes all nodes and relationships."""
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "codewiki"))
with driver.session(database="neo4j") as session:
    result = session.run("MATCH (n) DETACH DELETE n")
    summary = result.consume()
    print(f"Deleted nodes. Counters: {summary.counters}")
driver.close()
