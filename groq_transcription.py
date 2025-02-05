import os
import json
import logging
import aiohttp
import aiofiles
from typing import Dict, Any, Optional

class GroqTranscriptionService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('GROQ_API_KEY')
        if not self.api_key:
            raise ValueError("Groq API key not found")
        
        self.base_url = "https://api.groq.com/openai/v1"
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def transcribe_audio(self, audio_file_path: str, progress_callback=None) -> Dict[Any, Any]:
        """
        Transcribe audio using Groq's Whisper API.
        
        Args:
            audio_file_path: Path to the audio file
            progress_callback: Optional callback for progress updates
            
        Returns:
            Dict containing transcription results
        """
        if not self.session:
            self.session = aiohttp.ClientSession()

        try:
            if progress_callback:
                await progress_callback({
                    'stage': 'preparing',
                    'progress': 0,
                    'text': 'Preparing audio for transcription...'
                })

            # Prepare the multipart form data
            data = aiohttp.FormData()
            data.add_field('model', 'whisper-1')
            data.add_field('response_format', 'verbose_json')
            data.add_field('language', 'en')

            # Add the audio file
            async with aiofiles.open(audio_file_path, 'rb') as f:
                file_data = await f.read()
                data.add_field('file', file_data, filename='audio.wav', content_type='audio/wav')

            if progress_callback:
                await progress_callback({
                    'stage': 'uploading',
                    'progress': 30,
                    'text': 'Uploading audio to Groq...'
                })

            # Make the API request
            async with self.session.post(
                f"{self.base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                data=data
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Groq API error: {error_text}")

                if progress_callback:
                    await progress_callback({
                        'stage': 'processing',
                        'progress': 60,
                        'text': 'Processing transcription...'
                    })

                result = await response.json()

            # Extract segments if available
            segments = []
            if 'segments' in result:
                segments = [{
                    'start': segment['start'],
                    'end': segment['end'],
                    'text': segment['text']
                } for segment in result['segments']]

            # Update progress to complete
            if progress_callback:
                await progress_callback({
                    'stage': 'completed',
                    'progress': 100,
                    'text': result['text']
                })

            return {
                'text': result['text'],
                'segments': segments,
                'language': result.get('language', 'en'),
                'duration': result.get('duration', 0)
            }

        except Exception as e:
            logging.error(f"Transcription error: {str(e)}")
            if progress_callback:
                await progress_callback({
                    'stage': 'error',
                    'progress': 0,
                    'text': str(e)
                })
            raise
