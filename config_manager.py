#!/usr/bin/env python3
"""
JcampFX — Config Override Manager CLI

Quick commands to manage temporary config overrides for backtesting.

Usage
-----
    # Set overrides for threshold testing (CS 85/40/40)
    python config_manager.py set STRATEGY_TRENDRIDER_MIN_CS 85
    python config_manager.py set STRATEGY_BREAKOUTRIDER_MIN_CS 40
    python config_manager.py set STRATEGY_RANGERIDER_MAX_CS 40

    # Bulk set from preset (recommended for common tests)
    python config_manager.py preset threshold-85-40-40

    # View current overrides
    python config_manager.py show

    # Reset to defaults (delete all overrides)
    python config_manager.py reset

    # Save current overrides as new defaults in src/config.py (DANGER!)
    python config_manager.py save-as-defaults

    # Restore from backup (if save-as-defaults was used)
    python config_manager.py restore-backup
"""

import sys
import json
from pathlib import Path
from src.config_override import get_config


# Preset configurations for common tests
PRESETS = {
    "threshold-85-40-40": {
        "name": "DCRD Threshold Adjustment (CS 85/40/40)",
        "description": "Shift more time to Transitional regime for BreakoutRider",
        "overrides": {
            "STRATEGY_TRENDRIDER_MIN_CS": 85,
            "STRATEGY_BREAKOUTRIDER_MIN_CS": 40,
            "STRATEGY_RANGERIDER_MAX_CS": 40,
        },
    },
    "threshold-default": {
        "name": "Default Thresholds (CS 70/30/30)",
        "description": "Original PRD thresholds",
        "overrides": {
            "STRATEGY_TRENDRIDER_MIN_CS": 70,
            "STRATEGY_BREAKOUTRIDER_MIN_CS": 30,
            "STRATEGY_RANGERIDER_MAX_CS": 30,
        },
    },
    "price-level-cooldown": {
        "name": "Price Level Cooldown Test",
        "description": "Prevent re-entry at same price level (Task 1)",
        "overrides": {
            "PRICE_LEVEL_COOLDOWN_ENABLED": True,
            "PRICE_LEVEL_COOLDOWN_PIPS": 20,
            "PRICE_LEVEL_COOLDOWN_HOURS": 4,
        },
    },
    "aggressive-partial-exit": {
        "name": "Aggressive Partial Exit (80% at 1.5R)",
        "description": "Take more profit early, smaller runners",
        "overrides": {
            "PARTIAL_EXIT_TIERS": [
                (85, 0.80),  # CS > 85 → close 80% (was 60%)
                (70, 0.85),  # CS 70–85 → close 85% (was 70%)
                (30, 0.90),  # CS 30–70 → close 90% (was 75%)
                (0,  0.95),  # CS < 30  → close 95% (was 80%)
            ],
        },
    },
    "conservative-partial-exit": {
        "name": "Conservative Partial Exit (40% at 1.5R)",
        "description": "Smaller profit lock, larger runners",
        "overrides": {
            "PARTIAL_EXIT_TIERS": [
                (85, 0.40),  # CS > 85 → close 40% (was 60%)
                (70, 0.50),  # CS 70–85 → close 50% (was 70%)
                (30, 0.60),  # CS 30–70 → close 60% (was 75%)
                (0,  0.70),  # CS < 30  → close 70% (was 80%)
            ],
        },
    },
    "tight-chandelier": {
        "name": "Tight Chandelier Floors",
        "description": "Tighter trailing stops on runners",
        "overrides": {
            "CHANDELIER_FLOOR_MAJORS": 10,  # was 15
            "CHANDELIER_FLOOR_JPY": 15,     # was 25
        },
    },
    "loose-chandelier": {
        "name": "Loose Chandelier Floors",
        "description": "Wider trailing stops on runners",
        "overrides": {
            "CHANDELIER_FLOOR_MAJORS": 25,  # was 15
            "CHANDELIER_FLOOR_JPY": 35,     # was 25
        },
    },
    "high-risk": {
        "name": "High Risk Testing (2% base)",
        "description": "Test with elevated risk per trade",
        "overrides": {
            "BASE_RISK_PCT": 0.02,
            "MAX_RISK_PCT": 0.04,
        },
    },
    "low-risk": {
        "name": "Low Risk Testing (0.5% base)",
        "description": "Conservative risk for stability testing",
        "overrides": {
            "BASE_RISK_PCT": 0.005,
            "MAX_RISK_PCT": 0.015,
        },
    },
}


def cmd_show() -> None:
    """Show current config overrides."""
    cfg = get_config()
    overrides = cfg.get_active_overrides()

    print("Config Override Status")
    print("=" * 60)

    if not overrides:
        print("No overrides active — using defaults from src/config.py")
        return

    print(f"Active overrides ({len(overrides)}):\n")
    for key, value in sorted(overrides.items()):
        print(f"  {key:40s} = {value}")

    print("\nTo reset: python config_manager.py reset")


def cmd_set(key: str, value: str) -> None:
    """Set a single config override."""
    cfg = get_config()

    # Infer type from current default value if key exists
    if hasattr(cfg, key):
        default_val = getattr(cfg, key)
        if isinstance(default_val, int):
            typed_value = int(value)
        elif isinstance(default_val, float):
            typed_value = float(value)
        elif isinstance(default_val, bool):
            typed_value = value.lower() in ("true", "1", "yes")
        else:
            typed_value = value
    else:
        # Try to infer from string
        try:
            typed_value = int(value)
        except ValueError:
            try:
                typed_value = float(value)
            except ValueError:
                typed_value = value

    cfg.set_override(key, typed_value)
    cfg.save_overrides()

    print(f"[OK] Set override: {key} = {typed_value}")
    print(f"  Saved to config_overrides.json")


def cmd_reset() -> None:
    """Reset all overrides (delete config_overrides.json)."""
    cfg = get_config()
    cfg.reset_overrides()
    print("[OK] Reset all overrides — now using src/config.py defaults")


def cmd_preset(preset_name: str) -> None:
    """Apply a preset configuration."""
    if preset_name not in PRESETS:
        print(f"[ERROR] Unknown preset: {preset_name}")
        print("\nAvailable presets:")
        for name, info in PRESETS.items():
            print(f"  {name:25s} — {info['description']}")
        sys.exit(1)

    preset = PRESETS[preset_name]
    print(f"Applying preset: {preset['name']}")
    print(f"  {preset['description']}\n")

    cfg = get_config()
    for key, value in preset["overrides"].items():
        cfg.set_override(key, value)
        print(f"  {key:40s} = {value}")

    cfg.save_overrides()
    print(f"\n[OK] Applied {len(preset['overrides'])} overrides")


def cmd_save_as_defaults() -> None:
    """Save current overrides as new defaults in src/config.py."""
    cfg = get_config()
    overrides = cfg.get_active_overrides()

    if not overrides:
        print("[ERROR] No overrides active — nothing to save")
        return

    print("WARNING: This will modify src/config.py!")
    print("=" * 60)
    print("Current overrides to be saved as defaults:\n")
    for key, value in sorted(overrides.items()):
        print(f"  {key:40s} = {value}")

    print("\nA backup will be saved to config_defaults_backup.json")
    confirm = input("\nProceed? (yes/no): ").strip().lower()

    if confirm != "yes":
        print("[ABORTED]")
        return

    cfg.save_as_defaults()
    print("[OK] Saved overrides as new defaults in src/config.py")
    print("  Backup created: config_defaults_backup.json")
    print("  Overrides file deleted (now defaults)")


def cmd_restore_backup() -> None:
    """Restore src/config.py from backup (if save-as-defaults was used)."""
    backup_file = Path("config_defaults_backup.json")
    if not backup_file.exists():
        print("[ERROR] No backup file found (config_defaults_backup.json)")
        return

    print("WARNING: This will restore src/config.py from backup")
    print("=" * 60)
    confirm = input("Proceed? (yes/no): ").strip().lower()

    if confirm != "yes":
        print("[ABORTED]")
        return

    # Load backup
    with open(backup_file, "r", encoding="utf-8") as f:
        backup = json.load(f)

    # Update src/config.py
    from src import config as _base_config
    config_path = Path(_base_config.__file__)

    with open(config_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    updated_lines = []
    for line in lines:
        updated = False
        for key, value in backup.items():
            if line.strip().startswith(f"{key} ="):
                if isinstance(value, str):
                    updated_lines.append(f'{key} = "{value}"\n')
                elif isinstance(value, dict):
                    updated_lines.append(f"{key} = {value}\n")
                else:
                    updated_lines.append(f"{key} = {value}\n")
                updated = True
                break

        if not updated:
            updated_lines.append(line)

    with open(config_path, "w", encoding="utf-8") as f:
        f.writelines(updated_lines)

    print(f"[OK] Restored {len(backup)} constants from backup")


def cmd_list_presets() -> None:
    """List all available presets."""
    print("Available Config Presets")
    print("=" * 60)
    for name, info in PRESETS.items():
        print(f"\n{name}")
        print(f"  {info['description']}")
        print("  Overrides:")
        for key, value in info["overrides"].items():
            print(f"    {key:40s} = {value}")


def cmd_save_custom(name: str) -> None:
    """Save current overrides as a custom preset."""
    cfg = get_config()
    overrides = cfg.get_active_overrides()

    if not overrides:
        print("[ERROR] No overrides active — nothing to save")
        return

    custom_file = Path(f"config_custom_{name}.json")

    custom_preset = {
        "name": name,
        "description": f"Custom configuration: {name}",
        "overrides": overrides,
    }

    with open(custom_file, "w", encoding="utf-8") as f:
        json.dump(custom_preset, f, indent=2, sort_keys=True)

    print(f"[OK] Saved custom preset: {name}")
    print(f"  File: {custom_file}")
    print(f"  Overrides: {len(overrides)}")
    print()
    print(f"To load: python config_manager.py load-custom {name}")


def cmd_load_custom(name: str) -> None:
    """Load a custom preset from file."""
    custom_file = Path(f"config_custom_{name}.json")

    if not custom_file.exists():
        print(f"[ERROR] Custom preset not found: {custom_file}")
        return

    with open(custom_file, "r", encoding="utf-8") as f:
        custom_preset = json.load(f)

    print(f"Loading custom preset: {custom_preset.get('name', name)}")
    print(f"  {custom_preset.get('description', 'No description')}\n")

    cfg = get_config()
    for key, value in custom_preset["overrides"].items():
        cfg.set_override(key, value)
        print(f"  {key:40s} = {value}")

    cfg.save_overrides()
    print(f"\n[OK] Loaded {len(custom_preset['overrides'])} overrides from {name}")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "show":
        cmd_show()
    elif cmd == "set":
        if len(sys.argv) < 4:
            print("Usage: python config_manager.py set KEY VALUE")
            sys.exit(1)
        cmd_set(sys.argv[2], sys.argv[3])
    elif cmd == "reset":
        cmd_reset()
    elif cmd == "preset":
        if len(sys.argv) < 3:
            print("Usage: python config_manager.py preset PRESET_NAME")
            print("\nAvailable presets:")
            cmd_list_presets()
            sys.exit(1)
        cmd_preset(sys.argv[2])
    elif cmd == "list-presets":
        cmd_list_presets()
    elif cmd == "save-custom":
        if len(sys.argv) < 3:
            print("Usage: python config_manager.py save-custom NAME")
            sys.exit(1)
        cmd_save_custom(sys.argv[2])
    elif cmd == "load-custom":
        if len(sys.argv) < 3:
            print("Usage: python config_manager.py load-custom NAME")
            sys.exit(1)
        cmd_load_custom(sys.argv[2])
    elif cmd == "save-as-defaults":
        cmd_save_as_defaults()
    elif cmd == "restore-backup":
        cmd_restore_backup()
    else:
        print(f"[ERROR] Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
