---
name: codex-account-switch
description: Configure and switch locally saved Codex ChatGPT accounts or Responses-compatible API providers on macOS and Windows, including a custom model picker catalog, backups and explicit sidebar metadata repair.
---

# Codex Account Switch

Read [README.md](README.md) for installation and first-time setup. Run the Python entrypoint from this checkout, or its installed launcher. Requires Python 3.11+ and Codex CLI; use a trusted personal computer.

- ChatGPT accounts use official browser login, not passwords collected by this tool. API credentials are entered with a hidden prompt, never a command-line flag.
- Close Codex Desktop and other active Codex sessions before any write. Do not switch the account from an active agent conversation. Status and help are read-only.
- Profile names and API endpoints are user configured; no shared accounts or company service addresses are bundled.
- Keep credentials and backups outside the repository. Never ask the user to paste them into chat. Restrict Windows runtime-directory access to the current Windows user; POSIX files are mode 600.
- Model catalog visibility is not backend capability. Only add model IDs supported by that provider; see the README's GPT-6.1 Sol example. No automatic promise of latest-model access.
- Switching never edits sessions or silently repairs history. For missing sidebar history, inspect `doctor` first; `doctor --apply` is an explicit backed-up metadata-only repair, not a transcript rewrite.
- Use `restore BACKUP_ID` for rollback. Test against a temporary `--home`, never the user's real accounts. Unverified Desktop/platform behavior must be stated honestly.
- For provider changes involving DeepSeek, scheduled tasks, old-chat errors or cache questions, read [the beginner troubleshooting guide](docs/deepseek-and-troubleshooting.md). Do not assume a task inherits the newly selected chat model, auto-edit task definitions, claim cached-token savings without returned usage, or equate metadata repair with transcript compatibility.
- Explain Desktop, CLI and API Key in plain language first. Keep configuration internals in [advanced details](docs/advanced.md); never describe generic catalog metadata as a provider-tested preset.
