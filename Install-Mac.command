#!/bin/bash
# One-time Mac setup. Safe to re-run: existing data/, credentials and settings are kept.
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  PY=""
  for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
      PY="$candidate"; break
    fi
  done
  if [ -z "$PY" ]; then
    echo 'Python 3.11 or newer is required. Install it with: brew install python@3.12'
    read -r -p 'Press Return to close.'; exit 1
  fi
  "$PY" -m venv .venv || exit 1
fi
.venv/bin/python -m pip install --upgrade pip >/dev/null
.venv/bin/python -m pip install -r requirements.txt -r requirements-preparation.txt || exit 1
# Report anything still missing (FFmpeg, Ollama, qwen2.5:7b, YouTube sign-in) without stopping setup.
.venv/bin/python app_runtime.py doctor || echo 'Some items above still need setup. The app will install anyway.'
.venv/bin/python app_runtime.py install
read -r -p 'Press Return to close.'
