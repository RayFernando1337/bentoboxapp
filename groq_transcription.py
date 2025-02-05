import os
import json
import logging
import aiohttp
import aiofiles
from typing import Dict, Any, Optional
from openai import AsyncOpenAI
from pydub import AudioSegment
import tempfile

class GroqTranscriptionService:
    def __init__(self, api_key: Optional[str] = None, openai_api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('GROQ_API_KEY')
        self.openai_api_key = openai_api_key or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("Groq API key not found")
        if not self.openai_api_key:
            raise ValueError("OpenAI API key not found")
        
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

    async def transcribe_audio(self, audio_file_path: str, progress_callback=None) -> Dict[Any, Any]:
        """
        Transcribe audio using Groq's Whisper API with fallback to OpenAI.
        Handles large files by splitting them into chunks.
        
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

            # Load audio file
            audio = AudioSegment.from_file(audio_file_path)
            total_duration = len(audio)

            # If file is small enough, transcribe directly
            if total_duration <= self.chunk_duration:
                return await self._transcribe_single_file(audio_file_path, progress_callback)

            # For large files, split into chunks and transcribe each
            chunks = []
            full_transcript = {'text': '', 'segments': []}
            start_time = 0
            chunk_count = (total_duration + self.chunk_duration - 1) // self.chunk_duration

            for i, chunk_start in enumerate(range(0, total_duration, self.chunk_duration)):
                if progress_callback:
                    await progress_callback({
                        'stage': 'chunking',
                        'progress': (i / chunk_count) * 20,  # Use first 20% for chunking
                        'text': f'Processing chunk {i+1} of {chunk_count}...'
                    })

                # Extract chunk
                chunk_end = min(chunk_start + self.chunk_duration, total_duration)
                audio_chunk = audio[chunk_start:chunk_end]

                # Save chunk to temporary file
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                    audio_chunk.export(temp_file.name, format='wav')
                    chunks.append(temp_file.name)

                try:
                    # Transcribe chunk
                    chunk_transcript = await self._transcribe_single_file(
                        temp_file.name,
                        lambda p: self._adjust_progress(p, i, chunk_count, progress_callback)
                    )

                    # Adjust timestamps and combine results
                    chunk_transcript['text'] = chunk_transcript['text'].strip() + ' '
                    for segment in chunk_transcript['segments']:
                        segment['start'] += start_time
                        segment['end'] += start_time
                    
                    full_transcript['text'] += chunk_transcript['text']
                    full_transcript['segments'].extend(chunk_transcript['segments'])

                finally:
                    # Clean up temporary file
                    try:
                        os.unlink(temp_file.name)
                    except Exception as e:
                        logging.warning(f"Failed to delete temporary file {temp_file.name}: {e}")

                start_time += (chunk_end - chunk_start) / 1000  # Convert to seconds

            if progress_callback:
                await progress_callback({
                    'stage': 'completed',
                    'progress': 100,
                    'text': full_transcript['text']
                })

            return full_transcript

        except Exception as e:
            logging.error(f"Transcription error: {str(e)}")
            if progress_callback:
                await progress_callback({
                    'stage': 'error',
                    'progress': 0,
                    'text': str(e)
                })
            raise

    def _adjust_progress(self, chunk_progress, chunk_index, total_chunks, progress_callback):
        """Adjust chunk progress to overall progress"""
        if not progress_callback or not chunk_progress:
            return
        
        # Chunking takes 20%, transcription takes 80%
        # Within transcription, divide 80% by number of chunks
        chunk_base = 20 + (chunk_index * 80 / total_chunks)
        chunk_portion = 80 / total_chunks
        adjusted_progress = chunk_base + (chunk_progress['progress'] * chunk_portion / 100)

        return progress_callback({
            'stage': chunk_progress['stage'],
            'progress': min(adjusted_progress, 100),
            'text': chunk_progress['text']
        })

    async def _transcribe_single_file(self, audio_file_path: str, progress_callback=None) -> Dict[Any, Any]:
        """Transcribe a single audio file using Groq with OpenAI fallback"""
        try:
            result = await self._transcribe_with_groq(audio_file_path, progress_callback)
            return result
        except Exception as groq_error:
            logging.warning(f"Groq transcription failed: {str(groq_error)}. Falling back to OpenAI.")
            if progress_callback:
                await progress_callback({
                    'stage': 'fallback',
                    'progress': 30,
                    'text': 'Groq transcription failed, trying OpenAI...'
                })
            return await self._transcribe_with_openai(audio_file_path, progress_callback)

    async def _transcribe_with_groq(self, audio_file_path: str, progress_callback=None) -> Dict[Any, Any]:
        """Internal method to transcribe using Groq"""
        # Prepare the multipart form data
        data = aiohttp.FormData()
        data.add_field('model', 'whisper-large-v3')  # Use latest model
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

    async def _transcribe_with_openai(self, audio_file_path: str, progress_callback=None) -> Dict[Any, Any]:
        """Internal method to transcribe using OpenAI as fallback"""
        try:
            if progress_callback:
                await progress_callback({
                    'stage': 'uploading',
                    'progress': 40,
                    'text': 'Uploading audio to OpenAI...'
                })

            # Open and transcribe the file
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

            # Convert OpenAI response format to match Groq format
            result = {
                'text': transcript.text,
                'segments': [{
                    'start': segment.start,
                    'end': segment.end,
                    'text': segment.text
                } for segment in transcript.segments],
                'language': transcript.language,
                'duration': sum(segment.end - segment.start for segment in transcript.segments)
            }

            if progress_callback:
                await progress_callback({
                    'stage': 'completed',
                    'progress': 100,
                    'text': result['text']
                })

            return result

        except Exception as e:
            logging.error(f"OpenAI transcription error: {str(e)}")
            raise
