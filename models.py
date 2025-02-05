from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.dialects.postgresql import JSONB

db = SQLAlchemy()

class Transcript(db.Model):
    """Model for storing transcription data"""
    __tablename__ = 'transcripts'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), unique=True, nullable=False)
    content = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(50), nullable=False)
    progress = db.Column(db.Float, default=0)
    error = db.Column(db.Text, nullable=True)
    word_count = db.Column(db.Integer, default=0)
    duration = db.Column(db.Float, default=0)
    language = db.Column(db.String(10), default='en')
    segments = db.Column(JSONB, default=list)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert transcript to dictionary"""
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'status': self.status,
            'progress': self.progress,
            'error': self.error,
            'word_count': self.word_count,
            'duration': self.duration,
            'language': self.language,
            'segments': self.segments or [],
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    @staticmethod
    def create(title: str, status: str) -> 'Transcript':
        """Create a new transcript"""
        transcript = Transcript(
            title=title,
            status=status,
            created_at=datetime.utcnow()
        )
        db.session.add(transcript)
        db.session.commit()
        return transcript

    def update_status(self, status: str, progress: float = None, error: str = None) -> None:
        """Update transcript status"""
        self.status = status
        if progress is not None:
            self.progress = progress
        if error is not None:
            self.error = error
        self.updated_at = datetime.utcnow()
        db.session.commit()

    def update_content(self, content: str, segments: List[Dict[str, Any]] = None) -> None:
        """Update transcript content"""
        self.content = content
        if segments is not None:
            self.segments = segments
        self.word_count = len(content.split()) if content else 0
        self.updated_at = datetime.utcnow()
        db.session.commit()
