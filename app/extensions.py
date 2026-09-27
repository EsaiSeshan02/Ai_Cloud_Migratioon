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

from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect


# ==========================================================
# DATABASE
# ==========================================================

db = SQLAlchemy()


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
