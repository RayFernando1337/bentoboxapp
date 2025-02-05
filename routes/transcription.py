import os
from pathlib import Path
import logging
import asyncio
import shutil
from datetime import timedelta
from flask import Blueprint, request, jsonify, current_app
from werkzeug.exceptions import BadRequest, NotFound
from werkzeug.utils import secure_filename
from models import Transcript, db
from services.file_handler import FileHandler
from services.audio_processor import extract_audio, AudioProcessingError
from groq_transcription import GroqTranscriptionService, TranscriptionError
from utils.common import TranscriptStatus, api_response, timedelta_to_srt_time

logger = logging.getLogger(__name__)

transcription_bp = Blueprint('transcription', __name__)

# Constants
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'wmv', 'mp3', 'wav', 'm4a', 'aac', 'flac'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

async def process_file(file_path: Path, title: str) -> None:
    """Process uploaded file for transcription"""
    audio_path = None
    temp_chunks_dir = None
    
    try:
        # Initialize transcript
        transcript = Transcript.create(
            title=title,
            status=TranscriptStatus.PROCESSING
        )
        
        # Create temp directory
        temp_dir = Path(current_app.config['UPLOAD_FOLDER']) / 'temp'
        temp_dir.mkdir(exist_ok=True)
        
        # Extract audio if needed
        file_ext = file_path.suffix.lower()
        if file_ext not in ['.mp3', '.wav', '.m4a', '.aac', '.flac']:
            audio_path = temp_dir / f"{title}_audio.wav"
            await extract_audio(
                str(file_path), 
                str(audio_path),
                lambda status: transcript.update_status(status['stage'], status['progress'])
            )
        else:
            audio_path = file_path
        
        # Initialize transcription service
        async with GroqTranscriptionService(
            api_key=os.getenv('GROQ_API_KEY'),
            openai_api_key=os.getenv('OPENAI_API_KEY')
        ) as service:
            # Update status
            transcript.update_status(TranscriptStatus.TRANSCRIBING)
            
            # Transcribe audio
            result = await service.transcribe_audio(
                str(audio_path),
                lambda status, progress: transcript.update_status(status, progress)
            )
            
            # Save results
            transcript.update_content(
                content=result['text'],
                segments=result.get('segments', [])
            )
            transcript.language = result.get('language', 'en')
            transcript.duration = result.get('duration', 0)
            transcript.status = TranscriptStatus.COMPLETED
            db.session.commit()
        
    except Exception as e:
        logger.error(f"Processing error: {str(e)}")
        try:
            if transcript:
                transcript.update_status(
                    TranscriptStatus.FAILED,
                    error=str(e)
                )
        except Exception as db_error:
            logger.error(f"Database error: {str(db_error)}")
    
    finally:
        # Cleanup
        file_handler = FileHandler(current_app)
        file_handler.cleanup_files(file_path)
        if audio_path and audio_path != file_path:
            file_handler.cleanup_files(audio_path)
        if temp_chunks_dir:
            shutil.rmtree(temp_chunks_dir, ignore_errors=True)

@transcription_bp.route('/upload', methods=['POST'])
async def upload_file():
    """Handle file upload and start transcription"""
    if 'file' not in request.files:
        raise BadRequest('No file provided')
    
    file = request.files['file']
    if not file or not file.filename:
        raise BadRequest('No file selected')
    
    if not allowed_file(file.filename):
        raise BadRequest('File type not allowed')
    
    try:
        # Save file and create transcript
        filename = secure_filename(file.filename)
        title = Path(filename).stem
        
        if Transcript.get_by_title(title):
            raise BadRequest('A transcript with this name already exists')
        
        file_handler = FileHandler(current_app)
        file_path = file_handler.save_upload(file, filename)
        
        # Start processing in background
        asyncio.create_task(process_file(file_path, title))
        
        return jsonify(api_response(True, {
            'title': title,
            'size': file_path.stat().st_size,
            'type': file.content_type
        })), 200
        
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        if file_path:
            file_handler.cleanup_files(file_path)
        raise

@transcription_bp.route('/word_count/<title>')
async def get_word_count(title):
    """Get word count and status for a transcript"""
    try:
        transcript = Transcript.query.filter(
            Transcript.title.ilike(title)
        ).first()
        
        if not transcript:
            raise NotFound('Transcript not found')
        
        # Estimate duration based on file size if processing
        estimated_duration = None
        if transcript.status.startswith('processing'):
            file_path = None
            original_ext = os.path.splitext(transcript.original_filename)[1] if transcript.original_filename else '.wav'
            
            # Try different possible file paths
            for ext in [original_ext, '.wav', '.mp4']:
                temp_path = Path(current_app.config['UPLOAD_FOLDER']) / 'temp' / secure_filename(title + ext)
                if temp_path.exists():
                    file_path = temp_path
                    break
            
            if file_path:
                file_size = file_path.stat().st_size
                # Rough estimate: 1MB ≈ 1 minute of audio/video
                estimated_duration = (file_size / (1024 * 1024)) * 60  # seconds
            else:
                estimated_duration = 7200  # 2 hours default
        
        return jsonify(api_response(True, {
            'word_count': transcript.word_count,
            'status': transcript.status,
            'error': transcript.error_message if transcript.status == 'failed' else None,
            'estimated_duration': estimated_duration
        }))
    except Exception as e:
        logger.error(f"Error getting word count: {str(e)}")
        raise

@transcription_bp.route('/preview/<title>')
def preview_transcript(title):
    """Get preview of transcript content"""
    try:
        transcript = Transcript.query.filter_by(title=title).first()
        if not transcript:
            raise NotFound('Transcript not found')

        # Format content with paragraphs
        formatted_content = '<p>' + '</p><p>'.join(transcript.content.split('\n\n')) + '</p>'
        return jsonify(api_response(True, {
            'content': formatted_content,
            'title': title
        }))
    except Exception as e:
        logger.error(f"Error getting preview: {str(e)}")
        raise

@transcription_bp.route('/rename', methods=['POST'])
def rename_transcript():
    """Rename an existing transcript"""
    try:
        data = request.get_json()
        old_title = data.get('old_title')
        new_title = data.get('new_title')
        
        if not old_title or not new_title:
            raise BadRequest('Missing title')

        # Check if new title already exists
        if Transcript.query.filter_by(title=new_title).first():
            raise BadRequest('Transcript with new title already exists')

        # Update database record
        transcript = Transcript.query.filter_by(title=old_title).first()
        if not transcript:
            raise NotFound('Original transcript not found')

        transcript.title = new_title
        db.session.commit()
        
        return jsonify(api_response(True))
    except Exception as e:
        logger.error(f"Error renaming transcript: {str(e)}")
        raise

@transcription_bp.route('/<int:transcript_id>', methods=['GET'])
def get_transcript(transcript_id):
    """Get transcript by ID"""
    try:
        transcript = Transcript.query.get_or_404(transcript_id)
        return jsonify(transcript.to_dict())
    except Exception as e:
        logger.error(f"Error getting transcript: {str(e)}")
        raise

@transcription_bp.route('/<int:transcript_id>/srt', methods=['GET'])
def get_transcript_srt(transcript_id):
    """Get transcript in SRT format"""
    try:
        transcript = Transcript.query.get_or_404(transcript_id)
        
        if transcript.status != TranscriptStatus.COMPLETED:
            raise BadRequest('Transcript not ready')
        
        if not transcript.segments:
            raise BadRequest('No segments available')
        
        # Generate SRT content from segments
        srt_content = ''
        for segment in transcript.segments:
            # Convert start and end times to timedelta
            start_time = timedelta(seconds=segment['start'])
            end_time = timedelta(seconds=segment['end'])
            
            # Convert to SRT format
            start_time_str = timedelta_to_srt_time(start_time)
            end_time_str = timedelta_to_srt_time(end_time)
            
            # Build the subtitle entry
            srt_content += f"{segment['index']}\n"
            srt_content += f"{start_time_str} --> {end_time_str}\n"
            srt_content += f"{segment['text']}\n\n"
        
        return jsonify(api_response(True, {
            'title': transcript.title,
            'srt_content': srt_content
        }))
    except Exception as e:
        logger.error(f"Error generating SRT: {str(e)}")
        raise

@transcription_bp.route('/<int:transcript_id>', methods=['DELETE'])
def delete_transcript(transcript_id):
    """Delete transcript and associated files"""
    try:
        transcript = Transcript.query.get_or_404(transcript_id)
        title = transcript.title

        # Clean up any in-progress files
        if transcript.status == TranscriptStatus.PROCESSING:
            temp_dir = Path(current_app.config['UPLOAD_FOLDER']) / 'temp'
            for ext in ['.wav', '.mp4', '.avi', '.mov', '.wmv', '.mp3']:
                temp_path = temp_dir / secure_filename(title + ext)
                if temp_path.exists():
                    temp_path.unlink()
                    logger.info(f"Removed temp file: {temp_path}")

        # Delete database record
        db.session.delete(transcript)
        db.session.commit()
        logger.info(f"Transcript {title} deleted successfully")

        return jsonify(api_response(True, {
            'message': f'Transcript {title} deleted successfully'
        }))
    except Exception as e:
        logger.error(f"Error deleting transcript: {str(e)}")
        raise 