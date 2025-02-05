from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Transcript(db.Model):
    __table_args__ = (
        db.Index('idx_transcript_title', 'title'),  # Index for title lookups
        db.Index('idx_transcript_status', 'status'),  # Index for status filters
        db.Index('idx_transcript_created', 'created_at'),  # Index for sorting by date
    )
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    word_count = db.Column(db.Integer, nullable=False)
    duration = db.Column(db.Float)  # Duration in seconds
    original_filename = db.Column(db.String(255))  # Original filename for extension lookup
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    status = db.Column(db.String(50), default='processing')  # processing, completed, error
    error_message = db.Column(db.Text)
    segments = db.Column(db.JSON)  # Store time-aligned segments for SRT generation

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'word_count': self.word_count,
            'duration': self.duration,
            'content': self.content,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'status': self.status,
            'segments': self.segments
        }
