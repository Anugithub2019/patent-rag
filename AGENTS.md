# Repository instructions

## Architecture synchronization — mandatory

- Read `ARCHITECTURE.md` before modifying architecture-relevant source or configuration.
- Update `ARCHITECTURE.md` in the same task whenever changes affect components, routes, public contracts, dependencies, configuration, storage, data flow, deployment, build commands, or repository structure.
- Add or update a dated entry in the architecture Change Log for every architecture-relevant source or configuration change.
- Before finishing a coding task, inspect `git diff --name-only` and run `python3 scripts/check_architecture_sync.py`.
- Do not report completion when architecture-relevant files changed but `ARCHITECTURE.md` was not updated.
- If an architecture-relevant file changes without altering the structure or flows, add a concise Change Log entry stating that the internal implementation changed and the architecture is unchanged.
- Run `npm test` and `git diff --check` before completing code changes.
