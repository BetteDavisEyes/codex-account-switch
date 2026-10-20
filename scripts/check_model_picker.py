#!/usr/bin/env python3
"""Local Codex app-server smoke test. Synthetic credentials; no model request."""
import importlib.util
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading

spec = importlib.util.spec_from_file_location("switcher", Path(__file__).resolve().parents[1] / "codex_account_switch.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def main():
    exe = shutil.which("codex")
    if not exe:
        raise SystemExit("Install Codex CLI first.")
    with tempfile.TemporaryDirectory(prefix="codex-picker-smoke-") as temp:
        home = Path(temp)
        m.write_json(home / "catalog.json", {"models": [m.catalog_entry("gpt-6.1-sol")]})
        m.atomic(home / "config.toml", (
            'model_provider="smoke"\nmodel="gpt-6.1-sol"\n'
            + 'model_catalog_json=' + json.dumps(str(home / "catalog.json")) + '\n'
            + '[analytics]\nenabled=false\n'
            + '[model_providers.smoke]\nname="smoke"\n'
            + 'base_url="https://example.invalid/v1"\nwire_api="responses"\nenv_key="SMOKE_ONLY_KEY"\n'
        ).encode())
        env = dict(os.environ, CODEX_HOME=temp, SMOKE_ONLY_KEY="synthetic-not-a-real-key")
        proc = subprocess.Popen([exe, "app-server", "--stdio"], cwd=temp, env=env,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
        out = queue.Queue()
        def consume():
            for line in proc.stdout:
                try: out.put(json.loads(line))
                except json.JSONDecodeError: pass
            out.put({"closed": True})
        threading.Thread(target=consume, daemon=True).start()
        def send(value):
            proc.stdin.write(json.dumps(value) + "\n"); proc.stdin.flush()
        def receive(identifier):
            for _ in range(50):
                row = out.get(timeout=15)
                if row.get("closed"): raise RuntimeError("app-server exited before response")
                if row.get("id") == identifier:
                    if "error" in row: raise RuntimeError("app-server rejected request: " + str(row["error"]))
                    return row["result"]
            raise RuntimeError("Too many notifications without response")
        try:
            send({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "picker-smoke", "version": "1.0"}}})
            receive(1)
            send({"method": "initialized"})
            send({"id": 2, "method": "model/list", "params": {"includeHidden": False}})
            result = receive(2)
            rows = result.get("data", [])
            visible = [r.get("model", r.get("id")) for r in rows]
            if "gpt-6.1-sol" not in visible:
                raise RuntimeError("Configured model absent from app-server model/list")
            print("PASS: model/list exposes gpt-6.1-sol using isolated synthetic catalog. No inference requested.")
        finally:
            proc.terminate()
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired: proc.kill(); proc.wait()
            proc.stdin.close(); proc.stdout.close()


if __name__ == "__main__":
    main()
