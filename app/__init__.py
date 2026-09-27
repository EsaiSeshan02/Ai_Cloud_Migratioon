"""
==========================================================
AI CLOUD MIGRATION
APPLICATION FACTORY
==========================================================
"""

import os

from flask import Flask, jsonify, request
from flask_login import current_user

from config import Config, DevelopmentConfig
from app.extensions import (
    db,
    bcrypt,
    csrf,
    login_manager,
)
from app.error_handlers import register_error_handlers
from app.security.logging_utils import configure_logging, log_event
from app.security.rate_limit import limiter

from app.models.migration import (
    Migration,
    MigrationFile
)

# ==========================================================
# CREATE APPLICATION
# ==========================================================

def create_app(test_config=None):

    app = Flask(

        __name__,

        template_folder="templates",

        static_folder="static"

    )


    # ======================================================
    # LOAD CONFIGURATION
    # ======================================================

    config_class = DevelopmentConfig if os.getenv("APP_ENV", "").lower() == "development" else Config
    app.config.from_object(config_class)
    if test_config:
        app.config.update(test_config)

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY must be configured outside development mode.")

    # ======================================================
    # INITIALIZE EXTENSIONS
    # ======================================================

    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    configure_logging(app)
    register_error_handlers(app)

    # ==========================================================
    # DATABASE MODELS
    # ==========================================================

    from app.models.user import User
    
    from app.models.migration import (
        Migration,
        MigrationFile
    )
    from app.models.report import Report
    from app.database.migration_schema import upgrade_phase2_migration_schema

    # Add only the Phase 2 persistence columns when upgrading an existing
    # database.  This never creates, deletes, or resets a user's database.
    with app.app_context():
        upgrade_phase2_migration_schema()
        # A worker cannot survive a Flask process restart.  Persist the
        # interruption so its owner can explicitly reconnect and resume.
        from app.services.s3_migration_service import mark_incomplete_migrations_interrupted
        from app.services.lambda_migration_service import mark_incomplete_lambda_migrations_requires_review
        mark_incomplete_migrations_interrupted()
        mark_incomplete_lambda_migrations_requires_review()

    @login_manager.unauthorized_handler
    def unauthorized():
        if request.path.startswith("/api/"):
            return jsonify(success=False, message="Please sign in to continue."), 401
        return login_manager.redirect_to_login(request.url)

    @app.before_request
    def limit_sensitive_requests():
        if request.method != "POST":
            return None
        if request.path in {"/login", "/register"}:
            limiter.enforce(60, 300)
        elif request.path.startswith(("/api/aws/connect", "/api/azure/connect", "/api/migration/")):
            limiter.enforce(120, 300)
        return None


    # ======================================================
    # CREATE REQUIRED FOLDERS
    # ======================================================

    os.makedirs(

        app.config["UPLOAD_FOLDER"],

        exist_ok=True

    )


    # ======================================================
    # REGISTER BLUEPRINTS
    # ======================================================

    from app.routes.home_routes import home_bp

    app.register_blueprint(

        home_bp

    )


    from app.routes.migration_routes import migration_bp

    app.register_blueprint(

        migration_bp

    )

    from app.routes.auth_routes import auth_bp

    app.register_blueprint(auth_bp)

    @app.after_request
    def add_security_headers(response):
        if app.config.get("SECURITY_HEADERS_ENABLED", True):
            response.headers.setdefault("Content-Security-Policy", app.config["CONTENT_SECURITY_POLICY"])
            response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if app.config.get("HSTS_ENABLED"):
            response.headers.setdefault("Strict-Transport-Security", f"max-age={app.config['HSTS_MAX_AGE']}; includeSubDomains")
        return response


    # ======================================================
    # RETURN APPLICATION
    # ======================================================

    return app
