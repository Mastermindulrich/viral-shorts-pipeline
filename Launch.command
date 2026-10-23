#!/bin/bash
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo 'Create the Python environment and install requirements first.'
  read -r -p 'Press Enter to close.'
  exit 1
fi
exec .venv/bin/python -m streamlit run dashboard.py --server.address 127.0.0.1 --browser.gatherUsageStats false
