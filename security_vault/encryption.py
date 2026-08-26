"""
GodVault - simple secure vault using Fernet (cryptography)
- Supports passphrase (NEXUS_MASTER_KEY) or direct Fernet key
- Persists encrypted secrets to security_vault/secure_keys.json

NOTE: For production, ensure NEXUS_MASTER_KEY is set to a stable secret (not stored in this repo).
"""
import os
import json
import base64
import logging
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger("security_vault.encryption")

DEFAULT_STORE = Path("security_vault/secure_keys.json")
DEFAULT_STORE.parent.mkdir(parents=True, exist_ok=True)


def _derive_fernet_key_from_passphrase(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=390000,
        backend=default_backend()
    )
    key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode('utf-8')))
    return key


class GodAuth:
    """Simple file-backed vault using Fernet

    JSON format:
    {
      "salt": "base64...",
      "master_key_provided": true|false,
      "secrets": { "service": "<fernet-encrypted-base64>" }
    }

    If NEXUS_MASTER_KEY env var is provided it will be used (either a 44-char Fernet key or a passphrase).
    Otherwise a new master key will be generated and persisted in the store (less secure).
    """

    def __init__(self, store_path: Optional[Path] = None):
        self.store_path = Path(store_path or DEFAULT_STORE)
        self._data = {"secrets": {}}
        self._salt = None
        self._fernet = None
        self._load_or_init()

    def _load_or_init(self):
        # Load existing store if exists
        if self.store_path.exists():
            try:
                raw = json.loads(self.store_path.read_text(encoding='utf-8'))
                self._data = raw if isinstance(raw, dict) else {"secrets": {}}
                salt_b64 = self._data.get('salt')
                if salt_b64:
                    self._salt = base64.b64decode(salt_b64)
                else:
                    # create new salt
                    self._salt = os.urandom(16)
                    self._data['salt'] = base64.b64encode(self._salt).decode('utf-8')
            except Exception as e:
                logger.warning("Failed to load vault store, initializing new: %s", e)
                self._salt = os.urandom(16)
                self._data = {"salt": base64.b64encode(self._salt).decode('utf-8'), "secrets": {}}
        else:
            self._salt = os.urandom(16)
            self._data = {"salt": base64.b64encode(self._salt).decode('utf-8'), "secrets": {}}
            self._persist()

        # Resolve master key (env or derive)
        env_key = os.getenv('NEXUS_MASTER_KEY')
        if env_key:
            # if env_key looks like a Fernet key (44 chars urlsafe) accept it
            try:
                if len(env_key) == 44:
                    fernet_key = env_key.encode('utf-8')
                else:
                    # derive from passphrase
                    fernet_key = _derive_fernet_key_from_passphrase(env_key, self._salt)
                self._fernet = Fernet(fernet_key)
                self._data['master_key_provided'] = True
            except Exception as e:
                logger.exception('Failed to use NEXUS_MASTER_KEY from environment: %s', e)
                self._fernet = Fernet(Fernet.generate_key())
                self._data['master_key_provided'] = False
                self._persist()
        else:
            # No env var; if a master key is stored in file, try to use it
            stored_master = self._data.get('_master_key')
            if stored_master:
                try:
                    fernet_key = base64.b64decode(stored_master)
                    self._fernet = Fernet(fernet_key)
                    self._data['master_key_provided'] = False
                except Exception as e:
                    logger.warning('Stored master key invalid, regenerating: %s', e)
                    self._fernet = Fernet(Fernet.generate_key())
                    self._data['_master_key'] = base64.b64encode(self._fernet._signing_key + self._fernet._encryption_key if hasattr(self._fernet, '_signing_key') else self._fernet.generate_key()).decode('utf-8')
                    self._persist()
            else:
                # generate a new master key and persist it (not ideal but necessary fallback)
                self._fernet = Fernet(Fernet.generate_key())
                self._data['_master_key'] = base64.b64encode(self._fernet._signing_key + self._fernet._encryption_key if hasattr(self._fernet, '_signing_key') else self._fernet.generate_key()).decode('utf-8')
                self._data['master_key_provided'] = False
                self._persist()

    def _persist(self):
        try:
            self.store_path.write_text(json.dumps(self._data, indent=2), encoding='utf-8')
            os.chmod(self.store_path, 0o600)
        except Exception as e:
            logger.exception("Failed to persist vault: %s", e)

    def store_secret(self, name: str, secret: str) -> None:
        if not self._fernet:
            raise RuntimeError('Vault not initialized')
        token = self._fernet.encrypt(secret.encode('utf-8'))
        self._data.setdefault('secrets', {})[name] = base64.b64encode(token).decode('utf-8')
        self._persist()

    def get_secret(self, name: str) -> Optional[str]:
        if not self._fernet:
            raise RuntimeError('Vault not initialized')
        enc_b64 = self._data.get('secrets', {}).get(name)
        if not enc_b64:
            return None
        try:
            token = base64.b64decode(enc_b64)
            plain = self._fernet.decrypt(token)
            return plain.decode('utf-8')
        except Exception as e:
            logger.exception('Failed to decrypt secret %s: %s', name, e)
            return None


# Backwards compatibility alias
GodVault = GodAuth
