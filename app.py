import os
import sys
import logging
from pathlib import Path
from flask import Flask
from dotenv import load_dotenv
from models import db
from flask_migrate import Migrate
from routes import register_blueprints
from routes.errors import register_error_handlers
from services.file_handler import FileHandler

# Load environment variables first
load_dotenv()

# Configure logging once
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def create_app(config=None):
    """Create and configure Flask application"""
    app = Flask(__name__, static_url_path='/static', static_folder='static')
    
    # Load default configuration
    app.config.update(
        UPLOAD_FOLDER=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads'),
        MAX_CONTENT_LENGTH=8000 * 1024 * 1024,  # 8GB max file size
        SECRET_KEY=os.getenv('FLASK_SECRET_KEY', 'dev'),
        SQLALCHEMY_DATABASE_URI=os.getenv('SQLALCHEMY_DATABASE_URI', 'sqlite:///bentobox.db'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={
            'pool_size': 5,
            'max_overflow': 2,
            'pool_timeout': 30,
            'pool_recycle': 1800,
        }
    )
    
    # Override with custom config if provided
    if config:
        app.config.update(config)
    
    # Initialize extensions
    db.init_app(app)
    migrate = Migrate(app, db)  # Initialize Flask-Migrate
    
    # Ensure upload directories exist
    upload_dir = Path(app.config['UPLOAD_FOLDER'])
    temp_dir = upload_dir / 'temp'
    upload_dir.mkdir(exist_ok=True)
    temp_dir.mkdir(exist_ok=True)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Register blueprints
    register_blueprints(app)
    
    return app

def init_db(app):
    """Initialize database tables"""
    with app.app_context():
        db.create_all()

if __name__ == '__main__':
    app = create_app()
    init_db(app)  # Initialize database tables
    app.run(host='0.0.0.0', debug=True, port=5001)
