#!/usr/bin/env python3
"""Require architecture documentation alongside architecture-relevant changes."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Iterable


ARCHITECTURE_FILE = "ARCHITECTURE.md"
RELEVANT_PREFIXES = (
    ".codex/",
    ".github/workflows/",
    "api/",
    "backend/",
    "contracts/",
    "frontend/",
    "kg_builder/",
    "scripts/",
    "servers/",
)
RELEVANT_FILES = {
    ".gitignore",
    "AGENTS.md",
    "package.json",
    "requirements.txt",
    "vercel.json",
}
SOURCE_CONFIG_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".jsx",
    ".mjs",
    ".py",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".vue",
    ".yaml",
    ".yml",
}
EXCLUDED_PREFIXES = ("data/", "public/", "tests/")


class GitCommandError(RuntimeError):
    """Raised when a required Git inspection command fails."""


def run_git_paths(root: Path, *args: str) -> set[str]:
    result = subprocess.run(
        ("git", *args),
        cwd=root,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        stdout = result.stdout.decode("utf-8", errors="replace").strip()
        raise GitCommandError(
            f"git {' '.join(args)} failed: {stderr or stdout or 'unknown Git error'}"
        )
    return decode_nul_paths(result.stdout)


def repository_root() -> Path:
    result = subprocess.run(
        ("git", "rev-parse", "--show-toplevel"),
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitCommandError("architecture sync check must run inside a Git repository")
    return Path(result.stdout.strip()).resolve()


def normalize_paths(paths: Iterable[str]) -> set[str]:
    return {path.replace("\\", "/") for path in paths if path}


def decode_nul_paths(output: bytes) -> set[str]:
    """Decode Git's NUL-delimited path output without corrupting newlines."""
    return {
        item.decode("utf-8", errors="surrogateescape").replace("\\", "/")
        for item in output.split(b"\0")
        if item
    }


def working_tree_changes(root: Path) -> set[str]:
    tracked = run_git_paths(
        root,
        "diff",
        "--name-only",
        "--no-renames",
        "-z",
        "--diff-filter=ACMRDT",
        "HEAD",
        "--",
    )
    untracked = run_git_paths(
        root,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
    )
    return tracked | untracked


def committed_changes(
    root: Path,
    base: str,
    head: str,
    *,
    merge_base: bool = False,
) -> set[str]:
    common = (
        "diff",
        "--name-only",
        "--no-renames",
        "-z",
        "--diff-filter=ACMRDT",
    )
    if not base or set(base) == {"0"}:
        return run_git_paths(root, "ls-tree", "-r", "--name-only", "-z", head)
    elif merge_base:
        revisions = (f"{base}...{head}",)
    else:
        revisions = (base, head)
    return run_git_paths(root, *common, *revisions, "--")


def architecture_relevant(path: str) -> bool:
    if path in RELEVANT_FILES or path.startswith(RELEVANT_PREFIXES):
        return True
    if path.startswith(EXCLUDED_PREFIXES):
        return False
    return Path(path).suffix.lower() in SOURCE_CONFIG_SUFFIXES


def missing_architecture_update(
    changed_paths: Iterable[str],
    *,
    architecture_exists: bool = True,
) -> list[str]:
    changed = normalize_paths(changed_paths)
    relevant = sorted(
        path
        for path in changed
        if path != ARCHITECTURE_FILE and architecture_relevant(path)
    )
    if not architecture_exists:
        return relevant or [ARCHITECTURE_FILE]
    if not relevant or (ARCHITECTURE_FILE in changed and architecture_exists):
        return []
    return relevant


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fail when architecture-relevant files changed without a matching "
            f"{ARCHITECTURE_FILE} update."
        )
    )
    parser.add_argument("--base", help="Base Git revision for a committed-range check")
    parser.add_argument("--head", default="HEAD", help="Head revision (default: HEAD)")
    parser.add_argument(
        "--merge-base",
        action="store_true",
        help="Compare the base/head merge base to head (for pull requests)",
    )
    parser.add_argument(
        "--hook",
        action="store_true",
        help="Use Codex Stop-hook exit semantics on failure",
    )
    args = parser.parse_args()
    if args.base is None and args.head != "HEAD":
        parser.error("--head requires --base")
    if args.merge_base and args.base is None:
        parser.error("--merge-base requires --base")
    return args


def read_hook_payload() -> dict:
    try:
        raw = sys.stdin.read()
    except OSError:
        return {}
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def hook_failure_response(message: str, *, stop_hook_active: bool) -> dict:
    if stop_hook_active:
        return {
            "continue": True,
            "systemMessage": (
                "Architecture synchronization is still failing after one automatic "
                "continuation. CI will remain blocked until it is fixed."
            ),
        }
    return {"decision": "block", "reason": message}


def report_failure(message: str, *, hook_payload: dict | None) -> int:
    if hook_payload is None:
        print(message, file=sys.stderr)
        return 1
    print(json.dumps(hook_failure_response(
        message,
        stop_hook_active=hook_payload.get("stop_hook_active") is True,
    )))
    return 0


def main() -> int:
    args = parse_args()
    hook_payload = read_hook_payload() if args.hook else None
    try:
        root = repository_root()
        changed = (
            committed_changes(
                root,
                args.base,
                args.head,
                merge_base=args.merge_base,
            )
            if args.base is not None
            else working_tree_changes(root)
        )
        missing = missing_architecture_update(
            changed,
            architecture_exists=(root / ARCHITECTURE_FILE).is_file(),
        )
        if not missing:
            if not args.hook:
                print("Architecture synchronization check passed.")
            return 0

        preview = "\n".join(f"  - {path}" for path in missing[:20])
        remainder = len(missing) - 20
        if remainder > 0:
            preview += f"\n  - ... and {remainder} more"
        message = (
            f"Architecture-relevant files changed without {ARCHITECTURE_FILE}:\n"
            f"{preview}\n"
            f"Update {ARCHITECTURE_FILE} and its Change Log before finishing."
        )
        return report_failure(message, hook_payload=hook_payload)
    except GitCommandError as exc:
        return report_failure(
            f"Architecture synchronization check could not run: {exc}",
            hook_payload=hook_payload,
        )


if __name__ == "__main__":
    raise SystemExit(main())
