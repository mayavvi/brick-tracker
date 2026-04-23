# Project AGENTS

## Git Worktrees

Use `.worktrees/` under the repository root for local git worktrees.

- Keep `.worktrees/` gitignored.
- Prefer feature or chore branch names that describe the task, for example:
  - `feat/file-compare-indexed-workbench`
  - `chore/worktree-bootstrap`
- Treat each worktree as an isolated workspace based on committed history only.
- Uncommitted changes in the main workspace do not appear in a new worktree unless they are committed or copied intentionally.
