"""Centralized, safe error responses for browser pages and JSON APIs."""

from flask import jsonify, render_template, request
from flask_login import current_user
from flask_wtf.csrf import CSRFError

from app.security.logging_utils import log_event


def _is_api_request():
    return request.path.startswith("/api/")


def _response(status, message, template=None):
    if _is_api_request():
        return jsonify(success=False, message=message), status
    if template:
        return render_template(template), status
    return message, status


def register_error_handlers(app):
    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        log_event(app.logger, "csrf_rejected", operation="csrf", category="validation")
        if _is_api_request() and not current_user.is_authenticated:
            return jsonify(success=False, message="Please sign in to continue."), 401
        return _response(400, "Your form session expired. Please refresh the page and try again.")

    @app.errorhandler(400)
    def bad_request(error):
        return _response(400, "The request could not be processed.")

    @app.errorhandler(401)
    def unauthorized(error):
        return _response(401, "Please sign in to continue.")

    @app.errorhandler(403)
    def forbidden(error):
        return _response(403, "You do not have permission to access this resource.")

    @app.errorhandler(404)
    def not_found(error):
        return _response(404, "The requested page was not found.", "errors/404.html")

    @app.errorhandler(429)
    def rate_limited(error):
        return _response(429, "Too many requests. Please try again shortly.")

    @app.errorhandler(500)
    def internal_error(error):
        log_event(app.logger, "internal_error", operation="request", category="server")
        return _response(500, "An unexpected error occurred. Please try again later.", "errors/500.html")
