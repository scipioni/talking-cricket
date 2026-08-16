"""Bumps the semver version in pyproject.toml. Used by the release:* Task targets
(Taskfile.yml) rather than pulling in a dedicated version-bumping dependency, since
the only thing needed is a single `version = "X.Y.Z"` line.

Usage:
    uv run python scripts/bump_version.py major|minor|patch
    uv run python scripts/bump_version.py --set 1.2.3

Prints the new version to stdout (and nothing else), so it can be captured by
shell command substitution in the Taskfile.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"
VERSION_RE = re.compile(r'^version = "(\d+)\.(\d+)\.(\d+)"$', re.MULTILINE)


def current_version() -> tuple[int, int, int]:
    text = PYPROJECT.read_text(encoding="utf-8")
    match = VERSION_RE.search(text)
    if not match:
        raise SystemExit(f"could not find a `version = \"X.Y.Z\"` line in {PYPROJECT}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def bump(part: str) -> tuple[int, int, int]:
    major, minor, patch = current_version()
    if part == "major":
        return major + 1, 0, 0
    if part == "minor":
        return major, minor + 1, 0
    if part == "patch":
        return major, minor, patch + 1
    raise ValueError(f"unknown part: {part}")


def write_version(new_version: tuple[int, int, int]) -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    new_text, count = VERSION_RE.subn(
        'version = "{}.{}.{}"'.format(*new_version), text, count=1
    )
    if count != 1:
        raise SystemExit("failed to replace the version line")
    PYPROJECT.write_text(new_text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("part", nargs="?", choices=["major", "minor", "patch"])
    group.add_argument("--set", dest="set_version", metavar="X.Y.Z")
    args = parser.parse_args()

    if args.set_version:
        match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", args.set_version)
        if not match:
            raise SystemExit(f"invalid version: {args.set_version!r}, expected X.Y.Z")
        new_version = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    else:
        new_version = bump(args.part)

    write_version(new_version)
    print("{}.{}.{}".format(*new_version))


if __name__ == "__main__":
    main()
