#!/usr/bin/env python3
"""Validate skill metadata, local references, routing names, and duplicate blocks."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


FRONTMATTER = re.compile(r"\A---\n(?P<body>.*?)\n---\n", re.DOTALL)
NAME = re.compile(r"^name:\s*(\S+)\s*$", re.MULTILINE)
MARKDOWN_PATH = re.compile(r"(?:\]\(|`)([^`)]*?(?:references|SKILL\.md)[^`)]*)")
ROUTED_NAME = re.compile(r"`(laravel-[a-z0-9-]+)`")


def frontmatter(path: Path) -> tuple[str | None, list[str]]:
    errors: list[str] = []
    match = FRONTMATTER.match(path.read_text(encoding="utf-8"))
    if not match:
        return None, [f"{path}: missing YAML frontmatter"]
    name = NAME.search(match.group("body"))
    if not name:
        errors.append(f"{path}: frontmatter missing name")
        return None, errors
    if "description:" not in match.group("body"):
        errors.append(f"{path}: frontmatter missing description")
    return name.group(1), errors


def validate(root: Path, duplicate_limit: int) -> list[str]:
    errors: list[str] = []
    skill_files = sorted(root.glob("skills/*/SKILL.md"))
    known: dict[str, Path] = {}
    bodies: dict[Path, list[str]] = {}

    for path in skill_files:
        name, found = frontmatter(path)
        errors.extend(found)
        if name:
            if name in known:
                errors.append(f"duplicate skill name {name}: {known[name]} and {path}")
            known[name] = path
            if path.parent.name != name:
                errors.append(f"{path}: directory must match frontmatter name {name}")
        bodies[path] = path.read_text(encoding="utf-8").splitlines()

    known_names = set(known)
    for path, lines in bodies.items():
        text = "\n".join(lines)
        for raw in MARKDOWN_PATH.findall(text):
            candidate = raw.split("#", 1)[0]
            if candidate.startswith("references/"):
                target = path.parent / candidate
                if not target.exists():
                    errors.append(f"{path}: missing local reference {candidate}")
        for routed in ROUTED_NAME.findall(text):
            if routed not in known_names and routed not in {
                "laravel-react", "laravel-vue", "laravel-backend", "laravel-qa",
                "laravel-security", "laravel-deploy", "laravel-queues", "laravel-auth",
                "laravel-a11y", "laravel-frontend", "laravel-inertia", "laravel-static-analysis",
                "laravel-vite-plugin",
            }:
                errors.append(f"{path}: routes unknown skill {routed}")

    # Detect repeated prose blocks between skill bodies, ignoring short boilerplate.
    normalized: dict[Path, set[tuple[str, ...]]] = {}
    for path, lines in bodies.items():
        clean = [re.sub(r"\s+", " ", line.strip()).lower() for line in lines]
        clean = [line for line in clean if len(line) >= 35 and not line.startswith("#")]
        normalized[path] = {
            tuple(clean[index : index + duplicate_limit])
            for index in range(max(0, len(clean) - duplicate_limit + 1))
        }
    paths = list(normalized)
    for index, left in enumerate(paths):
        for right in paths[index + 1 :]:
            overlap = normalized[left] & normalized[right]
            if overlap:
                errors.append(
                    f"possible duplicated block ({duplicate_limit}+ lines): {left} and {right}"
                )

    if not skill_files:
        errors.append(f"{root}: no skills found")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".", type=Path)
    parser.add_argument("--duplicate-limit", type=int, default=20)
    args = parser.parse_args()
    errors = validate(args.root.resolve(), args.duplicate_limit)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Validated {len(list(args.root.glob('skills/*/SKILL.md')))} skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
