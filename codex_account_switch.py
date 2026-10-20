#!/usr/bin/env python3
"""Local Codex profile switcher. No third-party Python dependencies."""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import tomllib
import uuid
import warnings
from urllib.parse import urlsplit

ROUTING = {"model", "review_model", "model_provider", "model_catalog_json",
           "model_reasoning_effort", "cli_auth_credentials_store"}
RESERVED = {"status", "login", "save", "api", "switch", "restore", "doctor", "models", "install", "key"}
PROFILE_RE = re.compile(r"[a-z][a-z0-9_-]{0,39}\Z")


def name_ok(name):
    if not PROFILE_RE.fullmatch(name) or name in RESERVED:
        raise ValueError("Use a non-reserved lowercase name: letters, digits, underscore or hyphen (max 40).")
    return name


def provider_id(name):
    return "cas_" + name.replace("-", "_") + "_" + hashlib.sha256(name.encode()).hexdigest()[:8]


def key_env(name):
    return "CODEX_SWITCH_" + hashlib.sha256(name.encode()).hexdigest()[:16].upper() + "_KEY"


def private_dir(path):
    path.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        path.chmod(0o700)


def atomic(path, data):
    private_dir(path.parent)
    fd, temp = tempfile.mkstemp(prefix=".cas-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt":
            os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def write_json(path, value):
    atomic(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def running():
    """Fail closed if process inspection is unavailable."""
    if os.name == "nt":
        r = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, check=True)
        import csv
        names = {row[0].lower() for row in csv.reader(r.stdout.splitlines()) if row}
        return bool(names & {"codex.exe", "chatgpt.exe"})
    r = subprocess.run(["ps", "-axo", "pid=,comm="], capture_output=True, text=True, check=True)
    for line in r.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2 or int(parts[0]) == os.getpid():
            continue
        exe = parts[1].lower()
        if Path(exe).name in {"codex", "chatgpt"} or "/codex.app/" in exe or "/chatgpt.app/" in exe:
            return True
    return False


def require_closed():
    if running():
        raise ValueError("Codex is running. Fully quit Desktop and CLI sessions, then run this in an external terminal.")


@contextlib.contextmanager
def locked(home):
    root = home / "account-switch"
    private_dir(root)
    path = root / "write.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError("Another operation or a stale write.lock exists. Check processes before removing that lock.")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(str(os.getpid()))
        yield
    finally:
        path.unlink(missing_ok=True)


def profile_path(home, name):
    name_ok(name)
    p = home / "account-switch" / "profiles" / name
    if p.is_symlink():
        raise ValueError("Profile directory must not be a symbolic link.")
    return p


def profile(home, name):
    path = profile_path(home, name)
    data = read_json(path / "profile.json")
    if data.get("kind") not in {"oauth", "api"}:
        raise ValueError("Unknown profile kind.")
    return path, data


def oauth_valid(auth):
    return isinstance(auth, dict) and isinstance(auth.get("tokens"), dict) and bool(auth["tokens"].get("access_token"))


def config(home):
    path = home / "config.toml"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return text, tomllib.loads(text)


def patch_config(text, updates, provider=None):
    """Only replace scalar root routing keys; preserve other text and tables."""
    original = tomllib.loads(text)
    root, rest = [], []
    in_tables = False
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("["):
            in_tables = True
        (rest if in_tables else root).append(line)
    for key in ROUTING & original.keys():
        if not isinstance(original[key], str):
            raise ValueError(f"Root {key} must be a string; refusing to rewrite an unfamiliar config.")
        pattern = re.compile(r"^\s*" + re.escape(key) + r"\s*=")
        matches = [i for i, line in enumerate(root) if pattern.match(line)]
        if len(matches) != 1 or "\"\"\"" in root[matches[0]] or "'''" in root[matches[0]]:
            raise ValueError(f"Unfamiliar formatting for {key}; no changes made.")
        root[matches[0]] = ""
    header = "".join(root).rstrip() + "\n"
    header += "".join(f"{key} = {json.dumps(value)}\n" for key, value in updates.items()) + "\n"
    result = header + "".join(rest)
    if provider:
        pid, values = provider
        existing = original.get("model_providers", {}).get(pid)
        if existing is not None and existing != values:
            raise ValueError("Provider ID already has a different config. Use a new profile name or restore first.")
        if existing is None:
            result += f'\n[model_providers.{pid}]\n'
            result += "".join(f"{key} = {json.dumps(value)}\n" for key, value in values.items())
    parsed = tomllib.loads(result)
    # Every unrelated value must survive; comments/layout are retained where possible.
    before = {k: v for k, v in original.items() if k not in ROUTING and k != "model_providers"}
    after = {k: v for k, v in parsed.items() if k not in ROUTING and k != "model_providers"}
    if before != after:
        raise ValueError("Unrelated config changed; refusing the write.")
    return result


def backup(home):
    bid = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    path = home / "account-switch" / "backups" / bid
    private_dir(path)
    for rel in ("auth.json", "config.toml", "account-switch/active.json"):
        src = home / rel
        if src.exists():
            atomic(path / rel, src.read_bytes())
    write_json(path / "manifest.json", {"files": [rel for rel in ("auth.json", "config.toml", "account-switch/active.json") if (path / rel).exists()]})
    return path


def restore(home, bid):
    if not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}", bid):
        raise ValueError("Use a backup ID printed by switch/doctor, not a path.")
    path = home / "account-switch" / "backups" / bid
    files = set(read_json(path / "manifest.json")["files"])
    allowed = {"auth.json", "config.toml", "account-switch/active.json"}
    if not files <= allowed:
        raise ValueError("Invalid backup manifest.")
    data = {rel: (path / rel).read_bytes() for rel in files}
    # Backup current state before replacing it. API env variables are not changed by restore.
    saved = backup(home)
    for rel in allowed:
        if rel in data:
            atomic(home / rel, data[rel])
        else:
            (home / rel).unlink(missing_ok=True)
    print("Restored config/auth; current state backed up as", saved.name)
    print("API environment was not restored. To reactivate an API profile, run its switch command again.")


def save(home, name, model=None, replace=False, auth=None):
    path = profile_path(home, name)
    if (path / "profile.json").exists() and not replace:
        raise ValueError("Profile exists. Use --replace only if you intend to overwrite it.")
    auth = auth if auth is not None else read_json(home / "auth.json")
    if not oauth_valid(auth):
        raise ValueError("No file-backed ChatGPT OAuth login found. Use login NAME for browser authorization.")
    if (path / "profile.json").exists():
        archive = home / "account-switch" / "profile-backups" / (name + "-" + uuid.uuid4().hex)
        shutil.copytree(path, archive)
    write_json(path / "auth.json", auth)
    write_json(path / "profile.json", {"kind": "oauth", "model": model})
    print("Saved local OAuth profile:", name)


def login(home, name, model, device, replace):
    path = profile_path(home, name)
    if path.exists() and not replace:
        raise ValueError("Profile already exists; choose a new name or explicitly use --replace.")
    exe = shutil.which("codex")
    if not exe:
        raise ValueError("Install Codex CLI and ensure codex is on PATH first.")
    # Isolated file store avoids replacing the currently active user's credentials/keyring.
    private_dir(home / "account-switch")
    with tempfile.TemporaryDirectory(prefix="login-", dir=home / "account-switch") as temp:
        atomic(Path(temp) / "config.toml", b'cli_auth_credentials_store = "file"\n')
        env = {k: v for k, v in os.environ.items() if k not in {"OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN"}}
        env["CODEX_HOME"] = temp
        cmd = [exe, "login"] + (["--device-auth"] if device else [])
        subprocess.run(cmd, env=env, check=True)
        auth = read_json(Path(temp) / "auth.json")
        save(home, name, model, replace, auth)
    print("Login saved only. Activate with: codex-account-switch", name)


def api(home, name, url, model, replace):
    path = profile_path(home, name)
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("Use a credential-free HTTPS API base URL, without query or fragment.")
    if path.exists() and not replace:
        raise ValueError("Profile exists; use a new name or --replace.")
    catalog_entry(model)  # Validate all non-secret inputs before storing credentials.
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            key = getpass.getpass("API Key (hidden; stored locally): ").strip()
    except getpass.GetPassWarning:
        raise ValueError("A secure terminal is required for hidden API Key input; refusing echoed input.") from None
    if not key or any(c.isspace() for c in key):
        raise ValueError("API key must be nonempty and contain no whitespace.")
    if path.exists():
        archive = home / "account-switch" / "profile-backups" / (name + "-" + uuid.uuid4().hex)
        shutil.copytree(path, archive)
    atomic(path / "api.key", key.encode())
    write_json(path / "profile.json", {"kind": "api", "base_url": url.rstrip("/"), "model": model})
    models(home, name, [model])
    print("Saved API profile. The server must support the Responses API; Chat Completions alone is insufficient.")


def set_api_environment(name, key):
    """Use the same OS mechanisms as Desktop launchers, never print the secret."""
    env_name = key_env(name)
    if os.name == "nt":
        import winreg
        import ctypes
        from ctypes import wintypes
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Environment") as reg:
            winreg.SetValueEx(reg, env_name, 0, winreg.REG_SZ, key)
        result = ctypes.c_size_t()
        send = ctypes.windll.user32.SendMessageTimeoutW
        send.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_void_p,
                         wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
        send.restype = ctypes.c_ssize_t
        text = ctypes.create_unicode_buffer("Environment")
        if not send(65535, 0x1A, 0, ctypes.cast(text, ctypes.c_void_p), 2, 5000, ctypes.byref(result)):
            raise ValueError("Key saved to user environment, but refresh notification failed. Restart/sign in to Windows before use.")
    elif sys.platform == "darwin":
        # Key is not echoed or stored in shell history; launchctl receives it as an argument.
        subprocess.run(["launchctl", "setenv", env_name, key], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    else:
        raise ValueError("This package supports macOS and Windows only.")
    return env_name


def catalog_entry(model, priority=1):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}", model):
        raise ValueError("Invalid model ID.")
    return {"slug": model, "display_name": model, "description": "User-configured provider model; backend support must be verified.",
            "default_reasoning_level": "medium", "supported_reasoning_levels": [{"effort": "medium", "description": "Provider-dependent"}],
            "shell_type": "unified_exec", "visibility": "list", "supported_in_api": True, "priority": priority,
            "upgrade": None, "default_reasoning_summary": "none", "support_verbosity": False,
            "default_verbosity": None, "apply_patch_tool_type": "freeform", "web_search_tool_type": "text",
            "truncation_policy": {"mode": "tokens", "limit": 10000}, "supports_image_detail_original": False,
            "context_window": 128000, "effective_context_window_percent": 95,
            "experimental_supported_tools": [], "input_modalities": ["text"], "supports_search_tool": False}


def models(home, name, ids):
    path, info = profile(home, name)
    if info["kind"] != "api":
        raise ValueError("Custom catalogs apply only to API profiles.")
    ids = list(dict.fromkeys([info["model"], *ids]))
    entries = [catalog_entry(m, i + 1) for i, m in enumerate(ids)]
    if (path / "catalog.json").exists():
        atomic(path / ("catalog-backup-" + uuid.uuid4().hex + ".json"), (path / "catalog.json").read_bytes())
    write_json(path / "catalog.json", {"models": entries})
    print("Saved model picker catalog; run switch again and restart Desktop. This does not test server support.")


def switch(home, name):
    path, info = profile(home, name)
    text, old_config = config(home)
    if old_config.get("profile"):
        raise ValueError("An active config profile may override routing; resolve config.profile before switching.")
    updates = {"cli_auth_credentials_store": "file"}
    provider = None
    if info.get("model"):
        updates["model"] = info["model"]
    if info["kind"] == "oauth":
        auth = read_json(path / "auth.json")
        if not oauth_valid(auth):
            raise ValueError("Saved OAuth credentials are invalid; log in again.")
    else:
        key = (path / "api.key").read_text().strip()
        if not key:
            raise ValueError("Empty API key.")
        pid = provider_id(name)
        env_name = key_env(name)
        provider = (pid, {"name": pid, "base_url": info["base_url"], "wire_api": "responses", "env_key": env_name})
        updates["model_provider"] = pid
        if (path / "catalog.json").exists():
            read_json(path / "catalog.json")
            updates["model_catalog_json"] = str(path / "catalog.json")
    proposed = patch_config(text, updates, provider)
    # Save refreshed tokens only when current file is still the known active account.
    active = home / "account-switch" / "active.json"
    if active.exists() and (home / "auth.json").exists():
        prev = read_json(active)
        if prev.get("kind") == "oauth":
            current = read_json(home / "auth.json")
            previous_path, _ = profile(home, prev["name"])
            saved = read_json(previous_path / "auth.json")
            current_id = current.get("tokens", {}).get("account_id")
            saved_id = saved.get("tokens", {}).get("account_id")
            if oauth_valid(current) and current_id and current_id == saved_id:
                write_json(previous_path / "auth.json", current)
                if previous_path == path:
                    auth = current
    b = backup(home)
    try:
        if info["kind"] == "api":
            set_api_environment(name, key)
        else:
            write_json(home / "auth.json", auth)
        atomic(home / "config.toml", proposed.encode())
        write_json(active, {"name": name, "kind": info["kind"]})
    except Exception:
        # File rollback is deterministic; API env vars can remain, but are not selected by restored config.
        for rel in ("auth.json", "config.toml", "account-switch/active.json"):
            if (b / rel).exists():
                atomic(home / rel, (b / rel).read_bytes())
            else:
                (home / rel).unlink(missing_ok=True)
        raise ValueError("Switch failed; config/auth rolled back. OS API environment may remain set. Check backup " + b.name) from None
    print("Switched to", name, "| rollback:", b.name)
    print("Restart Desktop. For API profiles, reopen terminals too so they inherit the configured user environment.")
    print("Sessions were not edited. For missing history run doctor first; repair requires doctor --apply.")


def doctor(home, apply=False):
    """Known-schema metadata only; never rewrite or delete a transcript."""
    _, cfg = config(home)
    expected = cfg.get("model_provider", "openai")
    snapshots = []
    for rel in ("state_5.sqlite", "sqlite/state_5.sqlite"):
        path = home / rel
        if not path.exists():
            continue
        con = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        try:
            columns = {row[1] for row in con.execute("PRAGMA table_info(threads)")}
            if not {"model_provider", "preview", "has_user_event", "first_user_message"} <= columns:
                print(rel, "unsupported schema; not modified")
                continue
            mismatch = con.execute("SELECT COUNT(*) FROM threads WHERE preview != '' AND model_provider != ?", (expected,)).fetchone()[0]
            events = con.execute("SELECT COUNT(*) FROM threads WHERE has_user_event=0 AND first_user_message != ''").fetchone()[0]
            print(rel, "provider_mismatches=", mismatch, "missing_user_events=", events)
            snapshots.append((rel, path, mismatch + events))
        finally:
            con.close()
    if apply:
        b = backup(home)
        for rel, path, count in snapshots:
            if not count:
                continue
            private_dir((b / rel).parent)
            with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as src, sqlite3.connect(b / rel) as dst:
                src.backup(dst)
            with sqlite3.connect(path) as con:
                con.execute("PRAGMA busy_timeout=5000")
                con.execute("UPDATE threads SET model_provider=? WHERE preview != '' AND model_provider != ?", (expected, expected))
                con.execute("UPDATE threads SET has_user_event=1 WHERE has_user_event=0 AND first_user_message != ''")
        print("Metadata repaired; backup:", b.name, "(SQLite backups require manual restoration while Codex is closed).")
    elif not snapshots:
        print("No supported history index found. No changes made.")
    else:
        print("Read-only check. doctor --apply changes known metadata only after a backup; never sessions.")


def status(home):
    _, cfg = config(home)
    root = home / "account-switch" / "profiles"
    print("Saved profiles:", ", ".join(sorted(p.parent.name for p in root.glob("*/profile.json"))) if root.exists() else "none")
    if root.exists():
        for p in sorted(root.glob("*/profile.json")):
            info = read_json(p)
            print(" ", p.parent.name, info["kind"], "model=" + str(info.get("model") or "official default"))
    active = home / "account-switch" / "active.json"
    print("Active:", read_json(active).get("name") if active.exists() else "unmanaged")
    print("Config provider:", cfg.get("model_provider", "openai"), "| model:", cfg.get("model", "default"))
    print("Catalog configured:", bool(cfg.get("model_catalog_json")))
    print("No credentials or endpoint URLs are printed.")


def install(home):
    target = home / "bin"
    private_dir(target)
    source = Path(__file__).resolve()
    # Install a copy, so moving/deleting the checkout does not break the launcher.
    core = target / "codex_account_switch.py"
    paths = [core, target / ("codex-account-switch.cmd" if os.name == "nt" else "codex-account-switch")]
    if any(p.exists() for p in paths):
        raise ValueError("An installed switcher already exists. Not overwriting; use this checkout directly or back up old entrypoints first.")
    if os.name == "nt":
        launcher = '@echo off\r\n"' + sys.executable.replace('%', '%%') + '" "%~dp0codex_account_switch.py" %*\r\n'
    else:
        launcher = '#!/bin/sh\nexec ' + __import__('shlex').quote(sys.executable) + ' "$(dirname "$0")/codex_account_switch.py" "$@"\n'
    atomic(core, source.read_bytes())
    atomic(paths[1], launcher.encode())
    if os.name != "nt":
        paths[1].chmod(0o700)
    print("Installed launcher:", paths[1])
    print("Optional: add its bin directory to PATH. No existing installation was overwritten.")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # Short form NAME is equivalent to switch NAME.
    if argv and not argv[0].startswith("-") and argv[0] not in RESERVED:
        argv.insert(0, "switch")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--home", type=Path, default=Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))))
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("install")
    for action in ("login", "save"):
        s = sub.add_parser(action); s.add_argument("name"); s.add_argument("--model"); s.add_argument("--replace", action="store_true")
        if action == "login": s.add_argument("--device-auth", action="store_true")
    a = sub.add_parser("api"); a.add_argument("name"); a.add_argument("--url", required=True); a.add_argument("--model", required=True); a.add_argument("--replace", action="store_true")
    s = sub.add_parser("switch"); s.add_argument("name")
    s = sub.add_parser("models"); s.add_argument("name"); s.add_argument("ids", nargs="+")
    s = sub.add_parser("restore"); s.add_argument("backup_id")
    s = sub.add_parser("doctor"); s.add_argument("--apply", action="store_true")
    args = p.parse_args(argv)
    home = args.home.expanduser().resolve()
    try:
        if args.command == "status": status(home); return 0
        if args.command == "doctor" and not args.apply: doctor(home); return 0
        require_closed()
        with locked(home):
            if args.command == "install": install(home)
            elif args.command == "save": save(home, args.name, args.model, args.replace)
            elif args.command == "login": login(home, args.name, args.model, args.device_auth, args.replace)
            elif args.command == "api": api(home, args.name, args.url, args.model, args.replace)
            elif args.command == "switch": switch(home, args.name)
            elif args.command == "models": models(home, args.name, args.ids)
            elif args.command == "restore": restore(home, args.backup_id)
            elif args.command == "doctor": doctor(home, args.apply)
        return 0
    except (ValueError, OSError, KeyError, json.JSONDecodeError, tomllib.TOMLDecodeError, subprocess.SubprocessError) as exc:
        # Avoid exception details from subprocess/config parsing: they can contain secrets.
        if isinstance(exc, ValueError) and not isinstance(exc, (json.JSONDecodeError, tomllib.TOMLDecodeError)):
            print("Error:", str(exc), file=sys.stderr)
        else:
            print("Operation failed (" + type(exc).__name__ + "). Check paths/permissions and backups; no credentials printed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
