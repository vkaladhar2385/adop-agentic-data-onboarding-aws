---
name: push-both-remotes
description: Push the current branch to both the personal (origin) and corporate (perficient) Git remotes in one step, reporting per-remote success or failure. Use when the user asks to push, sync, publish, or back up changes to both personal and corporate, to all remotes, or mentions origin + perficient.
---

# Push to both remotes

This repo has two remotes:

| Remote | Account | URL |
|--------|---------|-----|
| `origin` | Personal (`vkaladhar2385`) | `github.com/vkaladhar2385/adop-agentic-data-onboarding-aws` |
| `perficient` | Corporate (`Perficient-Corporate`) | `github.com/Perficient-Corporate/ai-agentic-data-onboarding` |

## Steps

1. Confirm there is a commit to push (`git status`, `git log --oneline -1`). If the
   user asked to commit first, create the commit, then push. Never commit without
   being asked.
2. Run the push helper (Windows PowerShell):

```powershell
powershell -ExecutionPolicy Bypass -File .cursor/skills/push-both-remotes/scripts/push_all_remotes.ps1
```

   - Pushes the current branch to **every** configured remote (covers both `origin`
     and `perficient`), continuing past a failure so one bad remote never blocks the other.
   - Prints a per-remote summary and exits non-zero if any remote failed.

3. Report the per-remote result to the user. If a remote failed, show the error
   and the fix (see below) — do not silently retry or change git config.

## Two github.com accounts (the common failure)

Both remotes are on `github.com`, so Git Credential Manager caches one credential
per host — usually the corporate identity — and personal (`origin`) pushes return
**403**. Fix (user runs these; never change git config on their behalf):

```powershell
git config --global credential.useHttpPath true
git remote set-url origin https://vkaladhar2385@github.com/vkaladhar2385/adop-agentic-data-onboarding-aws.git
```

Then push again and authenticate with a personal-account PAT (Contents: read/write).
Alternatively `gh auth login` as the personal account, then `gh auth setup-git`.

## Notes

- To target specific remotes: `powershell -ExecutionPolicy Bypass -File .cursor/skills/push-both-remotes/scripts/push_all_remotes.ps1 -Remotes origin,perficient`
- To push a branch other than the current one: add `-Branch <name>`.
- The script uses `git push -u`, setting upstream on first push.
