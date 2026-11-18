"""macOS Keychain secure storage service for API keys and secrets."""

import logging
import subprocess
from typing import Optional

logger = logging.getLogger("MacAssistant.Keychain")

SERVICE_NAME = "MacAssistant"


class KeychainService:
    """Stores and retrieves sensitive credentials using native macOS /usr/bin/security Keychain."""

    @staticmethod
    def get_generic_password(account: str) -> Optional[str]:
        """Retrieves password or token for an account from macOS Keychain."""
        try:
            cmd = [
                "/usr/bin/security",
                "find-generic-password",
                "-s", SERVICE_NAME,
                "-a", account,
                "-w"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return res.stdout.strip()
        except Exception:
            return None

    @staticmethod
    def set_generic_password(account: str, password: str) -> bool:
        """Saves or updates password in macOS Keychain."""
        try:
            cmd = [
                "/usr/bin/security",
                "add-generic-password",
                "-U",
                "-s", SERVICE_NAME,
                "-a", account,
                "-w", password
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info("Securely saved '%s' in macOS Keychain under '%s'.", account, SERVICE_NAME)
            return True
        except Exception as e:
            logger.error("Failed saving password to macOS Keychain: %s", e)
            return False

    @staticmethod
    def delete_generic_password(account: str) -> bool:
        """Deletes generic password from macOS Keychain."""
        try:
            cmd = [
                "/usr/bin/security",
                "delete-generic-password",
                "-s", SERVICE_NAME,
                "-a", account
            ]
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            return True
        except Exception:
            return False
