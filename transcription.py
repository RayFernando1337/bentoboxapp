import os
import json
import logging
import asyncio
from deepgram import Deepgram

class TranscriptionService:
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv('DEEPGRAM_API_KEY')
        if not self.api_key:
            raise ValueError("Deepgram API key not found")
        self.dg_client = Deepgram(self.api_key)

    async def transcribe_chunk(self, file_path, start_byte, end_byte):
        """Transcribe a chunk of an audio file using Deepgram."""
        try:
            with open(file_path, 'rb') as audio:
                # Seek to chunk position
                audio.seek(start_byte)
                chunk_data = audio.read(end_byte - start_byte)
                
                # Configure Deepgram for optimal speed
                options = {
                    'smart_format': True,
                    'model': 'nova-2',     # Fastest model
                    'tier': 'enhanced',    # Better accuracy
                    'punctuate': True,
                    'language': 'en',      # Specify language for better performance
                    'encoding': 'linear16', # WAV format
                    'sample_rate': 16000,   # 16kHz
                    'channels': 1,          # Mono
                    'detect_language': False, # Speed up by skipping language detection
                    'profanity_filter': False, # Speed up by skipping filters
                    'numerals': False,     # Speed up by skipping number conversion
                }

                # Process chunk
                response = await self.dg_client.transcription.prerecorded(
                    {'buffer': chunk_data, 'mimetype': 'audio/wav'},
                    options
                )
                
                # Extract results
                transcript = response['results']['channels'][0]['alternatives'][0]
                return {
                    'text': transcript['transcript'],
                    'segments': transcript['words'],
                    'duration': response['metadata']['duration']
                }
        except Exception as e:
            logging.error(f"Error transcribing chunk: {str(e)}")
            return {'text': '', 'segments': [], 'duration': 0}

    async def transcribe_file(self, file_path):
        """Legacy method for full file transcription."""
        try:
            return await self.transcribe_chunk(file_path, 0, os.path.getsize(file_path))
        except Exception as e:
            raise Exception(f"Transcription failed: {str(e)}")

    async def transcribe_stream(self, file_path, progress_callback=None):
        """Transcribe audio in real-time using Deepgram streaming."""
        try:
            # Configure Deepgram for optimal real-time performance
            options = {
                'smart_format': True,
                'model': 'nova-2',     # Fastest model
                'tier': 'enhanced',    # Better accuracy
                'punctuate': True,
                'language': 'en',      # Specify language
                'encoding': 'linear16',  # WAV format
                'sample_rate': 16000,   # 16kHz
                'channels': 1,          # Mono
                'interim_results': False,  # Only final results
                'profanity_filter': False,  # Skip filtering
                'numerals': False,        # Skip number conversion
            }

            # Initialize streaming
            socket = await self.dg_client.transcription.live(options)
            transcript_parts = []
            word_segments = []
            current_duration = 0
            total_size = os.path.getsize(file_path)
            bytes_processed = 0

            @socket.event
            async def on_open(socket):
                """Start streaming audio when socket opens."""
                logging.info("Deepgram streaming connection opened")
                
                # Stream audio in chunks
                chunk_size = 8192  # 8KB chunks for smooth streaming
                with open(file_path, 'rb') as audio:
                    while True:
                        chunk = audio.read(chunk_size)
                        if not chunk:
                            break
                        await socket.send(chunk)
                        bytes_processed += len(chunk)
                        if progress_callback:
                            progress = (bytes_processed / total_size) * 100
                            await progress_callback({
                                'stage': 'transcribing',
                                'progress': progress,
                                'text': ' '.join(transcript_parts)
                            })
                    await socket.finish()

            @socket.event
            async def on_message(socket, message):
                """Process transcription messages."""
                if message.is_final:
                    result = message.channel.alternatives[0]
                    transcript_parts.append(result.transcript)
                    
                    # Process word timings
                    if hasattr(result, 'words'):
                        for word in result.words:
                            word_segments.append({
                                'start': current_duration + word.start,
                                'end': current_duration + word.end,
                                'word': word.punctuated_word
                            })
                    
                    # Update duration
                    if hasattr(message, 'duration'):
                        current_duration += message.duration

            @socket.event
            async def on_error(socket, error):
                """Handle streaming errors."""
                logging.error(f"Deepgram streaming error: {error}")
                raise Exception(f"Streaming failed: {error}")

            @socket.event
            async def on_close(socket):
                """Handle socket close."""
                logging.info("Deepgram streaming connection closed")

            # Wait for streaming to complete
            await socket.wait_closed()
            
            return {
                'text': ' '.join(transcript_parts),
                'segments': word_segments,
                'duration': current_duration
            }

        except Exception as e:
            logging.error(f"Streaming transcription failed: {str(e)}")
            raise
                    
        except Exception as e:
            raise Exception(f"Stream transcription failed: {str(e)}")
