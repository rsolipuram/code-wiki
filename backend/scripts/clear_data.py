"""Script to clear all data from the Code Wiki application.
This includes:
1. PostgreSQL (Truncating all tables)
2. Neo4j (Deleting all nodes and relationships)
3. Qdrant (Deleting all collections)
4. Redis (Flushing all data)
5. Local Cache (Deleting cloned repositories)
"""

import os
import shutil
import sys
from pathlib import Path

# Add src to path so we can import models and config
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker
from neo4j import GraphDatabase
from qdrant_client import QdrantClient
import redis
from src.config import get_settings
from src.storage.vector_db import ensure_collections

def clear_postgres():
    print("Clearing PostgreSQL...")
    settings = get_settings()
    # Use environment variable if set, otherwise use settings
    db_url = os.getenv("DATABASE_URL", settings.database_url)
    engine = create_engine(db_url)
    metadata = MetaData()
    metadata.reflect(bind=engine)
    
    # We want to truncate all tables except alembic_version
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            for table in reversed(metadata.sorted_tables):
                if table.name != "alembic_version":
                    print(f"  Truncating table: {table.name}")
                    connection.execute(table.delete())
            transaction.commit()
            print("PostgreSQL cleared.")
        except Exception as e:
            transaction.rollback()
            print(f"Error clearing PostgreSQL: {e}")

def clear_neo4j():
    print("Clearing Neo4j...")
    settings = get_settings()
    try:
        driver = GraphDatabase.driver(
            settings.neo4j_uri, 
            auth=(settings.neo4j_user, settings.neo4j_password)
        )
        with driver.session() as session:
            result = session.run("MATCH (n) DETACH DELETE n")
            summary = result.consume()
            print(f"  Deleted Neo4j nodes. Counters: {summary.counters}")
        driver.close()
        print("Neo4j cleared.")
    except Exception as e:
        print(f"Error clearing Neo4j: {e}")

def clear_qdrant():
    print("Clearing Qdrant...")
    settings = get_settings()
    try:
        client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key or None)
        collections = client.get_collections().collections
        for collection in collections:
            print(f"  Deleting collection: {collection.name}")
            client.delete_collection(collection.name)
        print("Qdrant cleared.")
    except Exception as e:
        print(f"Error clearing Qdrant: {e}")

def clear_redis():
    print("Clearing Redis...")
    settings = get_settings()
    # Use environment variable if set, otherwise use settings
    redis_url = os.getenv("REDIS_URL", settings.redis_url)
    try:
        client = redis.from_url(redis_url)
        client.flushall()
        print("Redis cleared.")
    except Exception as e:
        print(f"Error clearing Redis: {e}")

def clear_local_cache():
    print("Clearing local cache...")
    settings = get_settings()
    cache_dir = Path(settings.repo_cache_dir)
    if cache_dir.exists():
        print(f"  Deleting contents of {cache_dir}")
        for item in cache_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        print("Local cache cleared.")
    else:
        print(f"  Cache directory {cache_dir} does not exist.")

if __name__ == "__main__":
    print("Starting data cleanup...")
    clear_postgres()
    clear_neo4j()
    clear_qdrant()
    clear_redis()
    clear_local_cache()
    print("Recreating empty Qdrant collections...")
    ensure_collections()
    print("Cleanup complete.")
