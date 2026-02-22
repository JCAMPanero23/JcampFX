"""
JcampFX — Config Override System for Backtesting

Allows temporary test settings without modifying src/config.py.

Usage
-----
    from src.config_override import get_config

    cfg = get_config()  # Loads defaults + overrides
    trendrider_min_cs = cfg.STRATEGY_TRENDRIDER_MIN_CS

    # Set override for testing
    cfg.set_override("STRATEGY_TRENDRIDER_MIN_CS", 85)
    cfg.save_overrides()

    # Revert to defaults
    cfg.reset_overrides()

Override File
-------------
Overrides are stored in `config_overrides.json` (git-ignored).
The file contains a dict mapping config constant names to override values.

Example config_overrides.json:
{
    "STRATEGY_TRENDRIDER_MIN_CS": 85,
    "STRATEGY_BREAKOUTRIDER_MIN_CS": 40,
    "STRATEGY_RANGERIDER_MAX_CS": 40,
    "BASE_RISK_PCT": 0.015
}
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

# Import ALL constants from src.config as baseline defaults
from src import config as _base_config

log = logging.getLogger(__name__)

_OVERRIDE_FILE = Path("config_overrides.json")
_DEFAULT_BACKUP_FILE = Path("config_defaults_backup.json")


class ConfigOverride:
    """
    Config container that loads defaults from src.config and applies overrides.

    Attributes mirror src.config constants. Access via cfg.CONSTANT_NAME.
    """

    def __init__(self) -> None:
        self._overrides: dict[str, Any] = {}
        self._load_defaults()
        self._load_overrides()

    def _load_defaults(self) -> None:
        """Copy all public constants from src.config into this instance."""
        for key in dir(_base_config):
            if not key.startswith("_") and key.isupper():
                setattr(self, key, getattr(_base_config, key))

    def _load_overrides(self) -> None:
        """Load overrides from config_overrides.json if it exists."""
        if not _OVERRIDE_FILE.exists():
            log.debug("No config overrides file found — using defaults")
            return

        try:
            with open(_OVERRIDE_FILE, "r", encoding="utf-8") as f:
                self._overrides = json.load(f)

            # Apply overrides to instance attributes
            for key, value in self._overrides.items():
                if hasattr(self, key):
                    setattr(self, key, value)
                    log.info(f"Config override: {key} = {value}")
                else:
                    log.warning(f"Unknown config override key: {key}")
        except Exception as exc:
            log.error(f"Failed to load config overrides: {exc}")

    def set_override(self, key: str, value: Any) -> None:
        """Set a temporary override for a config constant."""
        if not hasattr(self, key):
            log.warning(f"Setting override for unknown config key: {key}")

        self._overrides[key] = value
        setattr(self, key, value)
        log.info(f"Config override set: {key} = {value}")

    def save_overrides(self) -> None:
        """Save current overrides to config_overrides.json."""
        try:
            with open(_OVERRIDE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._overrides, f, indent=2, sort_keys=True)
            log.info(f"Saved {len(self._overrides)} config overrides to {_OVERRIDE_FILE}")
        except Exception as exc:
            log.error(f"Failed to save config overrides: {exc}")

    def reset_overrides(self) -> None:
        """Delete all overrides and revert to src.config defaults."""
        if _OVERRIDE_FILE.exists():
            _OVERRIDE_FILE.unlink()
            log.info("Deleted config overrides — reverted to defaults")

        self._overrides.clear()
        self._load_defaults()

    def save_as_defaults(self) -> None:
        """
        Save current ACTIVE settings (defaults + overrides) back to src.config.

        DANGER: This modifies src/config.py! Use with caution.
        Creates a backup at config_defaults_backup.json first.
        """
        # Create backup of original defaults
        defaults_backup = {}
        for key in dir(_base_config):
            if not key.startswith("_") and key.isupper():
                defaults_backup[key] = getattr(_base_config, key)

        with open(_DEFAULT_BACKUP_FILE, "w", encoding="utf-8") as f:
            json.dump(defaults_backup, f, indent=2, sort_keys=True)

        log.info(f"Created backup of defaults at {_DEFAULT_BACKUP_FILE}")

        # Update src/config.py with current values
        config_path = Path(_base_config.__file__)
        if not config_path.exists():
            raise FileNotFoundError(f"Cannot find src/config.py at {config_path}")

        # Read current config.py
        with open(config_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Replace constant assignments
        updated_lines = []
        for line in lines:
            updated = False
            for key, value in self._overrides.items():
                if line.strip().startswith(f"{key} ="):
                    # Preserve type formatting (int, float, str, etc.)
                    if isinstance(value, str):
                        updated_lines.append(f'{key} = "{value}"\n')
                    elif isinstance(value, dict):
                        updated_lines.append(f"{key} = {value}\n")
                    else:
                        updated_lines.append(f"{key} = {value}\n")
                    updated = True
                    log.info(f"Updated src/config.py: {key} = {value}")
                    break

            if not updated:
                updated_lines.append(line)

        # Write updated config.py
        with open(config_path, "w", encoding="utf-8") as f:
            f.writelines(updated_lines)

        log.info("Saved overrides as new defaults in src/config.py")
        log.warning(f"Backup of original defaults saved at {_DEFAULT_BACKUP_FILE}")

        # Clear overrides file since they're now defaults
        self.reset_overrides()

    def get_active_overrides(self) -> dict[str, Any]:
        """Return current active overrides as a dict."""
        return self._overrides.copy()

    def has_overrides(self) -> bool:
        """Return True if any overrides are active."""
        return len(self._overrides) > 0


# Singleton instance
_config_instance: ConfigOverride | None = None


def get_config() -> ConfigOverride:
    """Get the global config instance (singleton)."""
    global _config_instance
    if _config_instance is None:
        _config_instance = ConfigOverride()
    return _config_instance


def reset_config() -> None:
    """Reset the global config instance (used for testing)."""
    global _config_instance
    _config_instance = None
