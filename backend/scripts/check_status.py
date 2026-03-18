import os
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.models.repository import Repository
from src.models.wiki import Wiki
from src.models.events import UpdateEvent
from src.models.code_entity import CodeEntity

from src.models.wiki import WikiPage

def check_status():
    db_url = os.getenv("DATABASE_URL", "postgresql://codewiki:codewiki@localhost:5434/codewiki")
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    repo = session.query(Repository).order_by(Repository.id.desc()).first()
    if not repo:
        print("No repositories found.")
        return

    print(f"Repository: {repo.name} (ID: {repo.id})")
    print(f"Status: {repo.status}")
    print(f"Progress: {repo.progress}")
    
    wiki = session.query(Wiki).filter_by(repository_id=repo.id).first()
    if wiki:
        pages_count = session.query(WikiPage).filter_by(wiki_id=wiki.id).count()
        print(f"Wiki ID: {wiki.id}, Pages generated: {pages_count}")
        if pages_count > 0:
            latest_page = session.query(WikiPage).filter_by(wiki_id=wiki.id).order_by(WikiPage.updated_at.desc()).first()
            print(f"Latest page: {latest_page.title} (Updated at: {latest_page.updated_at})")

if __name__ == "__main__":
    check_status()
