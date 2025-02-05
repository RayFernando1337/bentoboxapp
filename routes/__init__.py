from flask import Flask
from .main import main_bp
from .transcription import transcription_bp

def register_blueprints(app: Flask):
    """Register Flask blueprints"""
    app.register_blueprint(main_bp)
    app.register_blueprint(transcription_bp, url_prefix='/api/transcription') 