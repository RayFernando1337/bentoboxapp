import logging
from typing import Tuple
from flask import jsonify, Response
from werkzeug.exceptions import NotFound, BadRequest, RequestEntityTooLarge

logger = logging.getLogger(__name__)

def register_error_handlers(app):
    """Register error handlers for the application"""
    
    @app.errorhandler(NotFound)
    def handle_not_found(error) -> Tuple[Response, int]:
        return jsonify({'success': False, 'error': 'Resource not found'}), 404

    @app.errorhandler(BadRequest)
    def handle_bad_request(error) -> Tuple[Response, int]:
        return jsonify({'success': False, 'error': str(error)}), 400

    @app.errorhandler(RequestEntityTooLarge)
    def handle_file_too_large(error) -> Tuple[Response, int]:
        return jsonify({'success': False, 'error': 'File too large'}), 413

    @app.errorhandler(Exception)
    def handle_exception(error) -> Tuple[Response, int]:
        logger.error(f"Unhandled error: {str(error)}", exc_info=True)
        return jsonify({'success': False, 'error': 'Internal server error'}), 500 