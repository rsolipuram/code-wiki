import os
import sys
import json
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.models.repository import Repository
from src.models.wiki import Wiki, WikiPage, PageType
from src.models.events import UpdateEvent
from src.models.code_entity import CodeEntity

def review_home():
    db_url = os.getenv("DATABASE_URL", "postgresql://codewiki:codewiki@localhost:5434/codewiki")
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # Use the specific repo name or the latest one
    repo = session.query(Repository).filter_by(name='openai-cs-agents-demo').first()
    if not repo:
        repo = session.query(Repository).order_by(Repository.id.desc()).first()
        
    if not repo:
        print("No repositories found.")
        return

    w = session.query(Wiki).filter_by(repository_id=repo.id).first()
    if not w:
        print(f"No wiki found for repository {repo.name}.")
        return

    home_page = session.query(WikiPage).filter_by(wiki_id=w.id, page_type=PageType.home).first()
    if not home_page:
        print(f"No home page found for wiki {wiki.id}.")
        return

    print(f"--- HOME PAGE: {home_page.title} ---")
    print(json.dumps(home_page.content, indent=2))

if __name__ == "__main__":
    review_home()
