# BentoBox Transcription Service

A modern web application for transcribing audio and video files using Groq's Whisper model with OpenAI fallback.

## Features

- **Multiple Format Support**: Handles various audio and video formats:

  - Video: MP4, AVI, MOV, WMV
  - Audio: MP3, WAV, M4A, AAC, FLAC

- **Advanced Transcription**:

  - Uses Groq's latest Whisper-large-v3 model
  - Automatic fallback to OpenAI's Whisper model
  - Handles large files through intelligent chunking
  - Supports multiple languages

- **Progress Tracking**:

  - Real-time progress updates
  - Detailed status reporting for each stage
  - Estimated time remaining
  - Browser notifications on completion

- **File Management**:

  - Automatic audio extraction from video files
  - Intelligent file cleanup
  - Support for file renaming
  - SRT subtitle generation

- **User Interface**:
  - Modern, responsive design
  - Drag-and-drop file upload
  - Progress visualization
  - Transcript preview and editing
  - Content creation tools

## Setup

1. **Clone and Navigate**:

   ```bash
   git clone <repository-url>
   cd bentoboxapp
   ```

2. **Environment Setup**:

   ```bash
   # Create and activate conda environment
   conda create -n bentoboxapp python=3.12
   conda activate bentoboxapp
   ```

3. **Install Dependencies**:

   ```bash
   # Install FFmpeg first
   conda install -c conda-forge ffmpeg

   # Install Python packages
   pip install -r requirements.txt
   ```

4. **Environment Configuration**:
   Create a `.env` file in the project root:

   ```env
   GROQ_API_KEY=your_groq_api_key
   OPENAI_API_KEY=your_openai_api_key
   FLASK_SECRET_KEY=dev-secret-key
   SQLALCHEMY_DATABASE_URI=sqlite:///bentobox.db
   FLASK_APP=app.py
   ```

   Replace `your_groq_api_key` and `your_openai_api_key` with your actual API keys.

5. **Database Setup**:

   ```bash
   # Make sure you're in the project directory and your environment is activated
   cd /path/to/bentoboxapp
   conda activate bentoboxapp

   # Install dependencies (if not already done)
   pip install -r requirements.txt

   # Set the Flask application
   export FLASK_APP=app.py

   # Initialize the database
   flask db init
   flask db migrate -m "initial migration"
   flask db upgrade
   ```

   If you see "No such command 'db'", make sure you've installed all requirements and activated your environment.

6. **Run the Application**:
   ```bash
   # Development server
   flask run --port 5001
   ```
   The application will be available at http://localhost:5001

## Troubleshooting

- **Database Issues**:

  - Ensure the `.env` file exists and contains `SQLALCHEMY_DATABASE_URI`
  - Check that `FLASK_APP` is set correctly: `export FLASK_APP=app.py`
  - Verify the database directory is writable

- **FFmpeg Issues**:

  - Confirm FFmpeg installation: `ffmpeg -version`
  - If missing, reinstall: `conda install -c conda-forge ffmpeg`

- **API Keys**:
  - Verify both Groq and OpenAI API keys are set in `.env`
  - Test API keys validity before running the application

## System Requirements

- Python 3.12
- Conda package manager
- FFmpeg (installed via conda-forge)
- SQLite (for local development) or PostgreSQL (for production)
- Sufficient disk space for temporary file processing

## API Endpoints

- `POST /upload`: Upload audio/video file for transcription
- `GET /word_count/<title>`: Get transcription progress and word count
- `GET /preview_transcript/<title>`: Preview transcript content
- `GET /transcript/<id>`: Get full transcript details
- `GET /transcript/<id>/srt`: Download SRT subtitle file
- `DELETE /transcript/<id>`: Delete transcript
- `POST /rename_transcript`: Rename existing transcript

## Architecture

- **Frontend**: HTML, JavaScript with modern async/await patterns
- **Backend**: Flask with async support
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Processing**:
  - FFmpeg for audio extraction
  - Groq API for primary transcription
  - OpenAI API for fallback transcription
  - Chunked processing for large files

## Error Handling

- Comprehensive error handling throughout the application
- Automatic cleanup of failed transcriptions
- Graceful fallback to OpenAI when Groq fails
- Detailed error logging and reporting

## Security

- Secure file handling
- Input validation
- Safe filename handling
- Database connection pooling
- Environment variable protection

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

MIT License - See LICENSE file for details
