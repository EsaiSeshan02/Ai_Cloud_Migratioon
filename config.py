"""
==========================================================
AI CLOUD MIGRATION
APPLICATION CONFIGURATION
==========================================================
"""

import os
import secrets
from datetime import timedelta

from dotenv import load_dotenv


# ==========================================================
# LOAD ENVIRONMENT VARIABLES
# ==========================================================

load_dotenv()


# ==========================================================
# BASE CONFIGURATION
# ==========================================================

class Config:

    APP_ENV = os.getenv("APP_ENV", os.getenv("FLASK_ENV", "production")).lower()
    TESTING = False

    # ------------------------------------------------------
    # FLASK
    # ------------------------------------------------------

    SECRET_KEY = os.getenv("SECRET_KEY")


    # ------------------------------------------------------
    # DATABASE
    # ------------------------------------------------------

    BASE_DIR = os.path.abspath(
        os.path.dirname(__file__)
    )

    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "sqlite:///" + os.path.join(
            BASE_DIR,
            "app",
            "database",
            "database.db"
        )
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = os.getenv(
        "SESSION_COOKIE_SECURE",
        "true" if APP_ENV == "production" else "false"
    ).lower() == "true"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = SESSION_COOKIE_SAMESITE
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_REFRESH_EACH_REQUEST = True
    SECURITY_HEADERS_ENABLED = True
    HSTS_ENABLED = os.getenv("HSTS_ENABLED", "false").lower() == "true"
    HSTS_MAX_AGE = int(os.getenv("HSTS_MAX_AGE", "31536000"))
    CONTENT_SECURITY_POLICY = os.getenv(
        "CONTENT_SECURITY_POLICY",
        "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline' https://unpkg.com; font-src 'self' data:; connect-src 'self'; "
        "base-uri 'self'; frame-ancestors 'self'; form-action 'self'",
    )


    # ------------------------------------------------------
    # SECURITY
    # ------------------------------------------------------

    CREDENTIAL_ENCRYPTION_KEY = os.getenv(
        "CREDENTIAL_ENCRYPTION_KEY"
    )


    # ------------------------------------------------------
    # FILE UPLOADS
    # ------------------------------------------------------

    UPLOAD_FOLDER = os.path.join(
        BASE_DIR,
        "app",
        "uploads"
    )

    MAX_CONTENT_LENGTH = (
        100 * 1024 * 1024
    )
    MAX_FORM_MEMORY_SIZE = 1 * 1024 * 1024
    MAX_FORM_PARTS = 100


    # ------------------------------------------------------
    # MIGRATION
    # ------------------------------------------------------

    STORAGE_BATCH_SIZE_GB = 10

    STORAGE_BATCH_SIZE_BYTES = (

        STORAGE_BATCH_SIZE_GB

        * 1024

        * 1024

        * 1024

    )


class DevelopmentConfig(Config):
    """Local-only defaults that avoid a hard-coded application secret."""

    APP_ENV = "development"
    SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_urlsafe(32)
    SESSION_COOKIE_SECURE = False
