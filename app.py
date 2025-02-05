import os
import sys
import logging
import asyncio
import subprocess
import threading
import multiprocessing
import asyncio
from concurrent.futures import ProcessPoolExecutor
from datetime import timedelta, datetime
from enum import Enum
from typing import Optional, Dict, Any
import shutil

import pysrt
from dotenv import load_dotenv
from groq_transcription import GroqTranscriptionService

# Load environment variables first
load_dotenv()

# Configure logging once
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Flask imports
from flask import (
    Flask,
    request,
    render_template,
    jsonify,
    send_file,
    abort,
    redirect,
    url_for
)
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
from models import db, Transcript

# Constants
class TranscriptStatus(str, Enum):
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

app = Flask(__name__, static_url_path='/static', static_folder='static')

# Basic Flask configuration
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = None  # No file size limit
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'dev')

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'temp'), exist_ok=True)

# PostgreSQL configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://neondb_owner:npg_UI7tCka4SNlb@ep-damp-meadow-a832pv09-pooler.eastus2.azure.neon.tech/neondb?sslmode=require')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 5,
    'max_overflow': 2,
    'pool_timeout': 30,
    'pool_recycle': 1800,
}

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(RequestEntityTooLarge)
def too_large_error(error):
    return jsonify({'error': 'File too large'}), 413

# Initialize SQLAlchemy
db.init_app(app)

# Create tables
with app.app_context():
    db.create_all()

# Allowed file extensions
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'wmv', 'mp3', 'wav', 'm4a', 'aac', 'flac'}
MAX_FILE_AGE = timedelta(hours=24)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def cleanup_old_files():
    """Clean up files older than MAX_FILE_AGE"""
    temp_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'temp')
    current_time = datetime.now().timestamp()
    
    try:
        for filename in os.listdir(temp_dir):
            filepath = os.path.join(temp_dir, filename)
            if os.path.isfile(filepath):
                file_age = current_time - os.path.getctime(filepath)
                if file_age > MAX_FILE_AGE.total_seconds():
                    try:
                        os.remove(filepath)
                        logging.info(f"Cleaned up old file: {filepath}")
                    except Exception as e:
                        logging.error(f"Error removing old file {filepath}: {str(e)}")
    except Exception as e:
        logging.error(f"Error during cleanup: {str(e)}")

def cleanup_files(*files):
    """Clean up temporary files"""
    for file in files:
        if file and os.path.exists(file):
            try:
                os.remove(file)
                logging.info(f"Cleaned up file: {file}")
            except Exception as e:
                logging.error(f"Error cleaning up file {file}: {str(e)}")

async def extract_audio(video_path, audio_path, progress_callback=None):
    """Extract audio from video file using ffmpeg"""
    try:
        # Check if input file exists
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        # Check available disk space
        free_space = os.statvfs(os.path.dirname(audio_path)).f_frsize * os.statvfs(os.path.dirname(audio_path)).f_bavail
        video_size = os.path.getsize(video_path)
        if free_space < video_size * 2:  # Ensure we have at least 2x the video size available
            raise OSError("Insufficient disk space for audio extraction")

        if progress_callback:
            await progress_callback({
                'stage': TranscriptStatus.EXTRACTING_AUDIO,
                'progress': 10,
                'text': 'Extracting audio from video...'
            })

        # Use ffmpeg to extract audio with optimal settings for transcription
        cmd = [
            'ffmpeg', '-i', video_path,
            '-vn',  # Disable video
            '-acodec', 'pcm_s16le',  # Use WAV format
            '-ar', '16000',  # 16kHz sample rate
            '-ac', '1',  # Mono audio
            '-y',  # Overwrite output file
            audio_path
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise Exception(f"FFmpeg error: {stderr.decode()}")

        if progress_callback:
            await progress_callback({
                'stage': TranscriptStatus.EXTRACTING_AUDIO,
                'progress': 20,
                'text': 'Audio extraction complete'
            })

        return audio_path

    except Exception as e:
        logging.error(f"Error extracting audio: {str(e)}")
        raise

@app.route('/', methods=['GET'])
def index():
    cleanup_old_files()  # Clean up old files on index page load
    transcripts = []
    try:
        for filename in os.listdir(os.path.join(app.config['UPLOAD_FOLDER'], 'temp')):
            if filename.endswith('.json'):
                transcripts.append({
                    'title': filename[:-5],  # Remove .json extension
                    'date': datetime.fromtimestamp(
                        os.path.getmtime(os.path.join(app.config['UPLOAD_FOLDER'], 'temp', filename))
                    ).strftime('%Y-%m-%d %H:%M:%S')
                })
        transcripts.sort(key=lambda x: x['date'], reverse=True)
    except Exception as e:
        logging.error(f"Error loading transcripts: {str(e)}")
        return api_response(False, error="Error loading transcripts")
    
    return render_template('index.html', transcripts=transcripts)

@app.route('/transcribe', methods=['GET'])
def transcribe():
    transcripts = Transcript.query.order_by(Transcript.created_at.desc()).all()
    return render_template('transcribe.html', transcripts=transcripts, active_page='transcribe')

@app.route('/create', methods=['GET'])
def create():
    return render_template('create.html', active_page='create')

@app.route('/schedule', methods=['GET'])
def schedule():
    return render_template('schedule.html', active_page='schedule')

@app.route('/word_count/<title>')
async def get_word_count(title):
    try:
        # Use case-insensitive comparison for title
        transcript = Transcript.query.filter(
            Transcript.title.ilike(title)
        ).first()
        
        if not transcript:
            logging.error(f"Transcript not found with title: {title}")
            # List all transcript titles for debugging
            all_titles = [t.title for t in Transcript.query.all()]
            logging.info(f"Available transcripts: {all_titles}")
            return api_response(False, error='Transcript not found', status=404)

        logging.info(f"Found transcript: {transcript.title} with status {transcript.status}")
        
        # Estimate duration based on file size if processing
        estimated_duration = None
        if transcript.status.startswith(TranscriptStatus.PROCESSING):
            # Try to find the file using original extension first
            original_ext = os.path.splitext(transcript.original_filename)[1] if transcript.original_filename else '.wav'
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'temp', secure_filename(title + original_ext))
            
            # If not found, try common extensions
            if not os.path.exists(file_path):
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'temp', secure_filename(title + '.wav'))
            if not os.path.exists(file_path):
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'temp', secure_filename(title + '.mp4'))
            
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                # Rough estimate: 1MB ≈ 1 minute of audio/video
                estimated_duration = (file_size / (1024 * 1024)) * 60  # seconds
            else:
                estimated_duration = 7200  # 2 hours default
        
        return api_response(True, data={
            'word_count': transcript.word_count,
            'status': transcript.status,
            'error': None if not transcript.status == TranscriptStatus.FAILED else transcript.error_message,
            'estimated_duration': estimated_duration
        })
    except Exception as e:
        error_msg = f"Error getting word count: {str(e)}"
        logging.error(error_msg)
        return api_response(False, error=error_msg, status=500)

@app.route('/preview_transcript/<title>')
def preview_transcript(title):
    try:
        transcript = Transcript.query.filter_by(title=title).first()
        if not transcript:
            return jsonify(api_response(False, error='Transcript not found')), 404

        # Format content with paragraphs
        formatted_content = '<p>' + '</p><p>'.join(transcript.content.split('\n\n')) + '</p>'
        return jsonify(api_response(True, {
            'content': formatted_content,
            'title': title
        }))
    except Exception as e:
        logging.error(f"Error getting preview: {str(e)}")
        return jsonify(api_response(False, error=str(e))), 500

@app.route('/rename_transcript', methods=['POST'])
def rename_transcript():
    try:
        data = request.get_json()
        old_title = data.get('old_title')
        new_title = data.get('new_title')
        
        if not old_title or not new_title:
            return jsonify(api_response(False, error='Missing title')), 400

        # Check if new title already exists
        if Transcript.query.filter_by(title=new_title).first():
            return jsonify(api_response(False, error='Transcript with new title already exists')), 400

        # Update database record
        transcript = Transcript.query.filter_by(title=old_title).first()
        if not transcript:
            return jsonify(api_response(False, error='Original transcript not found')), 404

        # Update database
        transcript.title = new_title
        db.session.commit()
        
        return jsonify(api_response(True))
    except Exception as e:
        logging.error(f"Error renaming transcript: {str(e)}")
        return jsonify(api_response(False, error=str(e))), 500

async def process_file(file_path: str, title: str) -> None:
    """Process an uploaded file for transcription"""
    audio_path = None
    temp_chunks_dir = None
    
    try:
        # Initialize progress
        transcript = Transcript(
            title=title,
            status=TranscriptStatus.PROCESSING,
            created_at=datetime.utcnow()
        )
        db.session.add(transcript)
        db.session.commit()
        
        # Create temporary directory for audio processing
        temp_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        
        # Extract audio if needed
        file_ext = os.path.splitext(file_path)[1].lower()
        if file_ext not in ['.mp3', '.wav', '.m4a', '.aac', '.flac']:
            audio_path = os.path.join(temp_dir, f"{title}_audio.wav")
            success = await extract_audio(
                file_path, 
                audio_path,
                lambda status, progress, error=None: update_transcript_status(title, status, progress, error)
            )
            if not success:
                raise RuntimeError("Failed to extract audio from file")
        else:
            audio_path = file_path
            
        # Initialize transcription service
        transcription_service = GroqTranscriptionService(
            api_key=os.getenv('GROQ_API_KEY'),
            openai_api_key=os.getenv('OPENAI_API_KEY')
        )
        
        # Update status to transcribing
        transcript.status = TranscriptStatus.TRANSCRIBING
        db.session.commit()
        
        # Transcribe audio
        result = await transcription_service.transcribe_audio(
            audio_path,
            lambda status, progress: update_transcript_status(title, status, progress)
        )
        
        # Save transcription result
        transcript.content = result['text']
        transcript.segments = result.get('segments', [])
        transcript.language = result.get('language', 'en')
        transcript.duration = result.get('duration', 0)
        transcript.word_count = len(result['text'].split())
        transcript.status = TranscriptStatus.COMPLETED
        db.session.commit()
        
    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        try:
            transcript = Transcript.query.filter_by(title=title).first()
            if transcript:
                transcript.status = TranscriptStatus.FAILED
                transcript.error = str(e)
                db.session.commit()
        except Exception as db_error:
            logger.error(f"Error updating transcript status: {str(db_error)}")
    
    finally:
        # Cleanup temporary files
        cleanup_files(file_path)
        if audio_path and audio_path != file_path:
            cleanup_files(audio_path)
        if temp_chunks_dir:
            shutil.rmtree(temp_chunks_dir, ignore_errors=True)

def update_transcript_status(title: str, status: TranscriptStatus, progress: float = 0, error: Optional[str] = None) -> None:
    """Update the status and progress of a transcript"""
    try:
        transcript = Transcript.query.filter_by(title=title).first()
        if transcript:
            transcript.status = status
            transcript.progress = progress
            if error:
                transcript.error = error
            db.session.commit()
    except Exception as e:
        logger.error(f"Error updating transcript status: {str(e)}")

@app.route('/upload', methods=['POST'])
async def upload_file():
    if 'file' not in request.files:
        return jsonify(api_response(False, error="No file provided"))
    
    file = request.files['file']
    if file.filename == '':
        return jsonify(api_response(False, error="No file selected"))
    
    if not allowed_file(file.filename):
        return jsonify(api_response(False, error="File type not allowed"))
    
    try:
        # Save uploaded file
        filename = secure_filename(file.filename)
        title = os.path.splitext(filename)[0]
        
        # Check if transcript exists
        if Transcript.query.filter_by(title=title).first():
            return jsonify(api_response(False, error="A transcript with this name already exists"))
        
        # Save file
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # Start processing in background
        asyncio.create_task(process_file(file_path, title))
        
        # Return success response
        return jsonify(api_response(True, {
            "title": title,
            "size": os.path.getsize(file_path),
            "type": file.content_type
        }))
        
    except Exception as e:
        logger.error(f"Error handling upload: {str(e)}")
        return jsonify(api_response(False, error=str(e)))

@app.route('/transcript/<int:transcript_id>', methods=['GET'])
def get_transcript(transcript_id):
    try:
        transcript = Transcript.query.get_or_404(transcript_id)
        return jsonify(transcript.to_dict())
    except Exception as e:
        logging.error(f"Error getting transcript: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/transcript/<int:transcript_id>/srt', methods=['GET'])
def get_transcript_srt(transcript_id):
    try:
        transcript = Transcript.query.get_or_404(transcript_id)
        
        if transcript.status != 'completed':
            return jsonify({'error': 'Transcript not ready'}), 400
        
        if not transcript.segments:
            return jsonify({'error': 'No segments available'}), 400
        
        # Generate SRT content from segments
        srt_content = ''
        for segment in transcript.segments:
            # Convert start and end times to timedelta
            start_time = timedelta(seconds=segment['start'])
            end_time = timedelta(seconds=segment['end'])
            
            # Convert to SRT format
            start_time_str = str(timedelta_to_srt_time(start_time))
            end_time_str = str(timedelta_to_srt_time(end_time))
            
            # Build the subtitle entry
            srt_content += f"{segment['index']}\n"
            srt_content += f"{start_time_str} --> {end_time_str}\n"
            srt_content += f"{segment['text']}\n\n"
        
        return jsonify({
            'title': transcript.title,
            'srt_content': srt_content
        })

    except Exception as e:
        logging.error(f"Error generating SRT: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/transcript/<int:transcript_id>', methods=['DELETE'])
def delete_transcript(transcript_id):
    try:
        transcript = Transcript.query.get_or_404(transcript_id)
        title = transcript.title

        # Clean up any in-progress files
        if transcript.status == 'processing':
            # Find and remove temp files
            temp_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'temp')
            for ext in ['.wav', '.mp4', '.avi', '.mov', '.wmv', '.mp3']:
                temp_path = os.path.join(temp_dir, secure_filename(title + ext))
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    logging.info(f"Removed temp file: {temp_path}")

        # Delete database record
        db.session.delete(transcript)
        db.session.commit()
        logging.info(f"Transcript {title} deleted successfully")

        return jsonify({
            'success': True,
            'message': f'Transcript {title} deleted successfully'
        })

    except Exception as e:
        logging.error(f"Error deleting transcript: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Create database tables
    with app.app_context():
        db.create_all()
    
    # Start server
    app.run(host='0.0.0.0', debug=True, port=5001)
