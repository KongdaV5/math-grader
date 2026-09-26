#!/usr/bin/env python3
"""Install one verified test build at the project's established Desktop location."""

import argparse
from pathlib import Path
import os
import shutil
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("app", type=Path)
    parser.add_argument("--destination", type=Path,
                        default=Path.home() / "Desktop/Math Grader.app")
    args = parser.parse_args()
    source = args.app.resolve()
    destination = args.destination.expanduser().absolute()
    desktop = destination.parent.resolve()
    expected_desktop = (Path.home() / "Desktop").resolve()
    if not (source.is_dir() and source.name == "Math Grader.app" and
            (source / "Contents/Info.plist").is_file()):
        raise SystemExit("Source is not a Math Grader.app bundle")
    if desktop != expected_desktop or destination.name != "Math Grader.app":
        raise SystemExit("The installation destination must be a Desktop Math Grader.app path")
    if destination.is_symlink():
        raise SystemExit("Refusing to replace a symlink at the installed app path")
    if destination.exists() and not (destination.is_dir() and (destination / "Contents/Info.plist").is_file()):
        raise SystemExit("The existing destination is not an app bundle; refusing to replace it")

    install_root = Path(tempfile.mkdtemp(prefix=".math-grader-install-", dir=desktop))
    staged_app = install_root / "Math Grader.app"
    previous = install_root / "Previous Math Grader.app"
    try:
        shutil.copytree(source, staged_app, symlinks=True)
        if destination.exists():
            os.replace(destination, previous)
        try:
            os.replace(staged_app, destination)
        except BaseException:
            if previous.exists() and not destination.exists():
                os.replace(previous, destination)
            raise
    finally:
        if install_root.exists() and not install_root.is_symlink():
            shutil.rmtree(install_root)
    print(destination)


if __name__ == "__main__":
    main()
