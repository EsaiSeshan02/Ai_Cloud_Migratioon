"""AWS scan compatibility helpers.

The only registered HTTP route is ``migration.aws_scan`` in
``migration_routes.py``. Keeping that route authoritative ensures its
authentication, CSRF, and cloud-session ownership checks cannot be bypassed.
"""

from app.services.aws_service import scan_resources


def scan_aws_for_session(session_id, target, user_id):
    """Internal compatibility helper; this module does not register a route."""
    return scan_resources(session_id, target, user_id=user_id)
