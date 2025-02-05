from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.hybrid import hybrid_property

db = SQLAlchemy()

class Transcript(db.Model):
    """Model for storing transcription data"""
    __tablename__ = 'transcripts'

    # Primary fields
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), unique=True, nullable=False, index=True)
    content = db.Column(db.Text, nullable=True)
    
    # Status and progress
    status = db.Column(db.String(50), nullable=False, index=True)
    progress = db.Column(db.Float, default=0)
    error = db.Column(db.Text, nullable=True)
    
    # Metadata
    word_count = db.Column(db.Integer, default=0)
    duration = db.Column(db.Float, default=0)
    language = db.Column(db.String(10), default='en')
    segments = db.Column(JSONB, default=list)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @hybrid_property
    def is_processing(self) -> bool:
        """Check if transcript is currently processing"""
        return self.status.startswith('processing')

    @hybrid_property
    def is_completed(self) -> bool:
        """Check if transcript is completed"""
        return self.status == 'completed'

    @hybrid_property
    def is_failed(self) -> bool:
        """Check if transcript failed"""
        return self.status == 'failed'

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
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'is_processing': self.is_processing,
            'is_completed': self.is_completed,
            'is_failed': self.is_failed
        }

    @classmethod
    def create(cls, title: str, status: str = 'processing') -> 'Transcript':
        """Create a new transcript"""
        transcript = cls(
            title=title,
            status=status,
            created_at=datetime.utcnow()
        )
        db.session.add(transcript)
        db.session.commit()
        return transcript

    def update_status(self, status: str, progress: Optional[float] = None, error: Optional[str] = None) -> None:
        """Update transcript status and progress"""
        self.status = status
        if progress is not None:
            self.progress = min(100, max(0, progress))
        if error is not None:
            self.error = error
        self.updated_at = datetime.utcnow()
        db.session.commit()

    def update_content(self, content: str, segments: Optional[List[Dict[str, Any]]] = None) -> None:
        """Update transcript content and segments"""
        self.content = content
        if segments is not None:
            self.segments = segments
        self.word_count = len(content.split()) if content else 0
        self.updated_at = datetime.utcnow()
        db.session.commit()

    def delete(self) -> None:
        """Delete the transcript"""
        db.session.delete(self)
        db.session.commit()

    @classmethod
    def get_by_title(cls, title: str) -> Optional['Transcript']:
        """Get transcript by title"""
        return cls.query.filter(cls.title.ilike(title)).first()

    @classmethod
    def get_recent(cls, limit: int = 10) -> List['Transcript']:
        """Get recent transcripts"""
        return cls.query.order_by(cls.created_at.desc()).limit(limit).all()

    def __repr__(self) -> str:
        return f'<Transcript {self.title}>'
