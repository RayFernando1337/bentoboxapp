import os
import json
import logging
import aiohttp
import aiofiles
import asyncio
from typing import Dict, Any, Optional, Callable
from openai import AsyncOpenAI
from pydub import AudioSegment
import tempfile

# Custom exceptions for better error handling
class TranscriptionError(Exception):
    """Base exception for transcription errors"""
    pass

class APIError(TranscriptionError):
    """Raised when API calls fail"""
    pass

class AudioProcessingError(TranscriptionError):
    """Raised when audio processing fails"""
    pass

class GroqTranscriptionService:
    """Service for transcribing audio using Groq API with OpenAI fallback"""
    
    def __init__(self, api_key: Optional[str] = None, openai_api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('GROQ_API_KEY')
        self.openai_api_key = openai_api_key or os.getenv('OPENAI_API_KEY')
        
        if not self.api_key:
            raise ValueError("Groq API key not found. Set GROQ_API_KEY environment variable.")
        if not self.openai_api_key:
            raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY environment variable.")
        
        self.base_url = "https://api.groq.com/openai/v1"
        self.session = None
        self.openai_client = AsyncOpenAI(api_key=self.openai_api_key)
        self.chunk_duration = 10 * 60 * 1000  # 10 minutes in milliseconds

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def transcribe_audio(
        self, 
        audio_file_path: str, 
        progress_callback: Optional[Callable] = None,
        timeout: int = 3600
    ) -> Dict[Any, Any]:
        """
        Transcribe audio with automatic chunking and fallback to OpenAI.
        
        Args:
            audio_file_path: Path to audio file
            progress_callback: Optional function for progress updates
            timeout: Maximum time in seconds for transcription
        
        Returns:
            Dictionary containing transcription results
        """
        if not self.session:
            self.session = aiohttp.ClientSession()

        try:
            # Replace incorrect timeout syntax with proper wait_for implementation
            async def transcription_task():
                if progress_callback:
                    await progress_callback({
                        'stage': 'preparing',
                        'progress': 0,
                        'text': 'Preparing audio...'
                    })

                # Load and validate audio file
                try:
                    audio = AudioSegment.from_file(audio_file_path)
                except Exception as e:
                    raise AudioProcessingError(f"Failed to load audio file: {str(e)}")

                total_duration = len(audio)

                # Process small files directly
                if total_duration <= self.chunk_duration:
                    return await self._transcribe_single_file(audio_file_path, progress_callback)

                # Process large files in chunks
                return await self._process_large_file(audio, audio_file_path, progress_callback)

            try:
                return await asyncio.wait_for(transcription_task(), timeout=timeout)
            except asyncio.TimeoutError:
                raise TranscriptionError(f"Transcription timed out after {timeout} seconds")
            except Exception as e:
                raise TranscriptionError(f"Transcription failed: {str(e)}")

        except Exception as e:
            raise TranscriptionError(f"Transcription failed: {str(e)}")

    async def _process_large_file(
        self, 
        audio: AudioSegment,
        original_path: str,
        progress_callback: Optional[Callable]
    ) -> Dict[Any, Any]:
        """Process large audio files by chunking"""
        chunks = []
        full_transcript = {'text': '', 'segments': []}
        total_duration = len(audio)
        chunk_count = (total_duration + self.chunk_duration - 1) // self.chunk_duration
        start_time = 0

        for i, chunk_start in enumerate(range(0, total_duration, self.chunk_duration)):
            if progress_callback:
                await progress_callback({
                    'stage': 'chunking',
                    'progress': (i / chunk_count) * 20,
                    'text': f'Processing chunk {i+1} of {chunk_count}...'
                })

            # Extract and process chunk
            chunk_end = min(chunk_start + self.chunk_duration, total_duration)
            audio_chunk = audio[chunk_start:chunk_end]

            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                try:
                    audio_chunk.export(temp_file.name, format='wav')
                    chunks.append(temp_file.name)

                    # Transcribe chunk
                    chunk_result = await self._transcribe_single_file(
                        temp_file.name,
                        lambda p: self._adjust_progress(p, i, chunk_count, progress_callback)
                    )

                    # Combine results
                    chunk_result['text'] = chunk_result['text'].strip() + ' '
                    for segment in chunk_result['segments']:
                        segment['start'] += start_time
                        segment['end'] += start_time
                    
                    full_transcript['text'] += chunk_result['text']
                    full_transcript['segments'].extend(chunk_result['segments'])

                finally:
                    try:
                        os.unlink(temp_file.name)
                    except Exception as e:
                        logging.warning(f"Failed to delete temp file {temp_file.name}: {e}")

            start_time += (chunk_end - chunk_start) / 1000

        if progress_callback:
            await progress_callback({
                'stage': 'completed',
                'progress': 100,
                'text': full_transcript['text']
            })

        return full_transcript

    async def _transcribe_single_file(
        self, 
        audio_file_path: str, 
        progress_callback: Optional[Callable] = None
    ) -> Dict[Any, Any]:
        """Transcribe a single audio file with fallback"""
        try:
            return await self._transcribe_with_groq(audio_file_path, progress_callback)
        except Exception as groq_error:
            logging.warning(f"Groq transcription failed: {str(groq_error)}. Falling back to OpenAI.")
            if progress_callback:
                await progress_callback({
                    'stage': 'fallback',
                    'progress': 30,
                    'text': 'Groq transcription failed, trying OpenAI...'
                })
            return await self._transcribe_with_openai(audio_file_path, progress_callback)

    async def _transcribe_with_groq(
        self, 
        audio_file_path: str, 
        progress_callback: Optional[Callable] = None
    ) -> Dict[Any, Any]:
        """Internal method to transcribe using Groq"""
        data = aiohttp.FormData()
        data.add_field('model', 'whisper-large-v3')
        data.add_field('response_format', 'verbose_json')
        data.add_field('language', 'en')

        async with aiofiles.open(audio_file_path, 'rb') as f:
            file_data = await f.read()
            data.add_field('file', file_data, filename='audio.wav', content_type='audio/wav')

        if progress_callback:
            await progress_callback({
                'stage': 'uploading',
                'progress': 30,
                'text': 'Uploading to Groq...'
            })

        async with self.session.post(
            f"{self.base_url}/audio/transcriptions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            data=data
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                raise APIError(f"Groq API error: {error_text}")

            if progress_callback:
                await progress_callback({
                    'stage': 'processing',
                    'progress': 60,
                    'text': 'Processing transcription...'
                })

            result = await response.json()
            return self._format_transcription_result(result)

    async def _transcribe_with_openai(
        self, 
        audio_file_path: str, 
        progress_callback: Optional[Callable] = None
    ) -> Dict[Any, Any]:
        """Internal method to transcribe using OpenAI as fallback"""
        try:
            if progress_callback:
                await progress_callback({
                    'stage': 'uploading',
                    'progress': 40,
                    'text': 'Uploading to OpenAI...'
                })

            with open(audio_file_path, 'rb') as audio_file:
                transcript = await self.openai_client.audio.transcriptions.create(
                    file=audio_file,
                    model="whisper-1",
                    response_format="verbose_json",
                    timestamp_granularities=["segment"]
                )

            if progress_callback:
                await progress_callback({
                    'stage': 'processing',
                    'progress': 80,
                    'text': 'Processing OpenAI transcription...'
                })

            return self._format_transcription_result(transcript)

        except Exception as e:
            raise APIError(f"OpenAI transcription error: {str(e)}")

    def _format_transcription_result(self, result: Dict[Any, Any]) -> Dict[Any, Any]:
        """Format API response into standard structure"""
        return {
            'text': result['text'],
            'segments': [{
                'start': segment['start'],
                'end': segment['end'],
                'text': segment['text'].strip()
            } for segment in result['segments']],
            'language': result.get('language', 'en'),
            'duration': result.get('duration', 0)
        }

    def _adjust_progress(
        self, 
        chunk_progress: Dict[str, Any],
        chunk_index: int,
        total_chunks: int,
        progress_callback: Optional[Callable]
    ) -> None:
        """Adjust chunk progress to overall progress"""
        if not progress_callback or not chunk_progress:
            return

        chunk_base = 20 + (chunk_index * 80 / total_chunks)
        chunk_portion = 80 / total_chunks
        adjusted_progress = chunk_base + (chunk_progress['progress'] * chunk_portion / 100)

        return progress_callback({
            'stage': chunk_progress['stage'],
            'progress': min(adjusted_progress, 100),
            'text': chunk_progress.get('text', '')
        })
