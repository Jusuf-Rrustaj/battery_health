#!/usr/bin/env python3
"""
Build a standalone executable for the platform this script runs on.

The output name encodes the project version (from pyproject.toml) plus the
host OS and architecture, e.g.

    battery-health-1.0.0-windows-x86_64.exe
    battery-health-1.0.0-linux-x86_64
    battery-health-1.0.0-macos-arm64

so artifacts built on different machines never collide in dist/.
"""

import argparse
import importlib.util
import platform
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENTRY_POINT = PROJECT_ROOT / "battery_health.py"
PYPROJECT = PROJECT_ROOT / "pyproject.toml"
ICON_ICO = PROJECT_ROOT / "assets" / "icon.ico"
ICON_PNG = PROJECT_ROOT / "assets" / "icon.png"

APP_NAME = "battery-health"


def read_version() -> str:
    """Read [project] version from pyproject.toml, the single source of truth."""
    if not PYPROJECT.is_file():
        raise SystemExit(f"Missing project file: {PYPROJECT}")
    with PYPROJECT.open("rb") as handle:
        config = tomllib.load(handle)
    version = config.get("project", {}).get("version")
    if not version:
        raise SystemExit(f"No [project] version set in {PYPROJECT}")
    return str(version)


def os_tag() -> str:
    system = platform.system()
    return {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(system, system.lower())


def arch_tag() -> str:
    machine = platform.machine().lower()
    aliases = {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "i386": "x86",
        "i686": "x86",
        "aarch64": "arm64",
        "arm64": "arm64",
    }
    return aliases.get(machine, machine or "unknown")


def executable_name(version: str) -> str:
    suffix = ".exe" if platform.system() == "Windows" else ""
    return f"{APP_NAME}-{version}-{os_tag()}-{arch_tag()}{suffix}"


def icon_for_platform() -> Path | None:
    """PyInstaller wants .ico on Windows, .icns on macOS; Linux has no icon slot."""
    system = platform.system()
    if system == "Windows" and ICON_ICO.is_file():
        return ICON_ICO
    if system == "Darwin":
        icns = ICON_PNG.with_suffix(".icns")
        if icns.is_file():
            return icns
    return None


def ensure_pyinstaller() -> None:
    if importlib.util.find_spec("PyInstaller") is None:
        raise SystemExit(
            "PyInstaller is not installed in this environment.\n"
            f"Install it with: {sys.executable} -m pip install pyinstaller"
        )


def build(clean: bool) -> Path:
    ensure_pyinstaller()

    version = read_version()
    name = executable_name(version)
    dist_dir = PROJECT_ROOT / "dist"
    build_dir = PROJECT_ROOT / "build"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--console",
        "--name",
        # PyInstaller appends the platform-specific suffix itself.
        name[: -len(".exe")] if name.endswith(".exe") else name,
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(build_dir),
        "--specpath",
        str(build_dir),
        "--noconfirm",
    ]
    if clean:
        cmd.append("--clean")

    icon = icon_for_platform()
    if icon is not None:
        cmd += ["--icon", str(icon)]

    cmd.append(str(ENTRY_POINT))

    print(f"Building {name} ({os_tag()}/{arch_tag()}, python {platform.python_version()})")
    print("  " + " ".join(cmd))
    subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)

    artifact = dist_dir / name
    if not artifact.is_file():
        raise SystemExit(f"Build finished but expected artifact is missing: {artifact}")
    return artifact


def package(artifact: Path) -> Path:
    """Zip the executable so the release artifact carries its version in the name."""
    release_dir = PROJECT_ROOT / "release"
    release_dir.mkdir(exist_ok=True)

    stem = artifact.stem  # name without .exe on Windows, full name elsewhere
    staging = PROJECT_ROOT / "build" / "package" / stem
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    shutil.copy2(artifact, staging / artifact.name)
    for extra in ("README.md",):
        source = PROJECT_ROOT / extra
        if source.is_file():
            shutil.copy2(source, staging / extra)

    archive_format = "zip" if platform.system() == "Windows" else "gztar"
    archive = shutil.make_archive(str(release_dir / stem), archive_format, root_dir=staging)
    return Path(archive)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-clean", action="store_true", help="reuse PyInstaller's cached analysis"
    )
    parser.add_argument(
        "--package", action="store_true", help="also produce a release archive in release/"
    )
    parser.add_argument(
        "--print-version", action="store_true", help="print the project version and exit"
    )
    parser.add_argument(
        "--print-name",
        action="store_true",
        help="print the executable name for this environment and exit",
    )
    args = parser.parse_args()

    version = read_version()

    if args.print_version:
        print(version)
        return 0

    if args.print_name:
        print(executable_name(version))
        return 0

    artifact = build(clean=not args.no_clean)
    print(f"Executable: {artifact}")

    if args.package:
        archive = package(artifact)
        print(f"Archive:    {archive}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
