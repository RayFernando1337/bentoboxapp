# BentoBox Flask Version

This is the Flask version of the BentoBox Transcription application. It provides a web interface for transcribing audio and video files using OpenAI's Whisper model.

## Setup

1. Create a virtual environment (optional but recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python app.py
```

The application will be available at http://localhost:5000

## Features

- Upload audio/video files for transcription
- Automatic transcription using Whisper
- Download transcripts in various formats
- Preview transcripts in the browser
- Rename files
- Delete transcripts
