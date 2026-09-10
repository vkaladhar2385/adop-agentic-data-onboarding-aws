#!/usr/bin/env python3
"""Push the current branch to personal and/or corporate Git remotes.

Remotes are local git config (not stored in this repo). Typical setup:
  origin      → personal GitHub
  perficient  → corporate GitHub

Usage (from repo root):
  python tools/git_push_both.py --dry-run
  python tools/git_push_both.py
  python tools/git_push_both.py --personal-only
  python tools/git_push_both.py --corporate-only
  python tools/git_push_both.py --branch feature/agent-contract
  python tools/git_push_both.py --set-upstream
"""
from __future__ import annotations

import argparse
import subprocess
import sys


def _run(cmd: list[str], *, dry_run: bool) -> int:
    print("$ " + " ".join(cmd))
    if dry_run:
        return 0
    return subprocess.run(cmd, check=False).returncode


def _git(*args: str) -> str:
    out = subprocess.check_output(["git", *args], text=True).strip()
    return out


def _remote_exists(name: str) -> bool:
    remotes = _git("remote").splitlines()
    return name in remotes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Push current branch to personal + corporate remotes")
    ap.add_argument("--branch", default=None, help="Branch to push (default: current branch)")
    ap.add_argument("--personal-remote", default="origin", help="Personal remote name")
    ap.add_argument("--corporate-remote", default="perficient", help="Corporate remote name")
    ap.add_argument("--personal-only", action="store_true", help=f"Push only --personal-remote (default: origin)")
    ap.add_argument("--corporate-only", action="store_true", help="Push only --corporate-remote")
    ap.add_argument(
        "--set-upstream",
        action="store_true",
        help="Pass -u on first push to each remote (sets upstream tracking)",
    )
    ap.add_argument("--dry-run", action="store_true", help="Print git commands only")
    args = ap.parse_args(argv)

    if args.personal_only and args.corporate_only:
        print("error: use at most one of --personal-only and --corporate-only", file=sys.stderr)
        return 2

    try:
        branch = args.branch or _git("branch", "--show-current")
    except subprocess.CalledProcessError as exc:
        print(f"error: not a git repository ({exc})", file=sys.stderr)
        return 1

    if not branch:
        print("error: detached HEAD — pass --branch explicitly", file=sys.stderr)
        return 1

    remotes: list[str] = []
    if args.corporate_only:
        remotes = [args.corporate_remote]
    elif args.personal_only:
        remotes = [args.personal_remote]
    else:
        remotes = [args.personal_remote, args.corporate_remote]

    missing = [r for r in remotes if not _remote_exists(r)]
    if missing:
        print(
            "error: remote(s) not configured: "
            + ", ".join(missing)
            + "\nAdd with: git remote add <name> <url>\nSee docs/GIT_REMOTES.md",
            file=sys.stderr,
        )
        return 1

    push_args = ["push"]
    if args.set_upstream:
        push_args.append("-u")

    rc = 0
    for remote in remotes:
        cmd = ["git", *push_args, remote, branch]
        code = _run(cmd, dry_run=args.dry_run)
        if code != 0:
            rc = code

    if rc == 0 and not args.dry_run:
        print(f"\nPushed {branch} to: {', '.join(remotes)}")
    elif args.dry_run:
        print(f"\nDry-run: would push {branch} to: {', '.join(remotes)}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
