#!/usr/bin/env python3
from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
lock = json.loads((root / "tools/pkc-lock.json").read_text(encoding="utf-8"))
runtime = root / lock["runtime"]
exe = runtime / ("Scripts/pkc.exe" if os.name == "nt" else "bin/pkc")
if not exe.is_file():
    raise SystemExit("locked PKC runtime is missing; invoke global pkc-project-operator doctor")
env = os.environ.copy(); env.pop("PYTHONPATH", None)
raise SystemExit(subprocess.run([str(exe), "--root", str(root), *sys.argv[1:]], env=env).returncode)
