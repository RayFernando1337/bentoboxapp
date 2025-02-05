from datetime import datetime, timedelta
from pathlib import Path
import logging
from flask import Flask
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

class FileHandler:
    """Handle file operations with proper cleanup"""
    
    def __init__(self, app: Flask):
        self.app = app
        self.upload_dir = Path(app.config['UPLOAD_FOLDER'])
        self.temp_dir = self.upload_dir / 'temp'
        self.max_age = timedelta(hours=24)
        
        # Ensure directories exist
        self.upload_dir.mkdir(exist_ok=True)
        self.temp_dir.mkdir(exist_ok=True)
    
    def save_upload(self, file, filename: str) -> Path:
        """Save uploaded file with secure filename"""
        filepath = self.upload_dir / secure_filename(filename)
        file.save(filepath)
        return filepath
    
    def cleanup_old_files(self) -> None:
        """Clean up files older than max_age"""
        current_time = datetime.now()
        try:
            for file in self.temp_dir.glob('*'):
                if file.is_file():
                    file_age = current_time - datetime.fromtimestamp(file.stat().st_mtime)
                    if file_age > self.max_age:
                        file.unlink()
                        logger.info(f"Cleaned up old file: {file}")
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
    
    def cleanup_files(self, *files: Path) -> None:
        """Clean up specified files"""
        for file in files:
            try:
                if file and file.exists():
                    file.unlink()
                    logger.info(f"Cleaned up file: {file}")
            except Exception as e:
                logger.error(f"Error cleaning up file {file}: {str(e)}") 