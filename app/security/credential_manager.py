"""Credential lifecycle policy.

The application intentionally keeps SDK credential objects transient and does
not serialize raw cloud credentials into SQLite.  Use this module as the
single policy boundary if an encrypted persisted credential feature is added.
"""

from app.security.encryption import CredentialCipher


def credential_cipher_from_config(config):
    """Return a cipher only when encrypted persistence is explicitly enabled."""
    key = config.get("CREDENTIAL_ENCRYPTION_KEY")
    return CredentialCipher(key) if key else None
