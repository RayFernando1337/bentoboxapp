import os
import logging
import asyncio
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)

class AudioProcessingError(Exception):
    """Raised when audio processing fails"""
    pass

async def extract_audio(video_path: str, audio_path: str, progress_callback: Optional[Callable] = None) -> str:
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
                'stage': 'processing_extracting_audio',
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
            raise AudioProcessingError(f"FFmpeg error: {stderr.decode()}")

        if progress_callback:
            await progress_callback({
                'stage': 'processing_extracting_audio',
                'progress': 20,
                'text': 'Audio extraction complete'
            })

        return audio_path

    except Exception as e:
        logger.error(f"Error extracting audio: {str(e)}")
        raise AudioProcessingError(str(e)) 