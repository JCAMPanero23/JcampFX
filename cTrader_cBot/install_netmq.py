#!/usr/bin/env python3
"""
cTrader NetMQ Package Installer (Python)
Automates NetMQ package download for cTrader cBot
"""

import os
import subprocess
import sys
import urllib.request
from pathlib import Path


def print_header(text):
    """Print colored header."""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60 + "\n")


def print_step(step_num, text):
    """Print step with number."""
    print(f"[{step_num}/3] {text}")


def print_success(text):
    """Print success message."""
    print(f"✓ {text}")


def print_error(text):
    """Print error message."""
    print(f"✗ {text}", file=sys.stderr)


def download_nuget():
    """Download nuget.exe if not exists."""
    nuget_path = Path("nuget.exe")

    if nuget_path.exists():
        print_step(1, "nuget.exe already exists")
        return True

    print_step(1, "Downloading nuget.exe...")
    nuget_url = "https://dist.nuget.org/win-x86-commandline/latest/nuget.exe"

    try:
        urllib.request.urlretrieve(nuget_url, nuget_path)
        print_success("nuget.exe downloaded successfully")
        return True
    except Exception as e:
        print_error(f"Failed to download nuget.exe: {e}")
        return False


def create_packages_dir():
    """Create packages directory."""
    packages_dir = Path("packages")

    if packages_dir.exists():
        print_step(2, "Packages directory exists")
    else:
        packages_dir.mkdir()
        print_step(2, "Created packages directory")

    return packages_dir


def install_netmq(packages_dir):
    """Install NetMQ package using nuget.exe."""
    print_step(3, "Installing NetMQ package...")

    cmd = [
        "nuget.exe",
        "install",
        "NetMQ",
        "-OutputDirectory",
        str(packages_dir),
        "-Version",
        "4.0.1.13"
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        print_success("NetMQ package installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to install NetMQ: {e}")
        print(e.stdout)
        print(e.stderr, file=sys.stderr)
        return False


def show_next_steps(packages_dir):
    """Show next steps for user."""
    print_header("Installation Complete!")

    print("Next steps:")
    print("1. Open cTrader -> Automate -> New cBot")
    print("2. Click 'Manage References' -> 'Add Local File'")
    print("3. Navigate to:")
    print(f"   {packages_dir}\\NetMQ.4.0.1.13\\lib\\net47\\NetMQ.dll")
    print("4. Click 'OK' to add the reference")
    print()

    print("Or copy the DLL to cTrader's global packages folder:")
    print("   %USERPROFILE%\\Documents\\cAlgo\\Sources\\Packages\\")
    print()

    # Find and show NetMQ package location
    netmq_dirs = list(packages_dir.glob("NetMQ.*"))
    if netmq_dirs:
        netmq_dir = netmq_dirs[0]
        print(f"Package location:")
        print(f"   {netmq_dir}")
        print()

        dll_path = netmq_dir / "lib" / "net47" / "NetMQ.dll"
        if dll_path.exists():
            print(f"NetMQ.dll found at:")
            print(f"   {dll_path}")
        else:
            print("⚠ NetMQ.dll not found at expected location")
            print("  Check package structure manually")


def main():
    """Main installer function."""
    print_header("cTrader NetMQ Package Installer")

    # Change to script directory
    os.chdir(Path(__file__).parent)

    # Step 1: Download nuget.exe
    if not download_nuget():
        return 1

    print()

    # Step 2: Create packages directory
    packages_dir = create_packages_dir()

    print()

    # Step 3: Install NetMQ
    if not install_netmq(packages_dir):
        return 1

    print()

    # Show next steps
    show_next_steps(packages_dir)

    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        print("\nPress Enter to exit...")
        input()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nInstallation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        print("\nPress Enter to exit...")
        input()
        sys.exit(1)
