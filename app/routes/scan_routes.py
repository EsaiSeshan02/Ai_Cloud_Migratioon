from app.services.aws_service import scan_resources


def scan_aws_for_session(session_id, target, user_id):
    """Internal compatibility helper; this module does not register a route."""
    return scan_resources(session_id, target, user_id=user_id)
