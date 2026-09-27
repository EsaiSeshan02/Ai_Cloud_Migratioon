"""Authentication routes for the existing Flask-Login/Bcrypt setup."""

import re

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError

from app.extensions import bcrypt, db
from app.models.user import User
from app.security.audit_logger import audit_event


auth_bp = Blueprint("auth", __name__)

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalise_email(value):
    return (value or "").strip().lower()


def _safe_next_url(value):
    value = value or ""
    return value if value.startswith("/") and not value.startswith("//") else url_for("home.home")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("home.home"))

    if request.method == "GET":
        return render_template("auth/register.html")

    name = (request.form.get("fullname") or "").strip()
    email = _normalise_email(request.form.get("email"))
    password = request.form.get("password") or ""
    confirmation = request.form.get("confirm_password") or ""

    if not 2 <= len(name) <= 100 or not EMAIL_PATTERN.fullmatch(email):
        flash("Please enter a valid name and email address.", "error")
        return render_template("auth/register.html"), 400
    if len(password) < 12:
        flash("Password must be at least 12 characters.", "error")
        return render_template("auth/register.html"), 400
    if password != confirmation:
        flash("Passwords do not match.", "error")
        return render_template("auth/register.html"), 400
    if User.query.filter_by(email=email).first():
        flash("Unable to create an account with those details.", "error")
        return render_template("auth/register.html"), 400

    user = User(
        name=name,
        email=email,
        password_hash=bcrypt.generate_password_hash(password).decode("utf-8"),
    )
    try:
        db.session.add(user)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("Unable to create an account with those details.", "error")
        return render_template("auth/register.html"), 400

    audit_event("registration_succeeded", user_id=user.id, status="success", category="auth")
    login_user(user)
    return redirect(url_for("home.home"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home.home"))

    if request.method == "GET":
        return render_template("auth/login.html")

    email = _normalise_email(request.form.get("email"))
    password = request.form.get("password") or ""
    user = User.query.filter_by(email=email).first() if EMAIL_PATTERN.fullmatch(email) else None

    if not user or not bcrypt.check_password_hash(user.password_hash, password):
        audit_event("login_failed", operation="login", status="failed", category="auth")
        flash("Invalid email or password.", "error")
        return render_template("auth/login.html"), 401

    login_user(user, remember=bool(request.form.get("remember")))
    audit_event("login_succeeded", user_id=user.id, status="success", category="auth")
    return redirect(_safe_next_url(request.args.get("next")))


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    user_id = current_user.id
    logout_user()
    audit_event("logout_succeeded", user_id=user_id, status="success", category="auth")
    return redirect(url_for("home.home"))


@auth_bp.route("/api/auth/me", methods=["GET"])
@login_required
def current_user_details():
    return jsonify(success=True, user={"id": current_user.id, "name": current_user.name, "email": current_user.email})
