"""
==========================================================
AI CLOUD MIGRATION
FLASK EXTENSIONS
==========================================================

Centralized initialization for:

    - Database
    - Password hashing
    - User login management
"""

from pathlib import Path

from flask import current_app
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate


# ==========================================================
# DATABASE
# ==========================================================

db = SQLAlchemy()
migrate = Migrate()


@migrate.configure
def configure_alembic(config):
    """Point Flask-Migrate at the repository-level Alembic configuration.

    Flask-Migrate otherwise looks for ``alembic.ini`` inside its default
    migration-script directory.  This project deliberately keeps that
    configuration at the repository root and its script environment in
    ``Migrations``.  Deriving both paths from the Flask application keeps the
    setup portable without an absolute local path.
    """
    project_root = Path(current_app.root_path).parent
    config.config_file_name = str(project_root / "alembic.ini")
    config.set_main_option("script_location", str(project_root / "Migrations"))
    return config


# ==========================================================
# PASSWORD HASHING
# ==========================================================

bcrypt = Bcrypt()


# ==========================================================
# LOGIN MANAGER
# ==========================================================

login_manager = LoginManager()
login_manager.session_protection = "strong"
csrf = CSRFProtect()

login_manager.login_view = "auth.login"

login_manager.login_message = (
    "Please log in to access this page."
)

login_manager.login_message_category = "warning"

# ==========================================================
# USER LOADER
# ==========================================================

@login_manager.user_loader
def load_user(user_id):

    from app.models.user import User

    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None
