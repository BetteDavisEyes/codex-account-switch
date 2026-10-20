import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import tomllib
import unittest
import uuid
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("switcher", Path(__file__).parents[1] / "codex_account_switch.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.stdout = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.stdout)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)
        self.auth = {"auth_mode": "chatgpt", "tokens": {"access_token": "synthetic-token", "account_id": "account-a"}}

    def oauth(self, name="personal"):
        m.save(self.home, name, replace=False, auth=self.auth)

    def api(self, name="relay"):
        with patch.object(m.getpass, "getpass", return_value="synthetic-key"):
            m.api(self.home, name, "https://example.invalid/v1", "gpt-6.1-sol", False)

    def test_name_traversal(self):
        for value in ["../outside", "UPPER", "status", "", "a/b", "a\\b"]:
            with self.assertRaises(ValueError): m.name_ok(value)

    def test_names_do_not_collide(self):
        self.assertNotEqual(m.key_env("a-b"), m.key_env("a_b"))
        self.assertNotEqual(m.provider_id("a-b"), m.provider_id("a_b"))

    def test_preserves_unrelated_nested_keys_and_comments(self):
        text = '# keep\nmodel="old"\nnotify=["echo", "hi"]\n[profiles.demo]\nmodel="nested"\n[features]\nfast=true\n'
        result = m.patch_config(text, {"model": "new"})
        parsed = tomllib.loads(result)
        self.assertEqual(parsed["profiles"]["demo"]["model"], "nested")
        self.assertEqual(parsed["notify"], ["echo", "hi"])
        self.assertTrue(parsed["features"]["fast"])
        self.assertIn("# keep", result)

    def test_api_setup_and_picker(self):
        self.api()
        path, _ = m.profile(self.home, "relay")
        data = m.read_json(path / "catalog.json")
        self.assertEqual(data["models"][0]["slug"], "gpt-6.1-sol")
        self.assertEqual(data["models"][0]["visibility"], "list")
        self.assertNotIn("model_messages", data["models"][0])
        self.assertNotIn("synthetic-key", self.stdout.getvalue())

    def test_reject_bad_url_before_key_prompt(self):
        for url in ["http://example.invalid", "https://name:pass@example.invalid", "https://example.invalid/?key=x"]:
            with self.assertRaises(ValueError): m.api(self.home, "relay", url, "test", False)

    def test_api_then_oauth_clears_custom_catalog(self):
        self.api(); self.oauth()
        with patch.object(m, "set_api_environment"):
            m.switch(self.home, "relay")
        cfg = tomllib.loads((self.home / "config.toml").read_text())
        self.assertEqual(cfg["model_provider"], m.provider_id("relay"))
        self.assertTrue(Path(cfg["model_catalog_json"]).exists())
        m.switch(self.home, "personal")
        cfg = tomllib.loads((self.home / "config.toml").read_text())
        self.assertNotIn("model_provider", cfg)
        self.assertNotIn("model_catalog_json", cfg)
        self.assertEqual(m.read_json(self.home / "auth.json"), self.auth)

    def test_failed_environment_does_not_change_files(self):
        self.api()
        m.atomic(self.home / "config.toml", b'model="previous"\n')
        with patch.object(m, "set_api_environment", side_effect=OSError("synthetic failure")):
            with self.assertRaises(ValueError): m.switch(self.home, "relay")
        self.assertEqual((self.home / "config.toml").read_text(), 'model="previous"\n')
        self.assertFalse((self.home / "account-switch/active.json").exists())

    def test_restore_and_traversal(self):
        m.atomic(self.home / "config.toml", b'model="before"\n')
        b = m.backup(self.home)
        m.atomic(self.home / "config.toml", b'model="after"\n')
        m.restore(self.home, b.name)
        self.assertEqual((self.home / "config.toml").read_text(), 'model="before"\n')
        with self.assertRaises(ValueError): m.restore(self.home, "../../bad")

    def test_save_requires_valid_oauth(self):
        with self.assertRaises(ValueError): m.save(self.home, "personal", auth={"OPENAI_API_KEY": "synthetic"})
        self.oauth()
        with self.assertRaises(ValueError): self.oauth()

    def test_refreshed_tokens_are_saved_only_for_same_account(self):
        self.oauth(); m.switch(self.home, "personal")
        refreshed = {"tokens": {"access_token": "new-token", "account_id": "account-a"}}
        m.write_json(self.home / "auth.json", refreshed)
        m.switch(self.home, "personal")
        self.assertEqual(m.read_json(self.home / "auth.json"), refreshed)
        self.assertEqual(m.read_json(m.profile_path(self.home, "personal") / "auth.json"), refreshed)

    def test_foreign_account_not_saved_into_active_profile(self):
        self.oauth(); m.switch(self.home, "personal")
        foreign = {"tokens": {"access_token": "other", "account_id": "account-b"}}
        m.write_json(self.home / "auth.json", foreign)
        m.switch(self.home, "personal")
        self.assertEqual(m.read_json(m.profile_path(self.home, "personal") / "auth.json"), self.auth)

    def test_process_guard_prevents_writes(self):
        with patch.object(m, "running", return_value=True):
            self.assertEqual(m.main(["--home", str(self.home), "save", "personal"]), 1)
        self.assertFalse((self.home / "account-switch").exists())

    def test_lock_excludes_parallel_writes(self):
        with m.locked(self.home):
            with self.assertRaises(ValueError):
                with m.locked(self.home): pass

    def test_unsupported_schema_is_untouched(self):
        p = self.home / "state_5.sqlite"
        with contextlib.closing(sqlite3.connect(p)) as con, con: con.execute("CREATE TABLE threads (id TEXT)")
        before = p.read_bytes()
        m.doctor(self.home, True)
        self.assertEqual(p.read_bytes(), before)

    def test_doctor_metadata_not_transcripts(self):
        p = self.home / "state_5.sqlite"
        session = self.home / "sessions/test.jsonl"
        m.atomic(session, b'{"synthetic":"original"}\n')
        with contextlib.closing(sqlite3.connect(p)) as con, con:
            con.execute("CREATE TABLE threads (model_provider TEXT, preview TEXT, has_user_event INT, first_user_message TEXT)")
            con.execute("INSERT INTO threads VALUES ('old','preview',0,'hello')")
        m.doctor(self.home, False)
        with contextlib.closing(sqlite3.connect(p)) as con, con: self.assertEqual(con.execute("SELECT model_provider FROM threads").fetchone()[0], "old")
        m.doctor(self.home, True)
        with contextlib.closing(sqlite3.connect(p)) as con, con: self.assertEqual(con.execute("SELECT model_provider,has_user_event FROM threads").fetchone(), ("openai", 1))
        self.assertEqual(session.read_bytes(), b'{"synthetic":"original"}\n')
        self.assertTrue(list((self.home / "account-switch/backups").glob("*/state_5.sqlite")))

    def test_status_no_secrets(self):
        self.api(); self.oauth()
        m.status(self.home)
        self.assertNotIn("synthetic-key", self.stdout.getvalue())
        self.assertNotIn("synthetic-token", self.stdout.getvalue())

    def test_sensitive_files_private_on_posix(self):
        if os.name == "nt": self.skipTest("POSIX mode only; Windows uses user profile ACLs")
        self.oauth()
        path = m.profile_path(self.home, "personal") / "auth.json"
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_existing_installer_not_overwritten(self):
        m.install(self.home)
        core = self.home / "bin/codex_account_switch.py"
        before = core.read_bytes()
        with self.assertRaises(ValueError): m.install(self.home)
        self.assertEqual(core.read_bytes(), before)

    def test_installed_launcher_runs_with_spaces_in_path(self):
        home = self.home / "home with spaces"
        m.install(home)
        launcher = home / "bin" / ("codex-account-switch.cmd" if os.name == "nt" else "codex-account-switch")
        env = dict(os.environ, CODEX_HOME=str(home))
        r = subprocess.run([str(launcher), "status"], env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("unmanaged", r.stdout)

    def test_cli_status_read_only(self):
        self.assertEqual(m.main(["--home", str(self.home / "absent"), "status"]), 0)
        self.assertFalse((self.home / "absent").exists())

    def test_provider_collision_refused(self):
        text='[model_providers.cas_demo]\nname="do-not-touch"\n'
        with self.assertRaises(ValueError): m.patch_config(text, {}, ("cas_demo", {"name": "new"}))

    def test_windows_user_environment_real_roundtrip(self):
        if os.name != "nt": self.skipTest("Native Windows environment integration")
        import winreg
        name = "ci-" + uuid.uuid4().hex[:16]
        env_name = m.key_env(name)
        try:
            m.set_api_environment(name, "synthetic-ci-value")
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as reg:
                self.assertEqual(winreg.QueryValueEx(reg, env_name)[0], "synthetic-ci-value")
        finally:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as reg:
                try: winreg.DeleteValue(reg, env_name)
                except FileNotFoundError: pass

    def test_api_refuses_echoed_key_input(self):
        with patch.object(m.getpass, "getpass", side_effect=m.getpass.GetPassWarning("synthetic warning")):
            with self.assertRaises(ValueError): m.api(self.home, "relay", "https://example.invalid/v1", "test", False)
        self.assertFalse((m.profile_path(self.home, "relay") / "api.key").exists())


if __name__ == "__main__":
    unittest.main()
