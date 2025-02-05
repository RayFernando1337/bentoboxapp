from flask import Blueprint, render_template
from models import Transcript

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Render index page"""
    transcripts = Transcript.query.order_by(Transcript.created_at.desc()).all()
    return render_template('index.html', transcripts=transcripts)

@main_bp.route('/transcribe')
def transcribe():
    """Render transcribe page"""
    transcripts = Transcript.query.order_by(Transcript.created_at.desc()).all()
    return render_template('transcribe.html', transcripts=transcripts, active_page='transcribe')

@main_bp.route('/create')
def create():
    """Render create page"""
    return render_template('create.html', active_page='create')

@main_bp.route('/schedule')
def schedule():
    """Render schedule page"""
    return render_template('schedule.html', active_page='schedule') 