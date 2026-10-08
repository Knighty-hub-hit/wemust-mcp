"""Configuration and secret loading.

No personal data is hard-coded. Everything comes from environment variables,
and the account password / Notion token are read from the macOS Keychain when
available (recommended), with an environment-variable fallback (less safe).
"""
import os
import subprocess


class ConfigError(Exception):
    pass


def keychain_secret(service, account):
    """Read a generic password from the macOS Keychain (used in-memory only).

    Raises ConfigError if `security` is unavailable or the item is missing.
    """
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", service, "-a", account, "-w"],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        raise ConfigError("macOS `security` tool not found (Keychain only works on macOS)")
    if out.returncode != 0:
        raise ConfigError("Keychain item not found for service=%s" % service)
    return out.stdout.rstrip("\n")


class Config:
    """Runtime configuration, assembled from environment variables."""

    def __init__(self, env=None):
        e = env if env is not None else os.environ
        # Student account
        self.username = e.get("WEMUST_USERNAME") or None
        self.keychain_service = e.get("WEMUST_KEYCHAIN_SERVICE", "wemust")
        self._password_env = e.get("WEMUST_PASSWORD") or None
        # Grades are OFF unless explicitly enabled
        self.enable_grades = e.get("WEMUST_ENABLE_GRADES") == "1"
        # Notion (optional sync feature)
        self._notion_token_env = e.get("WEMUST_NOTION_TOKEN") or None
        self.notion_keychain_service = e.get("WEMUST_NOTION_KEYCHAIN_SERVICE", "wemust-notion")
        self.notion_keychain_account = e.get("WEMUST_NOTION_KEYCHAIN_ACCOUNT", "notion")
        self.notion_page_id = e.get("WEMUST_NOTION_PAGE_ID") or None

    # --- student credentials ---
    def require_username(self):
        if not self.username:
            raise ConfigError("WEMUST_USERNAME is not set (your student ID / username).")
        return self.username

    def get_password(self):
        """Keychain first (recommended), then WEMUST_PASSWORD env (less safe)."""
        self.require_username()
        try:
            return keychain_secret(self.keychain_service, self.username)
        except ConfigError:
            pass
        if self._password_env:
            return self._password_env
        raise ConfigError(
            "No password available. Store it in the Keychain:\n"
            "  security add-generic-password -U -s %s -a %s -w\n"
            "or set WEMUST_PASSWORD (less safe)." % (self.keychain_service, self.username)
        )

    # --- notion (optional) ---
    def get_notion_token(self):
        if self._notion_token_env:
            return self._notion_token_env
        return keychain_secret(self.notion_keychain_service, self.notion_keychain_account)

    def require_notion(self):
        if not self.notion_page_id:
            raise ConfigError("WEMUST_NOTION_PAGE_ID is not set.")
        return self.get_notion_token(), self.notion_page_id
