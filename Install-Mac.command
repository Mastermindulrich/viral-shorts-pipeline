#!/bin/bash
cd "$(dirname "$0")" || exit 1
.venv/bin/python -m pip install -r requirements.txt -r requirements-preparation.txt || exit 1
.venv/bin/python - <<'PYCODE'
import pipeline as p
settings=p.read(p.ROOT/'config/settings.json')
settings['max_uploads_per_day']=20
p.write(p.ROOT/'config/settings.json',settings)
PYCODE
.venv/bin/python app_runtime.py install
read -r -p 'Press Return to close.'
