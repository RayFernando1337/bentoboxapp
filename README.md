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

1. **Environment Setup**:

   ```bash
   # Create and activate virtual environment
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install Dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

3. **Environment Variables**:
   Create a `.env` file with the following:

   ```
   GROQ_API_KEY=your_groq_api_key
   OPENAI_API_KEY=your_openai_api_key
   FLASK_SECRET_KEY=your_secret_key
   DATABASE_URL=your_database_url
   ```

4. **Database Setup**:

   ```bash
   # The application will automatically create tables on first run
   python app.py
   ```

5. **Run the Application**:
   ```bash
   python app.py
   ```
   The application will be available at http://localhost:5001

## System Requirements

- Python 3.8 or higher
- FFmpeg (for audio extraction)
- PostgreSQL database
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
