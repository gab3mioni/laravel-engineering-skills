#!/usr/bin/env python3
"""Validate plugin manifests and Claude compatibility wrappers."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def load(path: Path, errors: list[str]) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path}: invalid JSON ({exc})")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{path}: manifest root must be an object")
        return {}
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    errors: list[str] = []
    claude = load(root / ".claude-plugin/plugin.json", errors)
    codex = load(root / ".codex-plugin/plugin.json", errors)
    for path in (root / ".claude-plugin/marketplace.json", root / ".agents/plugins/marketplace.json"):
        load(path, errors)

    versions = {manifest.get("version") for manifest in (claude, codex)}
    if versions != {"0.3.0"}:
        errors.append(f"plugin versions must agree at 0.3.0, got {versions}")
    names = {claude.get("name"), codex.get("name")}
    if names != {"laravel-engineering-skills"}:
        errors.append(f"plugin names must agree at laravel-engineering-skills, got {names}")
    if codex.get("skills") != "./skills/":
        errors.append(".codex-plugin/plugin.json: skills must point to ./skills/")

    wrappers = sorted((root / "agents").glob("*.md"))
    role_names = {
        path.name
        for path in (root / "skills").glob("laravel-role-*")
        if (path / "SKILL.md").exists()
    }
    if len(wrappers) != 8:
        errors.append(f"expected eight Claude wrappers, found {len(wrappers)}")
    for wrapper in wrappers:
        text = wrapper.read_text(encoding="utf-8")
        match = re.search(r"`(laravel-role-[a-z0-9-]+)`", text)
        if not match or match.group(1) not in role_names:
            errors.append(f"{wrapper}: does not point to an existing shared role")
        if "tools:" not in text:
            errors.append(f"{wrapper}: missing tools frontmatter")
    print(f"Validated manifests and {len(wrappers)} Claude wrappers") if not errors else None
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
