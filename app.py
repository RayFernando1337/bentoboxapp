import os
import sys
import logging
import asyncio
import subprocess
import threading
import multiprocessing
import asyncio
from concurrent.futures import ProcessPoolExecutor
from datetime import timedelta

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

ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'wmv', 'mp3', 'wav'}

# Ensure static directory exists
os.makedirs('static', exist_ok=True)

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def timedelta_to_srt_time(td):
    """Convert a timedelta to SubRipTime object"""
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    milliseconds = td.microseconds // 1000
    return pysrt.SubRipTime(hours=hours, minutes=minutes, seconds=seconds, milliseconds=milliseconds)

def extract_audio(video_path, output_path, progress_callback=None):
    """Extract audio from video file using ffmpeg with stream copy"""
    try:
        logging.info(f"Extracting audio stream from {video_path}")
        
        # Get video duration for progress calculation
        duration_cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            video_path
        ]
        duration = float(subprocess.check_output(duration_cmd).decode().strip())
        
        # Setup FFmpeg command for fast audio extraction
        command = [
            'ffmpeg',
            '-i', video_path,
            '-vn',                # No video
            '-acodec', 'pcm_s16le', # Audio codec
            '-ar', '16000',        # Sample rate
            '-ac', '1',            # Mono
            '-f', 'wav',           # Format
            '-progress', 'pipe:1',  # Output progress to stdout
            '-y',                  # Overwrite
            output_path
        ]
        
        # Start FFmpeg process
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        # Monitor progress
        time_processed = 0
        while True:
            line = process.stdout.readline()
            if not line:
                break
                
            # Parse progress
            if line.startswith('out_time_ms='):
                time_processed = float(line.split('=')[1]) / 1000000  # Convert to seconds
                if progress_callback:
                    progress = (time_processed / duration) * 100
                    progress_callback({
                        'stage': 'extracting_audio',
                        'progress': min(progress, 100)
                    })
        
        # Check result
        process.wait()
        if process.returncode != 0:
            error = process.stderr.read()
            raise Exception(f"FFmpeg error: {error}")
            
        if not os.path.exists(output_path):
            raise Exception("Audio extraction failed: output file not created")
            
        logging.info("Audio extraction completed successfully")
        return True
        
    except Exception as e:
        logging.error(f"Error during audio extraction: {str(e)}")
        if os.path.exists(output_path):
            os.remove(output_path)
        raise

@app.route('/', methods=['GET'])
def index():
    return redirect(url_for('transcribe'))

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
def get_word_count(title):
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
            return jsonify({
                'error': 'Transcript not found',
                'status': 'error'
            }), 404

        logging.info(f"Found transcript: {transcript.title} with status {transcript.status}")
        
        # Estimate duration based on file size if processing
        estimated_duration = None
        if transcript.status == 'processing':
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
        
        # Return status along with word count and duration estimate
        return jsonify({
            'word_count': transcript.word_count,
            'status': transcript.status,
            'error': None if transcript.status != 'failed' else transcript.error_message or 'Transcription failed',
            'estimated_duration': estimated_duration
        })
    except Exception as e:
        error_msg = f"Error getting word count: {str(e)}"
        logging.error(error_msg)
        return jsonify({
            'word_count': 0,
            'status': 'error',
            'error': error_msg
        }), 500

@app.route('/preview_transcript/<title>')
def preview_transcript(title):
    try:
        transcript = Transcript.query.filter_by(title=title).first()
        if not transcript:
            return jsonify({'error': 'Transcript not found'}), 404

        # Format content with paragraphs
        formatted_content = '<p>' + '</p><p>'.join(transcript.content.split('\n\n')) + '</p>'
        return jsonify({'content': formatted_content})
    except Exception as e:
        logging.error(f"Error getting preview: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/rename_transcript', methods=['POST'])
def rename_transcript():
    try:
        data = request.get_json()
        old_title = data.get('old_title')
        new_title = data.get('new_title')
        
        if not old_title or not new_title:
            return jsonify({'error': 'Missing title'}), 400

        # Check if new title already exists
        if Transcript.query.filter_by(title=new_title).first():
            return jsonify({'error': 'Transcript with new title already exists'}), 400

        # Update database record
        transcript = Transcript.query.filter_by(title=old_title).first()
        if not transcript:
            return jsonify({'error': 'Original transcript not found'}), 404

        # Update database
        transcript.title = new_title
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        logging.error(f"Error renaming transcript: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed'}), 400

    filename = secure_filename(file.filename)
    title = os.path.splitext(filename)[0]
    
    # Check if transcript with this title already exists
    if Transcript.query.filter_by(title=title).first():
        return jsonify({'error': 'A transcript with this name already exists'}), 400

    # Create temporary directory for processing
    temp_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'temp')
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, filename)
    
    try:
        # Clean the title (remove extension and special characters)
        clean_title = ''.join(c for c in title if c.isalnum() or c in ' -_')
        
        # Create transcript record
        transcript = Transcript(
            title=clean_title,
            content='',  # Will be updated after processing
            word_count=0,  # Will be updated after processing
            status='processing',
            error_message=None,
            original_filename=filename
        )
        db.session.add(transcript)
        db.session.commit()
        logging.info(f"Created transcript record with title: {clean_title}")

        # Save uploaded file to temp directory
        file.save(temp_path)
        file_size = os.path.getsize(temp_path)
        logging.info(f"File saved temporarily: {temp_path} (size: {file_size/1024/1024:.2f} MB)")
        
        # Start transcription process
        def process_file():
            try:
                # Create new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                async def process_async():
                    async def update_progress(progress_data):
                        """Update transcript progress in database"""
                        transcript.status = f"processing_{progress_data['stage']}"
                        if 'progress' in progress_data:
                            transcript.progress = progress_data['progress']
                        if 'text' in progress_data:
                            transcript.content = progress_data['text']
                        db.session.commit()

                    try:
                        # For video files, extract audio first
                        if file.filename.lower().endswith(('.mp4', '.avi', '.mov', '.wmv')):
                            audio_path = os.path.join(temp_dir, f"{title}.wav")
                            logging.info(f"Extracting audio from video file to {audio_path}")
                            
                            # Extract audio with progress tracking
                            await extract_audio(temp_path, audio_path, update_progress)
                            input_path = audio_path
                        else:
                            input_path = temp_path

                        # Initialize transcription service
                        async with GroqTranscriptionService() as service:
                            # Transcribe the file
                            result = await service.transcribe_audio(input_path, update_progress)
                            
                            # Update transcript with results
                            transcript.content = result['text']
                            transcript.word_count = len(result['text'].split())
                            transcript.duration = result['duration']
                            transcript.segments = [{
                                'index': i,
                                'start': segment['start'],
                                'end': segment['end'],
                                'text': segment['text'].strip()
                            } for i, segment in enumerate(result['segments'], 1)]
                            transcript.status = 'completed'
                            db.session.commit()
                            logging.info(f"Transcription completed for {clean_title}")
                    except Exception as e:
                        logging.error(f"Error in async processing: {str(e)}")
                        transcript.status = 'failed'
                        transcript.error_message = str(e)
                        db.session.commit()
                        raise
                
                try:
                    # Run the async process
                    loop.run_until_complete(process_async())
                except Exception as e:
                    logging.error(f"Error in process_file: {str(e)}")
                    # Error is already handled in process_async
                finally:
                    try:
                        # Clean up the event loop
                        if not loop.is_closed():
                            loop.stop()
                            loop.close()
                    except Exception as e:
                        logging.error(f"Error closing event loop: {str(e)}")
                    
                    # Clean up temporary files
                    if os.path.exists(temp_path):
                        try:
                            os.remove(temp_path)
                        except Exception as e:
                            logging.error(f"Error removing temp file: {str(e)}")
            except Exception as e:
                logging.error(f"Error in process_file: {str(e)}")
                transcript.status = 'failed'
                transcript.error_message = str(e)
                db.session.commit()
        
        # Start processing in background
        threading.Thread(target=process_file).start()
        
        return jsonify({
            'message': 'File uploaded successfully',
            'title': clean_title
        })
        
    except Exception as e:
        logging.error(f"Error uploading file: {str(e)}")
        return jsonify({'error': str(e)}), 500

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
