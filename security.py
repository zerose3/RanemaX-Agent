"""
Encryption helpers for config.json.

Instead of keeping your Supabase login sitting in plain text on the
device, this lets you encrypt config.json into config.enc, protected by
a passphrase you type each time the agent starts. If the device is ever
compromised, the attacker gets an encrypted blob, not your credentials.
"""

import base64
import getpass
import json
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

PBKDF2_ITERATIONS = 390_000


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))


def encrypt_config(plain_config: dict, passphrase: str) -> bytes:
    salt = os.urandom(16)
    key = _derive_key(passphrase, salt)
    token = Fernet(key).encrypt(json.dumps(plain_config).encode())
    # Store salt alongside the ciphertext so we can re-derive the key later.
    return base64.urlsafe_b64encode(salt) + b"." + token


def decrypt_config(blob: bytes, passphrase: str) -> dict:
    salt_b64, token = blob.split(b".", 1)
    salt = base64.urlsafe_b64decode(salt_b64)
    key = _derive_key(passphrase, salt)
    try:
        data = Fernet(key).decrypt(token)
    except InvalidToken:
        raise ValueError("Passphrase salah atau file config.enc rusak.")
    return json.loads(data)


def prompt_passphrase(confirm: bool = False) -> str:
    passphrase = getpass.getpass("Passphrase untuk config.enc: ")
    if confirm:
        again = getpass.getpass("Ketik ulang passphrase: ")
        if passphrase != again:
            raise ValueError("Passphrase tidak cocok.")
    if not passphrase:
        raise ValueError("Passphrase tidak boleh kosong.")
    return passphrase


def harden_permissions(path: Path):
    """Restricts a file to owner-read/write only (chmod 600)."""
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass  # Best-effort; some filesystems (e.g. shared storage) reject this.
