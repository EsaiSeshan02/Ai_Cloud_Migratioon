"""Authenticated encryption helper for future persisted secret material.

Cloud credentials are deliberately not persisted by this prototype.  This
module exists for values that genuinely require protected at-rest storage.
"""

from cryptography.fernet import Fernet, InvalidToken


class CredentialCipher:
    def __init__(self, key):
        if not key:
            raise ValueError("CREDENTIAL_ENCRYPTION_KEY is required for encryption.")
        self._fernet = Fernet(key.encode("utf-8") if isinstance(key, str) else key)

    def encrypt(self, plaintext):
        if not isinstance(plaintext, str):
            raise ValueError("Only text values can be encrypted.")
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext):
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except (InvalidToken, AttributeError, UnicodeError) as error:
            raise ValueError("Encrypted value could not be decrypted.") from error
