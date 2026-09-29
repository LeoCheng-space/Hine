# Contributing to HINE

This workflow is intentionally simple for team members who are still learning Git.

## Daily Workflow

1. Update your local repository from `main`.
2. Create a new branch for one task only.
3. Make your changes.
4. Commit with a clear message.
5. Push the branch.
6. Open a Pull Request.
7. Wait for review and CI checks.
8. Merge only after approval.

## Branch Naming

Use one of these patterns:

- `feature/<short-name>`
- `fix/<short-name>`
- `docs/<short-name>`
- `chore/<short-name>`

Examples:

- `feature/chat-ui`
- `feature/websocket-heartbeat`
- `fix/login-token-expiry`
- `docs/api-contract`

## Important Rules

- Do not push directly to `main`.
- Do not force-push shared branches.
- Pull the latest `main` before starting new work.
- Keep each branch focused on one task.
- Do not resolve merge conflicts by blindly accepting all changes.
- Never commit passwords, API keys, tokens, certificates, or private user data.

## Pull Request Checklist

Before opening a PR:

- The code runs locally.
- Related tests pass.
- Debug code and temporary files are removed.
- API / WebSocket / database changes are documented.
- No secrets are included.
- The PR explains what changed and how to test it.

## Commit Message Examples

- `feat: add websocket reconnect handling`
- `fix: prevent duplicate message insert`
- `docs: add REST API contract`
- `test: add message sync integration test`
- `chore: update github actions workflow`
