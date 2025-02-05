from app import app, db
from models import Transcript

def add_original_filename_column():
    with app.app_context():
        # Add column if it doesn't exist
        from sqlalchemy import text
        db.session.execute(text('ALTER TABLE transcript ADD COLUMN IF NOT EXISTS original_filename VARCHAR(255)'))
        db.session.commit()

if __name__ == '__main__':
    add_original_filename_column()
