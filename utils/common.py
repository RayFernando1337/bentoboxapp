from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum

class TranscriptStatus(str, Enum):
    """Enum for transcript processing status"""
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CHUNKING = "processing_chunking"
    TRANSCRIBING = "processing_transcribing"
    EXTRACTING_AUDIO = "processing_extracting_audio"
    UPLOADING = "processing_uploading"

def api_response(success: bool, data: Optional[Dict[str, Any]] = None, error: Optional[str] = None) -> Dict[str, Any]:
    """Generate a standardized API response"""
    response = {
        "success": success,
        "timestamp": datetime.utcnow().isoformat()
    }
    if data is not None:
        response["data"] = data
    if error is not None:
        response["error"] = error
    return response

def timedelta_to_srt_time(td):
    """Convert timedelta to SRT format time string"""
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    milliseconds = int(td.microseconds / 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}" 