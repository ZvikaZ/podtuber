#!/usr/bin/env python3
"""Launch Google's Android Auto Desktop Head Unit with a connected phone."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "tools" / "android-auto-dhu.ini"


def executable(name: str, relative_to_sdk: Path) -> Path:
    from_path = shutil.which(name)
    if from_path:
        return Path(from_path)

    sdk_roots = [
        os.environ.get("ANDROID_SDK_ROOT"),
        os.environ.get("ANDROID_HOME"),
        r"C:\Zvika\SOFTWARE\android-sdk",
        str(Path.home() / "AppData" / "Local" / "Android" / "Sdk"),
    ]
    for value in sdk_roots:
        if not value:
            continue
        candidate = Path(value) / relative_to_sdk
        if candidate.is_file():
            return candidate

    raise FileNotFoundError(
        f"Could not find {name}. Set ANDROID_SDK_ROOT to the Android SDK directory."
    )


def adb_devices(adb: Path) -> tuple[list[str], list[str]]:
    result = subprocess.run(
        [str(adb), "devices"], check=True, text=True, capture_output=True
    )
    connected: list[str] = []
    unauthorized: list[str] = []
    for line in result.stdout.splitlines()[1:]:
        if "\t" not in line:
            continue
        serial, state = line.split("\t", 1)
        if state == "device":
            connected.append(serial)
        elif state == "unauthorized":
            unauthorized.append(serial)
    return connected, unauthorized


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the real Android Auto UI from a USB-connected Android phone."
    )
    parser.add_argument("--serial", help="ADB serial when more than one device is connected")
    parser.add_argument(
        "--allow-emulator",
        action="store_true",
        help="allow an emulator when no physical Android phone is connected",
    )
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG, help="DHU .ini configuration"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        adb = executable("adb", Path("platform-tools") / "adb.exe")
        dhu = executable(
            "desktop-head-unit", Path("extras") / "google" / "auto" / "desktop-head-unit.exe"
        )
        devices, unauthorized = adb_devices(adb)
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    if unauthorized:
        print("The phone is connected but has not authorized USB debugging.", file=sys.stderr)
        print("Unlock it, accept the USB debugging prompt, then run this command again.", file=sys.stderr)
        return 2
    if not devices:
        print("No authorized Android phone was found.", file=sys.stderr)
        print("1. Connect the phone by USB and enable USB debugging.", file=sys.stderr)
        print("2. In Android Auto developer settings, select 'Start head unit server'.", file=sys.stderr)
        print("3. Run this command again. No Windows sign-in is required.", file=sys.stderr)
        return 2

    physical_devices = [serial for serial in devices if not serial.startswith("emulator-")]
    candidates = devices if args.allow_emulator else physical_devices
    if not candidates and devices:
        print("Only Android emulators are connected; a real phone is required for faithful Android Auto rendering.", file=sys.stderr)
        print("Connect the phone by USB, authorize USB debugging, and run this command again.", file=sys.stderr)
        return 2

    serial = args.serial or candidates[0]
    if serial not in devices:
        print(f"ADB device {serial!r} is not connected. Found: {', '.join(devices)}", file=sys.stderr)
        return 2
    if serial.startswith("emulator-") and not args.allow_emulator:
        print("Refusing to use an emulator by default; pass --allow-emulator only for deliberate experiments.", file=sys.stderr)
        return 2
    if len(devices) > 1 and not args.serial:
        print(f"Using {serial}; pass --serial to select another device.")

    config = args.config.resolve()
    if not config.is_file():
        print(f"DHU configuration not found: {config}", file=sys.stderr)
        return 1

    subprocess.run(
        [str(adb), "-s", serial, "forward", "tcp:5277", "tcp:5277"], check=True
    )
    print(f"Starting Android Auto DHU with phone {serial} and {config.name}...")
    return subprocess.run([str(dhu), "-c", str(config)]).returncode


if __name__ == "__main__":
    raise SystemExit(main())
